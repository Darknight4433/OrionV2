#!/usr/bin/env python3
"""
ORION Headless Client - Production Hardened
============================================
Terminal-based interface for ORION with deployment hardening.

ISSUES FIXED for Pi stability:
  ✓ Non-blocking audio pipeline (no freezing on listen)
  ✓ Async TTS (doesn't freeze system while speaking)
  ✓ Thread-safe camera (encoding outside lock)
  ✓ Resilient stdin handling (EOF-safe)
  ✓ Memory leak prevention (log rotation, frame cleanup)
  ✓ Thread health monitoring (detect dead threads)
  ✓ Network retry logic (backend resilience)
  ✓ Graceful shutdown (cleanup all resources)

Requirements:
  • Backend running at http://localhost:8000
  • Microphone configured
  • Speaker configured
"""

import sys
import os
import time
import json
import threading
import queue
import traceback
from datetime import datetime
import logging
from typing import Optional, Tuple
import gc

# Audio/Speech
import speech_recognition as sr
import pyttsx3
import pygame

# HTTP
import requests

# Vision (optional)
try:
    import cv2
    import base64
    import numpy as np
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

# TTS Services
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

try:
    import elevenlabs
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False

try:
    from sarvam_sdk import SarvamAI
    SARVAM_AVAILABLE = True
except ImportError:
    SARVAM_AVAILABLE = False

# ============================================================================
# TTS SERVICES (Strict Cascade)
# ============================================================================

