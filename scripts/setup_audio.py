import os
import subprocess
import re

def list_audio_cards():
    print("\n--- Available Audio Playback Devices (Cards) ---")
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
        print("Error: 'aplay' command not found. Are you on Windows?")
        return []

def configure_audio():
    cards = list_audio_cards()
    if not cards:
        print("No cards detected via aplay.")
        return

    # Suggest USB card (usually it has 'USB' in the name)
    default_card = cards[0]
    print(f"\nDefaulting to Card {default_card} (First detected).")
    
    choice = input(f"\nEnter the Card Index you want to use [Default {default_card}]: ").strip()
    index = int(choice) if choice else default_card
    
    # Update config.py or create an audio_config.py
    # For ORION, we use app/core/config.py or .env
    
    env_path = ".env"
    env_content = ""
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            env_content = f.read()
    
    if "SPEAKER_CARD_INDEX" in env_content:
        env_content = re.sub(r'SPEAKER_CARD_INDEX=.*', f'SPEAKER_CARD_INDEX={index}', env_content)
    else:
        env_content += f"\nSPEAKER_CARD_INDEX={index}"
    
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    print(f"\nSuccess! SPEAKER_CARD_INDEX set to {index} in {env_path}")
    print("Testing speaker... (You should hear a sound)")
    os.system(f"speaker-test -c2 -t sine -f 440 -l 1 -D plughw:{index},0")

if __name__ == "__main__":
    configure_audio()
