import os
import subprocess
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

def list_audio_cards():
    if os.name == 'nt':
        return list_audio_cards_windows()
    else:
        return list_audio_cards_linux()

def list_audio_cards_linux():
    print("\n--- Available Audio Playback Devices (ALSA Cards) ---")
    try:
        result = subprocess.run(['aplay', '-l'], capture_output=True, text=True)
        lines = result.stdout.split('\n')
        cards = []
        for line in lines:
            if line.startswith('card '):
                print(line)
                match = re.search(r'card (\d+):', line)
                if match:
                    cards.append(int(match.group(1)))
        return cards
    except FileNotFoundError:
        print("Error: 'aplay' command not found. Ensure ALSA utilities are installed.")
        return []

def list_audio_cards_windows():
    print("\n--- Available Windows Audio Playback Devices ---")
    cards = []

    # 1. Try sounddevice if installed
    try:
        import sounddevice as sd
        devs = sd.query_devices()
        for idx, dev in enumerate(devs):
            if dev.get('max_output_channels', 0) > 0:
                print(f"[{idx}] {dev.get('name')}")
                cards.append(idx)
        if cards:
            return cards
    except ImportError:
        pass

    # 2. Try pyaudio if installed
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        for idx in range(p.get_device_count()):
            dev = p.get_device_info_by_index(idx)
            if dev.get('maxOutputChannels', 0) > 0:
                print(f"[{idx}] {dev.get('name')}")
                cards.append(idx)
        p.terminate()
        if cards:
            return cards
    except ImportError:
        pass

    # 3. Fallback: PowerShell query for audio devices
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_SoundDevice | Select-Object -ExpandProperty Name"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        names = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        for idx, name in enumerate(names):
            print(f"[{idx}] {name}")
            cards.append(idx)
        if cards:
            return cards
    except Exception:
        pass

    print("[0] Default Windows Audio Output Device")
    return [0]

def test_audio(index: int):
    print("Testing speaker... (You should hear a sound)")
    if os.name == 'nt':
        try:
            import winsound
            winsound.Beep(440, 600)  # 440 Hz for 600ms
            print("Sound test passed (Windows tone generated).")
        except Exception:
            try:
                import pygame
                pygame.mixer.init()
                print("Windows audio system initialized successfully.")
            except Exception as e:
                print(f"Audio test note: {e}")
    else:
        os.system(f"speaker-test -c2 -t sine -f 440 -l 1 -D plughw:{index},0")

def configure_audio():
    cards = list_audio_cards()
    if not cards:
        print("No audio playback devices detected.")
        return

    default_card = cards[0]
    print(f"\nDefaulting to Device Index {default_card}.")
    
    choice = input(f"\nEnter the Device Index you want to use [Default {default_card}]: ").strip()
    try:
        index = int(choice) if choice else default_card
    except ValueError:
        print(f"Invalid input. Using default index {default_card}.")
        index = default_card
    
    env_content = ""
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, 'r', encoding="utf-8") as f:
            env_content = f.read()
    
    if "SPEAKER_CARD_INDEX" in env_content:
        env_content = re.sub(r'SPEAKER_CARD_INDEX=.*', f'SPEAKER_CARD_INDEX={index}', env_content)
    else:
        env_content = env_content.rstrip() + f"\nSPEAKER_CARD_INDEX={index}\n"
    
    with open(ENV_PATH, 'w', encoding="utf-8") as f:
        f.write(env_content)
    
    print(f"\nSuccess! SPEAKER_CARD_INDEX set to {index} in {ENV_PATH}")
    test_audio(index)

if __name__ == "__main__":
    configure_audio()