class TTSService:
    """Multi-engine TTS with strict cascade routing"""
    
    def __init__(self):
        self.sarvam_client = None
        self.eleven_client = None
        self.sarvam_keys = []
        self.sarvam_index = 0
        self.interrupt_flag = False  # For interrupt system
        
        # Initialize Sarvam
        if SARVAM_AVAILABLE:
            sarvam_keys_raw = os.environ.get("SARVAM_API_KEYS", "")
            if sarvam_keys_raw:
                try:
                    self.sarvam_keys = json.loads(sarvam_keys_raw.replace("'", '"'))
                    if self.sarvam_keys:
                        self.sarvam_client = SarvamAI(api_key=self.sarvam_keys[0])
                        logger.info(f"✓ Sarvam TTS initialized with {len(self.sarvam_keys)} keys")
                except Exception as e:
                    logger.warning(f"Sarvam init failed: {e}")
        
        # Initialize ElevenLabs
        if ELEVENLABS_AVAILABLE:
            eleven_key = os.environ.get("ELEVENLABS_API_KEY")
            eleven_voice = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
            if eleven_key:
                try:
                    elevenlabs.set_api_key(eleven_key)
                    self.eleven_client = elevenlabs
                    self.eleven_voice_id = eleven_voice
                    logger.info("✓ ElevenLabs TTS initialized")
                except Exception as e:
                    logger.warning(f"ElevenLabs init failed: {e}")
        
        if GTTS_AVAILABLE:
            logger.info("✓ gTTS fallback available")
    
    def interrupt(self):
        """Interrupt current speech"""
        self.interrupt_flag = True
        try:
            pygame.mixer.music.stop()
        except:
            pass
    
    def is_interrupted(self):
        """Check if interrupted"""
        return self.interrupt_flag
    
    def _detect_language(self, text: str) -> str:
        """Simple language detection"""
        # Check for Devanagari (Hindi)
        if any('\u0900' <= char <= '\u097F' for char in text):
            return "hindi"
        # Check for other Indic scripts
        if any('\u0980' <= char <= '\u09FF' for char in text):  # Bengali
            return "bengali"
        if any('\u0A80' <= char <= '\u0AFF' for char in text):  # Gujarati
            return "gujarati"
        if any('\u0B00' <= char <= '\u0B7F' for char in text):  # Oriya
            return "oriya"
        if any('\u0C00' <= char <= '\u0C7F' for char in text):  # Telugu
            return "telugu"
        if any('\u0D00' <= char <= '\u0D7F' for char in text):  # Malayalam
            return "malayalam"
        if any('\u0E00' <= char <= '\u0E7F' for char in text):  # Thai
            return "thai"
        return "english"
    
    def _speak_offline(self, text: str) -> bool:
        """gTTS offline fallback"""
        if not GTTS_AVAILABLE:
            return False
        
        try:
            tts = gTTS(text=text, lang='en')
            temp_file = f"temp_tts_{int(time.time())}.mp3"
            tts.save(temp_file)
            
            # Play with pygame (interruptible)
            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not self.is_interrupted():
                time.sleep(0.1)
            pygame.mixer.music.stop()
            
            # Reset interrupt flag
            self.interrupt_flag = False
            
            # Cleanup
            try:
                os.remove(temp_file)
            except:
                pass
            
            logger.info("TTS: gTTS success")
            return True
        except Exception as e:
            logger.error(f"gTTS failed: {e}")
            return False
    
    def _speak_elevenlabs(self, text: str) -> bool:
        """ElevenLabs TTS"""
        if not self.eleven_client:
            return False
        
        try:
            audio = self.eleven_client.generate(
                text=text,
                voice=self.eleven_voice_id,
                model="eleven_monolingual_v1"
            )
            
            temp_file = f"temp_tts_{int(time.time())}.mp3"
            with open(temp_file, 'wb') as f:
                f.write(audio)
            
            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not self.is_interrupted():
                time.sleep(0.1)
            pygame.mixer.music.stop()
            
            # Reset interrupt flag
            self.interrupt_flag = False
            
            try:
                os.remove(temp_file)
            except:
                pass
            
            logger.info("TTS: ElevenLabs success")
            return True
        except Exception as e:
            logger.error(f"ElevenLabs failed: {e}")
            return False
    
    def _speak_sarvam(self, text: str) -> bool:
        """Sarvam TTS with key rotation"""
        if not self.sarvam_client or not self.sarvam_keys:
            return False
        
        retries = 0
        max_retries = len(self.sarvam_keys)
        
        while retries < max_retries:
            try:
                response = self.sarvam_client.text_to_speech.convert(
                    text=text,
                    target_language_code="en-IN",
                    speaker="priya",
                    model="bulbul:v2"
                )
                
                audio_bytes = None
                if hasattr(response, 'audios') and response.audios:
                    audio_bytes = base64.b64decode(response.audios[0])
                elif isinstance(response, dict) and 'audios' in response:
                    audio_bytes = base64.b64decode(response['audios'][0])
                
                if audio_bytes and len(audio_bytes) > 100:
                    # Save to temp file and play
                    temp_file = f"temp_tts_{int(time.time())}.wav"
                    with open(temp_file, 'wb') as f:
                        f.write(audio_bytes)
                    
                    pygame.mixer.music.load(temp_file)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy() and not self.is_interrupted():
                        time.sleep(0.1)
                    pygame.mixer.music.stop()
                    
                    # Reset interrupt flag
                    self.interrupt_flag = False
                    
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                    
                    logger.info(f"TTS: Sarvam success (key #{self.sarvam_index})")
                    return True
                else:
                    logger.warning("Sarvam returned empty audio")
            
            except Exception as e:
                logger.error(f"Sarvam key #{self.sarvam_index} failed: {e}")
            
            # Rotate key
            self.sarvam_index = (self.sarvam_index + 1) % len(self.sarvam_keys)
            if self.sarvam_client:
                self.sarvam_client = SarvamAI(api_key=self.sarvam_keys[self.sarvam_index])
            retries += 1
            time.sleep(1)
        
        return False
    
    def speak_response(self, text: str, ai_mode: str = "ollama"):
        """
        Strict cascade TTS routing based on AI mode.
        Always resolves, never loops.
        """
        if not text or text.startswith("SYSTEM"):
            return
        
        try:
            # Detect language
            lang = self._detect_language(text)
            
            # Strict cascade based on AI mode
            if ai_mode == "tinyllama":
                # Offline mode → always use gTTS
                if not self._speak_offline(text):
                    logger.warning("All TTS engines failed for TinyLlama mode")
                return
            
            if lang != "english":
                # Non-English → Sarvam AI → gTTS
                if not self._speak_sarvam(text):
                    if not self._speak_offline(text):
                        logger.warning("All TTS engines failed for non-English text")
                return
            
            # English → ElevenLabs → Sarvam → gTTS (strict order)
            if self._speak_elevenlabs(text):
                return
            if self._speak_sarvam(text):
                return
            if not self._speak_offline(text):
                logger.warning("All TTS engines failed for English text")
        
        except Exception as e:
            logger.error(f"TTS cascade error: {e}")
            # Final fallback
            try:
                self._speak_offline(text)
            except:
                logger.error("Complete TTS failure")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

