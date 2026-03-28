import os
import threading
import time
import uuid
import re
import queue
import asyncio
import pygame
from typing import Optional, List
from gtts import gTTS
import speech_recognition as sr
from ..services.sarvam_service import SarvamService
from ..services.eleven_labs_service import ElevenLabsService
from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger()

# Shared state for audio interactions
class VoiceState:
    def __init__(self):
        self.is_speaking = False
        self.is_listening = False
        self.stop_requested = False
        self.last_transcript = ""
        self.active_user = "Unknown"

voice_state = VoiceState()

class SpeakerService:
    def __init__(self):
        self.playback_queue = queue.Queue()
        self.current_proc = None
        self.running = True
        self._init_mixer()
        
        # Services
        self.sarvam = SarvamService()
        self.eleven = ElevenLabsService()
        
        # Start playback thread
        self.thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.thread.start()

    def _init_mixer(self):
        try:
            pygame.mixer.init()
        except Exception as e:
            logger.error(f"Pygame mixer init failed: {e}")

    def _playback_loop(self):
        while self.running:
            try:
                # Wait for next audio file
                audio_file = self.playback_queue.get(timeout=0.1)
                voice_state.is_speaking = True
                
                try:
                    if os.name == 'nt':
                        # Windows playback
                        pygame.mixer.music.load(audio_file)
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy() and not voice_state.stop_requested:
                            time.sleep(0.05)
                        pygame.mixer.music.stop()
                    else:
                        # Linux/Pi optimized playback
                        import subprocess
                        card = settings.SPEAKER_CARD_INDEX
                        device = f"plughw:{card},0"
                        # Try mpg123 for lower latency and better ALSA handling
                        try:
                            subprocess.run(['mpg123', '-q', '-a', device, audio_file], 
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
                        except:
                            # Fallback to aplay (raw) or simple os.system
                            os.system(f"aplay -q -D {device} {audio_file} > /dev/null 2>&1")
                
                except Exception as e:
                    logger.error(f"Playback error: {e}")
                
                finally:
                    voice_state.is_speaking = False
                    if os.path.exists(audio_file):
                        try: os.remove(audio_file)
                        except: pass
                    self.playback_queue.task_done()
                    
            except queue.Empty:
                continue

    def speak(self, text: str):
        """Generate and queue speech from text with tiered fallback."""
        if not text: return
        
        # Sentence splitting for faster perceived start time
        sentences = [s.strip() for s in re.split(r'(?<=[.!?\n]) +', text) if s.strip()]
        
        for sentence in sentences:
            temp_file = f"temp_speech_{uuid.uuid4().hex}.mp3"
            success = False
            
            # Simple language detection for Hindi/Devanagari
            is_hindi = any('\u0900' <= char <= '\u097F' for char in sentence)
            
            if not is_hindi:
                # Tier 1 (Eng): ElevenLabs
                success = self.eleven.generate_tts(sentence, temp_file)
                if success: logger.info("TTS: ElevenLabs (English) success.")
                
                # Tier 2 (Eng): Sarvam (Priya voice)
                if not success:
                    success = self.sarvam.generate_tts(sentence, temp_file)
                    if success: logger.info("TTS: Sarvam (English Fallback) success.")
            else:
                # Tier 1 (Hin): Sarvam
                success = self.sarvam.generate_tts(sentence, temp_file)
                if success: logger.info("TTS: Sarvam (Hindi) success.")
                
                # Tier 2 (Hin): ElevenLabs (Might sound accented but works)
                if not success:
                    success = self.eleven.generate_tts(sentence, temp_file)
                    if success: logger.info("TTS: ElevenLabs (Hindi Fallback) success.")

            # Tier 3: gTTS (Last Resort)
            if not success:
                try:
                    tts = gTTS(text=sentence, lang='en')
                    tts.save(temp_file)
                    success = True
                    logger.info("TTS: gTTS generation success (Emergency Fallback).")
                except Exception as e:
                    logger.error(f"TTS: Final gTTS fallback failed: {e}")

            if success:
                self.playback_queue.put(temp_file)

    def stop(self):
        voice_state.stop_requested = True
        # Clear queue
        while not self.playback_queue.empty():
            try:
                fn = self.playback_queue.get_nowait()
                if os.path.exists(fn): os.remove(fn)
            except: pass
        voice_state.stop_requested = False

class VoiceListenerService:
    def __init__(self, callback):
        self.callback = callback # Function to call with transcript
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 1000
        self.recognizer.dynamic_energy_threshold = True
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def _listen_loop(self):
        logger.info("ORION Voice Listener active.")
        
        while self.running:
            # 1. Wait if speaker is active (Echo mitigation)
            if voice_state.is_speaking:
                time.sleep(0.1)
                continue

            try:
                with sr.Microphone(device_index=settings.MIC_INDEX) as source:
                    # Adjust for background noise quickly
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    
                    voice_state.is_listening = True
                    logger.debug("Listening...")
                    
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                    voice_state.is_listening = False
                    
                    try:
                        text = self.recognizer.recognize_google(audio)
                        logger.info(f"Heard: {text}")
                        
                        # Check for wake word if not in active conversation
                        text_lower = text.lower()
                        is_wake = any(w in text_lower for w in settings.WAKE_WORDS)
                        
                        if is_wake:
                            # Strip wake word and pass to engine
                            clean_text = text_lower
                            for w in settings.WAKE_WORDS:
                                clean_text = clean_text.replace(w, "").strip()
                            
                            if clean_text:
                                self.callback(clean_text)
                            else:
                                # Just wake word? Give an ACK.
                                # Future: sound effect
                                pass
                        
                    except sr.UnknownValueError:
                        pass # Typical for background noise
                    except Exception as e:
                        logger.debug(f"Recognition error: {e}")

            except Exception as e:
                logger.error(f"Microphone error: {e}")
                time.sleep(2)

    def stop(self):
        self.running = False