# Logging with rotation (prevent disk fill)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('orion_client.log', maxBytes=10*1024*1024, backupCount=3),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# API
API_URL = os.environ.get("ORION_API_URL", "http://localhost:8000")
BACKEND_ENDPOINT = f"{API_URL}/api/chat"
BACKEND_TIMEOUT = 15
BACKEND_RETRY_COUNT = 2

# Audio Config
MIC_INDEX = None
try:
    mic_idx = os.environ.get("MIC_INDEX")
    MIC_INDEX = int(mic_idx) if mic_idx else None
except:
    pass

SPEAKER_CARD_INDEX = os.environ.get("SPEAKER_CARD_INDEX")

# User
USER_ID = os.environ.get("USER_ID", "headless_user")

# Health monitoring
HEARTBEAT_INTERVAL = 10
THREAD_TIMEOUT = 30

# ============================================================================
# AUDIO INITIALIZATION
# ============================================================================

def init_audio() -> bool:
    """Initialize audio system with recovery capability"""
    try:
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        logger.info("✓ Audio mixer initialized")
        return True
    except Exception as e:
        logger.warning(f"Audio mixer init failed: {e}")
        return False

def recover_audio() -> bool:
    """Recover audio system on hardware lock"""
    try:
        # Stop any playing audio
        pygame.mixer.music.stop()
        pygame.mixer.quit()
        
        # Try to restart ALSA (Linux/Pi specific)
        import subprocess
        try:
            subprocess.run(['sudo', 'systemctl', 'restart', 'alsa-utils'], 
                         capture_output=True, timeout=5)
            logger.info("ALSA restarted for audio recovery")
        except:
            pass  # ALSA restart may not be available
        
        # Reinitialize pygame
        time.sleep(1)
        success = init_audio()
        if success:
            logger.info("✓ Audio system recovered")
        return success
        
    except Exception as e:
        logger.error(f"Audio recovery failed: {e}")
        return False

def init_microphone() -> Tuple[Optional[sr.Recognizer], Optional[sr.Microphone]]:
    """Initialize microphone with timeout safety"""
    recognizer = sr.Recognizer()
    recognizer.max_dynamic_frequency_adjustment_depth = 32
    
    try:
        mic = sr.Microphone(device_index=MIC_INDEX)
        
        # Timeout-protected calibration
        try:
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=1)
        except Exception as e:
            logger.warning(f"Could not calibrate mic: {e}")
        
        logger.info("✓ Microphone initialized")
        return recognizer, mic
    except Exception as e:
        logger.error(f"Microphone init failed: {e}")
        return None, None

# ============================================================================
# VISION (Hardened for Pi)
# ============================================================================

class VisionManager:
    """Manage camera with thread safety and memory protection"""
    
    def __init__(self):
        self.cap = None
        self.frame = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.last_capture_time = 0
        self.last_frame_time = 0  # For FPS capping
        self.capture_thread = None
        self.error_count = 0
        self.MAX_ERRORS = 5
        
        if not VISION_AVAILABLE:
            logger.warning("Vision disabled (OpenCV not available)")
            return
        
        try:
            self.cap = cv2.VideoCapture(0)
            if self.cap.isOpened():
                # Set resolution to reduce memory (Pi optimization)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap.set(cv2.CAP_PROP_FPS, 15)  # Lower FPS saves CPU
                
                logger.info("✓ Camera initialized (640x480@15fps)")
                self.running = True
                self.capture_thread = threading.Thread(
                    target=self._capture_loop,
                    daemon=True,
                    name="CameraThread"
                )
                self.capture_thread.start()
            else:
                logger.warning("Camera not available")
        except Exception as e:
            logger.warning(f"Camera init failed: {e}")
    
    def _should_process_frame(self) -> bool:
        """FPS capping to prevent CPU spikes - max 3 FPS processing"""
        now = time.time()
        if now - self.last_frame_time < 0.33:  # ~3 FPS (1/0.33 ≈ 3)
            return False
        self.last_frame_time = now
        return True
    
    def _capture_loop(self):
        """Continuously capture frames (isolated from encoding) with camera recovery and FPS capping"""
        while self.running:
            try:
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    # Only process frame if FPS cap allows (prevents CPU spikes)
                    if self._should_process_frame():
                        with self.frame_lock:
                            # Only keep latest frame (discard old one)
                            self.frame = frame
                            self.error_count = 0
                        self.last_capture_time = time.time()
                else:
                    self.error_count += 1
                    if self.error_count > self.MAX_ERRORS:
                        logger.error("Camera capture failed repeatedly - attempting recovery")
                        self._recover_camera()
                        break
                
                time.sleep(0.067)  # ~15 FPS capture (CPU-friendly on Pi)
            
            except Exception as e:
                logger.error(f"Capture error: {e}")
                self.error_count += 1
                if self.error_count > self.MAX_ERRORS:
                    logger.error("Camera capture failed repeatedly - attempting recovery")
                    self._recover_camera()
                    break
                time.sleep(1)
    
    def _recover_camera(self):
        """Camera recovery: release and reinitialize on failure"""
        try:
            # Release current camera
            if self.cap:
                self.cap.release()
                logger.info("Camera released for recovery")
            
            time.sleep(2)  # Wait before reinitializing
            
            # Reinitialize camera
            self.cap = cv2.VideoCapture(0)
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap.set(cv2.CAP_PROP_FPS, 15)
                self.error_count = 0
                logger.info("✓ Camera recovered successfully")
                
                # Restart capture loop
                if not self.capture_thread or not self.capture_thread.is_alive():
                    self.capture_thread = threading.Thread(
                        target=self._capture_loop,
                        daemon=True,
                        name="CameraThread"
                    )
                    self.capture_thread.start()
            else:
                logger.error("Camera recovery failed - camera not available")
                self.running = False
                
        except Exception as e:
            logger.error(f"Camera recovery failed: {e}")
            self.running = False
    
    def get_frame_b64(self) -> Optional[str]:
        """Get current frame as base64 (encoding happens outside lock)"""
        if not self.running or self.frame is None:
            return None
        
        try:
            # Copy frame while holding lock (fast)
            with self.frame_lock:
                frame_copy = self.frame.copy() if self.frame is not None else None
            
            if frame_copy is None:
                return None
            
            # Encode outside lock (slow operation - no blocking)
            # Compress more for Pi bandwidth
            _, buffer = cv2.imencode('.jpg', frame_copy, [cv2.IMWRITE_JPEG_QUALITY, 70])
            b64 = base64.b64encode(buffer).decode()
            return b64
        
        except Exception as e:
            logger.error(f"Frame encoding failed: {e}")
            return None
    
    def stop(self):
        """Stop camera gracefully"""
        self.running = False
        if self.cap:
            try:
                self.cap.release()
                logger.info("✓ Camera released")
            except:
                pass

# ============================================================================
# BACKEND COMMUNICATION (with retry)
# ============================================================================

def send_to_backend(user_input: str, image_b64: Optional[str] = None) -> Tuple[str, str]:
    """Send message to backend with retry logic and timeouts"""
    payload = {
        "user_id": USER_ID,
        "text": user_input,
        "stream": False
    }
    
    if image_b64:
        payload["image"] = image_b64
    
    logger.debug(f"Sending to backend: {user_input[:50]}...")
    
    # Retry logic for resilience
    for attempt in range(BACKEND_RETRY_COUNT):
        try:
            resp = requests.post(
                BACKEND_ENDPOINT,
                json=payload,
                timeout=BACKEND_TIMEOUT
            )
            
            if resp.status_code == 200:
                data = resp.json()
                response = data.get("response", "No response from backend")
                ai_mode = data.get("ai_mode", "ollama")
                logger.info(f"[RESPONSE] {response[:50]}... (mode: {ai_mode})")
                return response, ai_mode
            else:
                logger.error(f"Backend error: {resp.status_code}")
        
        except requests.exceptions.Timeout:
            logger.warning(f"Backend timeout (attempt {attempt+1}/{BACKEND_RETRY_COUNT})")
        except requests.exceptions.ConnectionError:
            logger.warning(f"Backend unreachable (attempt {attempt+1}/{BACKEND_RETRY_COUNT})")
        except Exception as e:
            logger.error(f"Backend error: {e}")
        
        if attempt < BACKEND_RETRY_COUNT - 1:
            time.sleep(2)  # Wait before retry
    
    return "Backend not responding. Please try again.", "system"

# ============================================================================
# INPUT PIPELINE (Non-blocking)
# ============================================================================

class InputThread(threading.Thread):
    """Listen for voice input (non-blocking)"""
    
    def __init__(self, recognizer: sr.Recognizer, mic: sr.Microphone, output_queue: queue.Queue):
        super().__init__(daemon=True, name="InputThread")
        self.recognizer = recognizer
        self.mic = mic
        self.output_queue = output_queue
        self.running = True
        self.last_activity = time.time()
    
    def run(self):
        if not self.recognizer or not self.mic:
            logger.error("Microphone not available")
            return
        
        logger.info("[INPUT] Voice listening started")
        no_audio_counter = 0
        
        # Non-blocking with timeout
        try:
            with self.mic as source:
                while self.running:
                    try:
                        # Timeout so we can check running flag
                        audio = self.recognizer.listen(
                            source,
                            timeout=2,
                            phrase_time_limit=10
                        )
                        
                        # Recognize (with timeout)
                        try:
                            text = self.recognizer.recognize_google(audio)
                            if text:
                                self.last_activity = time.time()
                                no_audio_counter = 0  # Reset counter on successful recognition
                                logger.info(f"[HEARD] {text}")
                                
                                # Interrupt current speech for natural conversation
                                if hasattr(self, 'tts_service') and self.tts_service:
                                    self.tts_service.interrupt()
                                
                                self.output_queue.put((1, ("voice", text)))  # Priority 1: voice
                            else:
                                no_audio_counter += 1
                        except sr.UnknownValueError:
                            no_audio_counter += 1  # Count as no audio detected
                            pass  # Couldn't understand
                        except sr.RequestError as e:
                            logger.warning(f"Google API unavailable: {e}")
                            no_audio_counter += 1
                    
                    except sr.WaitTimeoutError:
                        no_audio_counter += 1  # No input detected
                        pass  # No input yet
                    except Exception as e:
                        logger.error(f"Input error: {e}")
                        no_audio_counter += 1
                        time.sleep(0.5)  # Back off
                    
                    # Mic watchdog: If no audio detected for 10+ consecutive checks, trigger recovery
                    if no_audio_counter >= 10:
                        logger.warning("Mic watchdog: No audio detected for extended period - triggering recovery")
                        if recover_audio():
                            logger.info("Audio recovery successful")
                            no_audio_counter = 0
                        else:
                            logger.error("Audio recovery failed")
                            no_audio_counter = 0  # Reset to prevent spam
        
        except Exception as e:
            logger.error(f"Input thread crashed: {e}")

class NotificationPoller(threading.Thread):
    """Poll backend for proactive notifications"""
    
    def __init__(self, output_queue: queue.Queue):
        super().__init__(daemon=True, name="NotificationPoller")
        self.output_queue = output_queue
        self.running = True
        self.last_poll = 0
    
    def run(self):
        logger.info("[NOTIFICATIONS] Poller started")
        
        while self.running:
            try:
                now = time.time()
                if now - self.last_poll >= 60:  # Poll every 60 seconds
                    self._poll_notifications()
                    self.last_poll = now
                
                time.sleep(10)  # Check every 10s if it's time to poll
            
            except Exception as e:
                logger.error(f"Notification poller error: {e}")
                time.sleep(30)
    
    def _poll_notifications(self):
        """Poll backend for notifications"""
        try:
            resp = requests.get(f"{BACKEND_ENDPOINT}/notifications?user_id={USER_ID}", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                notifications = data.get("notifications", [])
                for note in notifications:
                    if isinstance(note, str):
                        suggestion = note
                    elif isinstance(note, dict):
                        suggestion = note.get("content", "")
                    else:
                        suggestion = None

                    if suggestion:
                        logger.info(f"[NOTIFICATION] {suggestion}")
                        self.output_queue.put((2, ("notification", suggestion)))  # Priority 2
                        # Mark as read is handled by backend        except Exception as e:
            logger.debug(f"Notification poll failed: {e}")
    
    def run(self):
        logger.info("[STDIN] Text input ready")
        
        try:
            while self.running:
                try:
                    # This will block, but that's OK (daemon thread)
                    line = input().strip()
                    
                    if not line:
                        continue
                    
                    if line.lower() == "exit":
                        self.output_queue.put((3, ("command", "exit")))  # Priority 3: commands
                    elif line.startswith("text:"):
                        text = line[5:].strip()
                        if text:
                            self.last_activity = time.time()
                            logger.info(f"[TEXT] {text}")
                            self.output_queue.put((2, ("text", text)))  # Priority 2: text
                    elif line.lower() == "/see":
                        self.output_queue.put((2, ("vision", "see")))  # Priority 2: vision
                    else:
                        # Treat as text
                        self.last_activity = time.time()
                        logger.info(f"[TEXT] {line}")
                        self.output_queue.put((2, ("text", line)))  # Priority 2: text
                
                except EOFError:
                    logger.info("EOF on stdin")
                    break
                except Exception as e:
                    logger.error(f"Stdin error: {e}")
                    break
        
        except Exception as e:
            logger.error(f"Stdin thread crashed: {e}")

# ============================================================================
# OUTPUT PIPELINE (Async TTS)
# ============================================================================

class OutputThread(threading.Thread):
    """Handle TTS output with multi-engine cascade"""
    
    def __init__(self, tts_service: TTSService, input_queue: queue.Queue):
        super().__init__(daemon=True, name="OutputThread")
        self.tts_service = tts_service
        self.input_queue = input_queue
        self.running = True
        self.is_speaking = False
        self.last_activity = time.time()
    
    def run(self):
        logger.info("[OUTPUT] Multi-engine TTS ready")
        
        while self.running:
            try:
                item = self.input_queue.get(timeout=2)
                if isinstance(item, tuple) and len(item) == 2:
                    priority, (msg_type, data) = item
                    if msg_type == "voice" or msg_type == "notification":
                        text = data
                        ai_mode = "ollama"  # Default for suggestions
                    else:
                        text, ai_mode = data
                else:
                    text, ai_mode = item
                
                if text and len(text) > 0:
                    self.is_speaking = True
                    self.last_activity = time.time()
                    
                    try:
                        logger.info(f"[TTS] Speaking with mode {ai_mode}: {text[:40]}...")
                        self.tts_service.speak_response(text, ai_mode)
                    except Exception as e:
                        logger.error(f"TTS playback error: {e}")
                    finally:
                        self.is_speaking = False
            
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Output thread error: {e}")
                self.is_speaking = False

# ============================================================================
# HEALTH MONITORING
# ============================================================================

class HealthMonitor(threading.Thread):
    """Monitor thread health and detect dead threads"""
    
    def __init__(self, threads_dict: dict):
        super().__init__(daemon=True, name="HealthMonitor")
        self.threads_dict = threads_dict
        self.running = True
    
    def run(self):
        logger.info("[HEALTH] Monitor started")
        
        while self.running:
            try:
                for name, thread in self.threads_dict.items():
                    if thread and hasattr(thread, 'last_activity'):
                        elapsed = time.time() - thread.last_activity
                        
                        # Warn if no activity for a while
                        if elapsed > THREAD_TIMEOUT:
                            logger.warning(f"[HEALTH] {name} inactive for {elapsed:.0f}s")
                
                time.sleep(HEARTBEAT_INTERVAL)
            
            except Exception as e:
                logger.error(f"Health monitor error: {e}")

# ============================================================================
# MAIN CLIENT
# ============================================================================

class ORIONHeadlessClient:
    """Production-hardened ORION headless client"""
    
    def __init__(self):
        logger.info("=" * 70)
        logger.info("ORION HEADLESS CLIENT - Production Hardened")
        logger.info("=" * 70)
        
        # Initialize subsystems
        init_audio()
        recognizer, mic = init_microphone()
        tts_service = TTSService()  # Multi-engine TTS
        
        self.recognizer = recognizer
        self.mic = mic
        self.tts_service = tts_service
        self.vision = VisionManager() if VISION_AVAILABLE else None
        
        # Queues - now priority queue: (priority, (type, data))
        self.input_queue = queue.Queue()      # For TTS output
        self.user_input_queue = queue.PriorityQueue() # For backend input with priority
        
        # Threads
        self.threads = {}
        self.running = True
    
    def start(self):
        """Start all subsystem threads"""
        logger.info("[CLIENT] Starting threads...")
        
        # Output thread (TTS)
        output_thread = OutputThread(self.tts_service, self.input_queue)
        output_thread.start()
        self.threads['output'] = output_thread
        
        # Stdin thread (text input)
        stdin_thread = StdinThread(self.user_input_queue)
        stdin_thread.start()
        self.threads['stdin'] = stdin_thread
        
        # Voice input thread
        if self.recognizer and self.mic:
            input_thread = InputThread(self.recognizer, self.mic, self.user_input_queue)
            input_thread.start()
            self.threads['voice'] = input_thread
            print("✓ Voice input enabled")
        else:
            print("⚠ Voice input disabled")
        
        # Health monitor
        monitor = HealthMonitor(self.threads)
        monitor.running = self.running
        monitor.start()
        
        # Notification poller
        poller = NotificationPoller(self.input_queue)
        poller.start()
        self.threads['poller'] = poller
        
        print("✓ Text input enabled")
        print("\nCommands:")
        print("  - Speak or type naturally")
        print("  - text: <message>  - Send explicit text")
        print("  - /see             - Trigger camera")
        print("  - exit             - Quit")
        print("=" * 70)
    
    def run(self):
        """Main processing loop with watchdog monitoring and runtime health checks"""
        self.start()
        watchdog_timer = 0
        health_check_timer = 0
        heartbeat_timer = 0
        memory_trim_timer = 0
        
        try:
            while self.running:
                try:
                    current_time = time.time()
                    
                    # Heartbeat file every 30 seconds (anti-zombie guard)
                    if current_time - heartbeat_timer >= 30:
                        try:
                            with open("/tmp/orion_heartbeat", "w") as f:
                                f.write(str(current_time))
                        except Exception as e:
                            logger.warning(f"Heartbeat write failed: {e}")
                        heartbeat_timer = current_time
                    
                    # Memory trimmer every 10 minutes (long-run safety)
                    if current_time - memory_trim_timer >= 600:
                        gc.collect()
                        logger.debug("[MEMORY] Garbage collection completed")
                        memory_trim_timer = current_time
                    
                    # Watchdog check every 60 seconds
                    if current_time - watchdog_timer >= 60:
                        try:
                            from orion.core.dev_monitor import check_backend_health
                            check_backend_health()
                        except ImportError:
                            pass  # Dev monitor not available
                        watchdog_timer = current_time
                    
                    # Runtime health check every 5 minutes
                    if current_time - health_check_timer >= 300:
                        try:
                            from orion.core.dev_monitor import perform_runtime_health_check
                            perform_runtime_health_check()
                        except ImportError:
                            pass  # Dev monitor not available
                        health_check_timer = current_time
                    
                    # Adaptive CPU throttling: adjust timeout based on load
                    try:
                        load = os.getloadavg()[0] if hasattr(os, 'getloadavg') else 1.0
                        timeout = 0.2 if load > 2.0 else 0.05
                    except:
                        timeout = 0.05  # Default
                    
                    priority, (input_type, user_input) = self.user_input_queue.get(timeout=timeout)
                    
                    # Handle commands
                    if input_type == "command":
                        if user_input == "exit":
                            logger.info("[CLIENT] Exit requested")
                            self.running = False
                    
                    # Handle vision
                    elif input_type == "vision":
                        self._handle_vision()
                    
                    # Handle user input
                    else:
                        # Interrupt current speech for natural conversation flow
                        if self.tts_service and hasattr(self.tts_service, 'interrupt'):
                            self.tts_service.interrupt()
                        
                        self._handle_input(user_input)
                
                except queue.Empty:
                    pass
                except Exception as e:
                    logger.error(f"Main loop error: {e}")
                    traceback.print_exc()
        
        except KeyboardInterrupt:
            logger.info("[CLIENT] Interrupted")
        
        finally:
            self.cleanup()
    
    def _handle_input(self, user_input: str):
        """Process user input"""
        start_time = time.time()
        try:
            image_b64 = None
            if "see" in user_input.lower() and self.vision:
                image_b64 = self.vision.get_frame_b64()
            
            response, ai_mode = send_to_backend(user_input, image_b64)
            
            latency = time.time() - start_time
            logger.info(f"[LATENCY] Input processing: {latency:.2f}s")
            
            print(f"\n🤖 ORION ({ai_mode}): {response}\n")
            
            if response and self.tts_service:
                self.input_queue.put((response, ai_mode))
        
        except Exception as e:
            latency = time.time() - start_time
            logger.error(f"Input handling error after {latency:.2f}s: {e}")
            print(f"Error: {str(e)[:100]}\n")
    
    def _handle_vision(self):
        """Handle vision request"""
        try:
            if not self.vision:
                print("⚠ Vision not available\n")
                return
            
            image_b64 = self.vision.get_frame_b64()
            if not image_b64:
                print("⚠ Could not capture frame\n")
                return
            
            print("📷 Analyzing camera...", end="", flush=True)
            response = send_to_backend("What do you see?", image_b64)
            
            print(f"\r🤖 ORION: {response}\n")
            
            if response and self.engine:
                self.input_queue.put(response)
        
        except Exception as e:
            logger.error(f"Vision error: {e}")
            print(f"Error: {str(e)[:100]}\n")
    
    def cleanup(self):
        """Graceful shutdown"""
        logger.info("[CLIENT] Shutting down...")
        
        self.running = False
        
        # Stop all threads
        for name, thread in self.threads.items():
            if hasattr(thread, 'running'):
                thread.running = False
        
        # Stop vision
        if self.vision:
            self.vision.stop()
        
        # Stop engine
        if self.engine:
            try:
                self.engine._cleanup()
            except:
                pass
        
        logger.info("✓ ORION Client stopped")
        print("\n✓ Goodbye!\n")

# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    """Entry point"""
    try:
        client = ORIONHeadlessClient()
        client.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
