"""
ORION Executive Dashboard — gui_client.py
=========================================
Solidified client with:
  • Sarvam AI TTS (Simrun voice) with 3-key rotation
  • Portable face-encoding path (data/encoded_file.p)
  • Clean, premium HUD with live status feedback
  • Sentence-split streaming for low-latency speech
"""

import sys, os, cv2, time, threading, requests, queue, psutil, pickle, json
import numpy as np, face_recognition, pyttsx3, speech_recognition as sr
import pygame, tempfile, re, base64

from datetime import datetime
from dotenv import load_dotenv

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QTextEdit, QFrame, QProgressBar,
    QGraphicsDropShadowEffect, QLineEdit
)
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QFont, QColor

# ─────────────────────────────────────────────
# 1. CONFIGURATION
# ─────────────────────────────────────────────
# Load .env from project root (one level up from /client)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

API_URL = os.environ.get("ORION_API_URL", "http://localhost:8000")
ENCODINGS_FILE = os.path.join(PROJECT_ROOT, "data", "encoded_file.p")
# Stricter threshold = fewer false matches. 0.42 works well for webcam at close range.
# Lower = stricter. If too many UNKNOWN, increase slightly. If wrong person, decrease.
MATCH_THRESHOLD = float(os.environ.get("MATCH_THRESHOLD", "0.42"))


def parse_env_list(key):
    """Parse a JSON-style list from an environment variable."""
    raw = os.environ.get(key, "")
    if not raw:
        return []
    try:
        return json.loads(raw.replace("'", '"'))
    except Exception:
        return [raw] if raw else []

SARVAM_API_KEYS = parse_env_list("SARVAM_API_KEYS")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
print(f"[INIT] Loaded {len(SARVAM_API_KEYS)} Sarvam keys | ElevenLabs key: {'SET (' + ELEVENLABS_API_KEY[:8] + '...)' if ELEVENLABS_API_KEY else 'NOT SET'} | Voice: {ELEVENLABS_VOICE_ID}")

# Speaker Card selection (Pi-Specific mainly)
SPEAKER_CARD_INDEX = os.environ.get("SPEAKER_CARD_INDEX", None)
if SPEAKER_CARD_INDEX and os.name == 'posix':
    # On Linux, SDL_AUDIODEV is the standard for selecting a specific card
    os.environ["SDL_AUDIODEV"] = f"plughw:{SPEAKER_CARD_INDEX},0"

# Initialise PyGame Mixer
try:
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
except Exception as e:
    print(f"[AUDIO INIT ERR] {e}")

PRIORITY_RESPONSE = 1
PRIORITY_ALERT    = 2
PRIORITY_IDLE     = 3

def split_sentences(text):
    """Split text into sentences for faster TTS streaming."""
    return [s.strip() for s in re.split(r'(?<=[.!?\n]) +', text) if s.strip()]


# ─────────────────────────────────────────────
# 2. THREADS
# ─────────────────────────────────────────────

class VoiceThread(QThread):
    """Microphone listener — emits recognised text."""
    heard_text     = pyqtSignal(str)
    status_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.recognizer = sr.Recognizer()
        
        # Robust Mic selection: Use .env (MIC_INDEX) or default to None
        mic_idx = os.environ.get("MIC_INDEX")
        try:
            mic_idx = int(mic_idx) if mic_idx is not None else None
        except:
            mic_idx = None
            
        print(f"[ORION] Initialising microphone on index: {mic_idx if mic_idx is not None else 'Default'}")
        self.mic = sr.Microphone(device_index=mic_idx)
        self.running = True
        self.muted = False  # set True when ORION is speaking to prevent self-feedback

    def run(self):
        try:
            with self.mic as source:
                print("[ORION] Calibrating microphone …")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                print("[ORION] Microphone ready.")
                while self.running:
                    try:
                        # Don't listen while ORION is speaking — prevents self-feedback
                        if self.muted:
                            time.sleep(0.1)
                            continue
                        self.status_changed.emit("LISTENING")
                        audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=10)
                        self.status_changed.emit("PROCESSING")
                        text = self.recognizer.recognize_google(audio)
                        if text:
                            print(f"[HEARD] {text}")
                            self.heard_text.emit(text)
                    except sr.WaitTimeoutError:
                        pass
                    except sr.UnknownValueError:
                        pass
                    except Exception as e:
                        print(f"[MIC ERR] {e}")
                    finally:
                        self.status_changed.emit("IDLE")
        except Exception as e:
            print(f"[MIC CRITICAL ERR] Could not access microphone: {e}")
            self.status_changed.emit("MIC_ERROR")
            # Ensure the thread stays alive or exits gracefully
            time.sleep(5)


class SpeakerThread(QThread):
    """TTS engine — edge-tts (Microsoft neural voices, free, natural sounding).
    Falls back to pyttsx3 if no internet."""
    status_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.edge_voice = "en-IN-NeerjaNeural"  # natural Indian English female
        self.edge_rate  = "+0%"

        # pyttsx3 hard fallback (offline)
        self.offline_engine = pyttsx3.init()
        self.offline_engine.setProperty('rate', 175)
        voices = self.offline_engine.getProperty('voices')
        for v in voices:
            if any(n in v.name for n in ["Zira", "Hazel", "Catherine", "Female"]):
                self.offline_engine.setProperty('voice', v.id)
                break

        self.queue   = queue.PriorityQueue()
        self.running = True
        print(f"[TTS] edge-tts ready. Voice: {self.edge_voice}")

    def say(self, text, priority=PRIORITY_RESPONSE):
        if not text or text.startswith("SYSTEM"):
            return
        self.queue.put((priority, text))

    def run(self):
        while self.running:
            try:
                priority, text = self.queue.get(timeout=1)
            except queue.Empty:
                continue
            if not text.strip():
                continue
            self.status_changed.emit("SPEAKING")
            if not self._speak_edge(text):
                self._speak_offline(text)
            self.status_changed.emit("IDLE")

    def _speak_edge(self, text) -> bool:
        """Synthesize with edge-tts and play via pygame."""
        try:
            import edge_tts, asyncio

            async def _synth():
                communicate = edge_tts.Communicate(text, self.edge_voice, rate=self.edge_rate)
                tmp = tempfile.mktemp(suffix=".mp3")
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        with open(tmp, "ab") as f:
                            f.write(chunk["data"])
                return tmp

            loop = asyncio.new_event_loop()
            tmp_path = loop.run_until_complete(_synth())
            loop.close()

            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) < 100:
                return False

            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            pygame.mixer.music.unload()
            try: os.remove(tmp_path)
            except: pass
            return True

        except Exception as e:
            print(f"[TTS edge ERR] {e}")
            return False

    def _speak_offline(self, text):
        """pyttsx3 fallback when edge-tts fails (no internet)."""
        try:
            self.offline_engine.say(text)
            self.offline_engine.runAndWait()
        except Exception as e:
            print(f"[TTS offline ERR] {e}")


class OrionWebSocketThread(QThread):
    """
    Persistent WebSocket connection to Pi 4 Brain.
    Replaces BackendThread (SSE) + NotificationThread (polling).

    Single connection handles everything:
      • Sends chat messages → receives streaming tokens
      • Sends face detection events → receives greetings
      • Receives proactive alerts (meetings, battery) pushed by Pi 4
      • Sends mood updates
      • Sends interrupt when user speaks mid-response

    Signals:
      token_received(str)      — individual AI token (for live TTS)
      response_received(str)   — full response when streaming completes
      greeting_received(str)   — greeting after face detection
      alert_received(str)      — proactive alert pushed from Pi 4
      status_changed(str)      — connection status: CONNECTED / RECONNECTING / OFFLINE
      error_occurred(str)      — error message
    """
    token_received    = pyqtSignal(str)
    response_received = pyqtSignal(str)
    greeting_received = pyqtSignal(str)
    alert_received    = pyqtSignal(str)
    status_changed    = pyqtSignal(str)
    error_occurred    = pyqtSignal(str)

    def __init__(self, user_id: str):
        super().__init__()
        self.user_id = user_id
        self.running = True
        self._ws = None
        self._send_queue = queue.Queue()
        # Derive WS URL from API_URL (http→ws, https→wss)
        self._ws_url = API_URL.replace("http://", "ws://").replace("https://", "wss://")

    # ── Public send API ──

    def send_chat(self, message: str):
        """Queue a chat message to be sent to Pi 4."""
        self._send_queue.put({
            "type": "chat",
            "user_id": self.user_id,
            "message": message
        })

    def send_face(self, detected_user: str):
        """Notify Pi 4 that a face was detected."""
        self._send_queue.put({
            "type": "face",
            "user_id": detected_user,
            "action": "detected"
        })

    def send_mood(self, mood: str):
        """Send detected mood to Pi 4."""
        self._send_queue.put({"type": "mood", "mood": mood})

    def send_interrupt(self):
        """Tell Pi 4 to stop the current AI stream."""
        self._send_queue.put({"type": "interrupt"})

    def update_user(self, user_id: str):
        """Update the active user ID (called after face recognition)."""
        self.user_id = user_id

    # ── Thread main loop ──

    def run(self):
        """
        Maintains a persistent WebSocket connection with automatic reconnect.
        Uses websocket-client library (sync, runs fine in QThread).
        """
        try:
            import websocket as ws_lib
        except ImportError:
            self.error_occurred.emit("websocket-client not installed. Run: pip install websocket-client")
            return

        RECONNECT_DELAY = 3   # seconds between reconnect attempts
        MAX_DELAY = 30

        delay = RECONNECT_DELAY

        while self.running:
            ws_url = f"{self._ws_url}/ws/{self.user_id}"
            print(f"[WS] Connecting to {ws_url}...")
            self.status_changed.emit("RECONNECTING")

            try:
                self._ws = ws_lib.WebSocketApp(
                    ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                # run_forever blocks until connection drops
                self._ws.run_forever(ping_interval=20, ping_timeout=10)

            except Exception as e:
                print(f"[WS] Connection error: {e}")

            if not self.running:
                break

            # Reconnect with backoff
            print(f"[WS] Reconnecting in {delay}s...")
            time.sleep(delay)
            delay = min(delay * 2, MAX_DELAY)

    def _on_open(self, ws):
        self.status_changed.emit("CONNECTED")
        print("[WS] Connected to Pi 4 Brain.")
        # Start sender loop in a daemon thread
        threading.Thread(target=self._sender_loop, args=(ws,), daemon=True).start()

    def _on_message(self, ws, raw):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type", "")

        if msg_type == "ack":
            # Immediate acknowledgment — speak it right away
            self.token_received.emit(msg.get("text", ""))

        elif msg_type == "token":
            self.token_received.emit(msg.get("text", ""))

        elif msg_type == "done":
            full = msg.get("full_response", "")
            if full:
                self.response_received.emit(full)

        elif msg_type == "greeting":
            self.greeting_received.emit(msg.get("text", ""))

        elif msg_type == "alert":
            self.alert_received.emit(msg.get("text", ""))

        elif msg_type == "error":
            self.error_occurred.emit(msg.get("message", "Unknown error"))

        elif msg_type == "interrupted":
            print("[WS] Stream interrupted by server.")

        elif msg_type == "pong":
            pass  # keepalive reply

    def _on_error(self, ws, error):
        print(f"[WS] Error: {error}")
        self.status_changed.emit("OFFLINE")

    def _on_close(self, ws, code, msg):
        print(f"[WS] Closed (code={code})")
        self.status_changed.emit("OFFLINE")

    def _sender_loop(self, ws):
        """Drain the send queue and push messages to the WebSocket."""
        while self.running:
            try:
                msg = self._send_queue.get(timeout=0.5)
                ws.send(json.dumps(msg))
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[WS] Send error: {e}")
                break

    def stop(self):
        self.running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass


class NotificationThread(QThread):
    """
    HTTP fallback for notifications — only used when WebSocket is unavailable.
    OrionWebSocketThread handles this automatically when WS is connected.
    """
    new_notification = pyqtSignal(str)

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
        self.running = True

    def run(self):
        while self.running:
            try:
                res = requests.get(
                    f"{API_URL}/notifications",
                    params={"user_id": self.user_id},
                    timeout=3
                )
                if res.status_code == 200:
                    for alert in res.json().get("notifications", []):
                        self.new_notification.emit(alert)
            except Exception:
                pass
            time.sleep(10)  # Less frequent since WS handles real-time alerts


class LogTailThread(QThread):
    """Tails the orion.log file and emits new lines in real-time."""
    new_log_line = pyqtSignal(str)

    def __init__(self, log_path):
        super().__init__()
        self.log_path = log_path
        self.running = True

    def run(self):
        # Wait for file to exist
        while not os.path.exists(self.log_path) and self.running:
            time.sleep(1)
            
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, 2)
                last_pos = f.tell()
                
                while self.running:
                    # Check for rotation: if file size < last_pos, it was rotated
                    if os.path.exists(self.log_path) and os.path.getsize(self.log_path) < last_pos:
                        print(f"[LOG] File {self.log_path} rotated. Re-opening.")
                        f.close()
                        f = open(self.log_path, "r", encoding="utf-8", errors="ignore")
                        last_pos = 0 # Start from beginning of new file
                    
                    line = f.readline()
                    if not line:
                        time.sleep(0.5)
                        last_pos = f.tell() # Update pos even if no line to track shrinkage
                        continue
                    
                    # Cleaning logs (ANSI codes, prefixes)
                    clean_line = re.sub(r'\u001b\[.*?[mK]', '', line).strip()
                    if clean_line:
                        self.new_log_line.emit(clean_line)
                    last_pos = f.tell()
        except Exception as e:
            print(f"[LOG TAIL ERR] {e}")


class FaceRecognitionThread(QThread):
    """Offloads heavy face detection/encoding to avoid UI stuttering."""
    faces_detected = pyqtSignal(list, list) # (locations, names)

    def __init__(self, encodings, names):
        super().__init__()
        self.known_encodings = encodings
        self.known_names = names
        self.frame_queue = queue.Queue(maxsize=1)
        self.running = True
        # Allow choosing between 'hog' (fast/Pi) and 'cnn' (accurate/PC)
        self.model = os.environ.get("FACE_MODEL", "hog")

    def process_frame(self, frame):
        if self.frame_queue.full():
            try: self.frame_queue.get_nowait()
            except: pass
        self.frame_queue.put(frame)

    def run(self):
        print(f"[FACE] Thread started using model: {self.model}")
        while self.running:
            try:
                frame = self.frame_queue.get(timeout=0.5)
                # Double resize for high accuracy (0.5x instead of 0.25x)
                small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                
                # OPTIONAL: Enhance contrast on live frame to match training
                gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
                clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8,8))
                enhanced_gray = clahe.apply(gray)
                rgb_enhanced = cv2.merge([enhanced_gray, enhanced_gray, enhanced_gray])

                # Detect / Encode
                # Use rgb_enhanced for detections as well for consistent results
                locs = face_recognition.face_locations(rgb_enhanced, model=self.model)
                # Use num_jitters=2 for live encoding to handle slight motion blur
                encs = face_recognition.face_encodings(rgb_enhanced, locs, num_jitters=2)
                
                detected_names = []
                for enc in encs:
                    # Logic: Get distances to ALL known faces
                    face_distances = face_recognition.face_distance(self.known_encodings, enc)
                    
                    name = "UNKNOWN"
                    if len(face_distances) > 0:
                        best_match_index = np.argmin(face_distances)
                        # Check if the best match is actually below the threshold
                        if face_distances[best_match_index] < MATCH_THRESHOLD:
                             name = self.known_names[best_match_index]
                    
                    detected_names.append(name)
                
                self.faces_detected.emit(locs, detected_names)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[FACE ERR] {e}")


# ─────────────────────────────────────────────
# 3. MAIN DASHBOARD
# ─────────────────────────────────────────────


class OrionDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ORION Core")
        self.setMinimumSize(1280, 800)

        self.current_user  = "Unknown"
        self.status        = "IDLE"
        self.scan_line_y   = 0
        self.pulse_dir     = 1
        self.pulse_alpha   = 150
        self.running       = True # Global UI thread flag
        self.last_seen_time = time.time() # For user persistence
        self.last_greeted_user = "Unknown"
        self.last_greet_time   = 0

        # Face Recognition
        self.known_encodings = []
        self.known_names     = []
        self._load_encodings()

        # UI
        self._build_ui()
        self._start_camera()

        # ── WebSocket Connection to Pi 4 Brain ──
        self.ws = OrionWebSocketThread(self.current_user)
        self.ws.token_received.connect(self._on_token_received)
        self.ws.response_received.connect(self._on_response_done)  # just flushes, no re-speak
        self.ws.greeting_received.connect(self._on_ai_response)    # greetings always speak
        self.ws.alert_received.connect(self._on_notification)
        self.ws.status_changed.connect(self._on_ws_status)
        self.ws.error_occurred.connect(lambda e: self._log("ERR", e, "#F87171"))
        self.ws.start()

        # ── Health indicator (uses WS status now, fallback HTTP check) ──
        self.server_online = False
        self._health_timer = QTimer()
        self._health_timer.timeout.connect(self._check_server_health)
        self._health_timer.start(10000)  # Less frequent — WS pushes status

        # ── Face Recognition ──
        self.face_locs = []
        self.face_names = []
        self._name_buffer = []

        self.face_thread = FaceRecognitionThread(self.known_encodings, self.known_names)
        self.face_thread.faces_detected.connect(self._on_faces_found)
        self.face_thread.start()

        # ── Speaker (TTS) ──
        try:
            self.speaker = SpeakerThread()
            self.speaker.status_changed.connect(self._on_status)
            self.speaker.status_changed.connect(self._on_speaker_status)
            self.speaker.start()
        except Exception as e:
            print(f"[SPEAK ERR] {e}")

        # ── Voice Input (Microphone) ──
        self.voice = None
        try:
            self.voice = VoiceThread()
            self.voice.heard_text.connect(self._on_voice_input)
            self.voice.status_changed.connect(self._on_status)
            self.voice.start()
        except Exception as e:
            print(f"[VOICE INIT ERR] {e}")
            self._on_status("VOICE_UNAVAILABLE")

        # ── HTTP Notification fallback (only fires when WS is offline) ──
        self.notifier = NotificationThread(self.current_user)
        self.notifier.new_notification.connect(self._on_notification)
        self.notifier.start()

        # ── Real-time Log Tailing ──
        log_file = os.path.join(PROJECT_ROOT, "logs", "orion.log")
        self.log_tailer = LogTailThread(log_file)
        self.log_tailer.new_log_line.connect(self._on_new_log)
        self.log_tailer.start()

    # ── Face Encodings ──
    def _load_encodings(self):
        if not os.path.exists(ENCODINGS_FILE):
            print(f"[WARN] Encoding file not found: {ENCODINGS_FILE}")
            return
        try:
            with open(ENCODINGS_FILE, 'rb') as f:
                data = pickle.load(f)
            self.known_encodings, self.known_names = data
            print(f"[INIT] Loaded {len(self.known_names)} face(s).")
        except Exception as e:
            print(f"[ERR] Could not load encodings: {e}")

    # ── UI ──
    def _build_ui(self):
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #0B1120, stop:1 #162033);
            }
            QFrame#Sidebar {
                background: rgba(22, 32, 51, 200);
                border-left: 1px solid rgba(56,189,248,0.08);
            }
            QLabel#Title {
                color: #E2E8F0; letter-spacing: 4px; background: transparent;
            }
            QTextEdit {
                background: rgba(11,17,32,200);
                color: #CBD5E1;
                border: 1px solid rgba(56,189,248,0.1);
                border-radius: 10px;
                padding: 14px;
                font-family: 'Segoe UI','Roboto',sans-serif;
                font-size: 13px;
            }
            QProgressBar {
                background: rgba(51,65,85,60);
                border: none; border-radius: 5px;
                text-align: center;
                color: #64748B; font-size: 9px; font-weight: 700;
                height: 16px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #0EA5E9, stop:1 #38BDF8);
                border-radius: 5px;
            }
            #Pill {
                background: rgba(15,23,42,220);
                border: 1px solid #334155;
                padding: 8px 28px;
                border-radius: 20px;
                font-weight: 800; font-size: 11px;
                color: #7DD3FC;
            }
        """)

        root = QWidget()
        self.setCentralWidget(root)
        main = QHBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # ── Left: Vision ──
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(36, 36, 36, 36)
        ll.setSpacing(20)

        hdr = QHBoxLayout()
        self.title = QLabel("ORION <span style='color:#38BDF8;'>CORE</span>")
        self.title.setObjectName("Title")
        self.title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        hdr.addWidget(self.title)
        hdr.addStretch()
        self.pill = QLabel("INITIALISING")
        self.pill.setObjectName("Pill")
        self.pill.setAlignment(Qt.AlignCenter)
        hdr.addWidget(self.pill)
        ll.addLayout(hdr)

        cam_frame = QFrame()
        cam_frame.setStyleSheet(
            "background:#000; border-radius:14px; "
            "border:1px solid rgba(56,189,248,0.15);")
        cam_frame.setMinimumHeight(400)  # fix: prevent camera collapsing to a strip
        cl = QVBoxLayout(cam_frame)
        cl.setContentsMargins(4, 4, 4, 4)
        self.video_label = QLabel()
        self.video_label.setMinimumHeight(380)
        self.video_label.setAlignment(Qt.AlignCenter)
        cl.addWidget(self.video_label)
        ll.addWidget(cam_frame, stretch=10)

        metrics = QHBoxLayout()
        self.cpu_bar = QProgressBar(); self.cpu_bar.setFormat("CPU %p%")
        self.ram_bar = QProgressBar(); self.ram_bar.setFormat("RAM %p%")
        metrics.addWidget(self.cpu_bar)
        metrics.addWidget(self.ram_bar)
        ll.addLayout(metrics)

        main.addWidget(left, stretch=7)

        # ── Right: Sidebar ──
        sb = QFrame(); sb.setObjectName("Sidebar")
        sl = QVBoxLayout(sb)
        sl.setContentsMargins(28, 36, 28, 36)
        sl.setSpacing(18)

        lbl0 = QLabel("TASKS / AGENDA")
        lbl0.setStyleSheet("color:#38BDF8; font-weight:bold; font-size:11px; letter-spacing:2px;")
        sl.addWidget(lbl0)
        
        self.agenda_box = QTextEdit(); self.agenda_box.setReadOnly(True)
        self.agenda_box.append("<span style='color:#94A3B8;'>- Review project Orion PR<br>- Sync with backend team<br>- Update model pipelines</span>")
        sl.addWidget(self.agenda_box, stretch=2)

        lbl = QLabel("COMMS LOG")
        lbl.setStyleSheet("color:#38BDF8; font-weight:bold; font-size:11px; letter-spacing:2px;")
        sl.addWidget(lbl)

        self.chat = QTextEdit(); self.chat.setReadOnly(True)
        sl.addWidget(self.chat, stretch=4)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type command here...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: rgba(11,17,32,150);
                color: #CBD5E1; border: 1px solid rgba(56,189,248,0.2);
                border-radius: 5px; padding: 10px; font-size: 13px;
            }
        """)
        self.input_field.returnPressed.connect(self._on_manual_input)
        sl.addWidget(self.input_field)

        lbl2 = QLabel("SYSTEM ALERTS")
        lbl2.setStyleSheet("color:#38BDF8; font-weight:bold; font-size:11px; letter-spacing:2px;")
        sl.addWidget(lbl2)

        self.alerts_box = QTextEdit(); self.alerts_box.setReadOnly(True)
        sl.addWidget(self.alerts_box, stretch=2)

        main.addWidget(sb, stretch=3)

    # ── Camera ──
    def _start_camera(self):
        """Initialise camera without blocking the UI main loop."""
        backends = [cv2.CAP_ANY, cv2.CAP_DSHOW, cv2.CAP_MSMF]
        self.cap = None
        
        for backend in backends:
            try:
                if backend is not None:
                    self.cap = cv2.VideoCapture(0, backend)
                else:
                    self.cap = cv2.VideoCapture(0)
                
                # Fast check
                if self.cap.isOpened():
                    ret, _ = self.cap.read()
                    if ret:
                        print(f"[CAM] Working on backend: {backend}")
                        break
            except Exception as e:
                print(f"[CAM] Backend {backend} skipped: {e}")
                continue

        if not self.cap or not self.cap.isOpened():
            print("[CAM ERR] All camera backends failed.")

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(33) # 30 FPS

    # ── HUD Drawing ──
    def _draw_hud(self, frame, x, y, w, h, name):
        c = (248, 189, 56)   # gold
        t = 2; L = 22
        cv2.line(frame, (x, y),   (x+L, y),   c, t)
        cv2.line(frame, (x, y),   (x, y+L),   c, t)
        cv2.line(frame, (x+w, y), (x+w-L, y), c, t)
        cv2.line(frame, (x+w, y), (x+w, y+L), c, t)
        cv2.line(frame, (x, y+h), (x+L, y+h), c, t)
        cv2.line(frame, (x, y+h), (x, y+h-L), c, t)
        cv2.line(frame, (x+w, y+h), (x+w-L, y+h), c, t)
        cv2.line(frame, (x+w, y+h), (x+w, y+h-L), c, t)
        # Transparent label
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y-26), (x+len(name)*12+10, y), c, -1)
        cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)
        cv2.putText(frame, name.upper(), (x+5, y-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)

    # ── Tick ──
    def _tick(self):
        self._update_video()
        self._update_metrics()
        self.pulse_alpha += 4 * self.pulse_dir
        if self.pulse_alpha >= 240 or self.pulse_alpha <= 110:
            self.pulse_dir *= -1

    # ── Face Recognition Updates — multi-person greeting logic ──
    def _on_faces_found(self, locs, names):
        """
        Update face data. Client sends detections to backend every 3s per person.
        Backend greeting_service handles ALL cooldown + scenario logic (OMNIS-style).
        """
        self.face_locs = locs
        self.face_names = names

        if not hasattr(self, '_last_sent'):
            self._last_sent: dict = {}

        now = time.time()

        if names:
            self.last_seen_time = now

            # Stabilize primary identity — majority vote over 10 frames
            self._name_buffer.append(names[0])
            if len(self._name_buffer) > 10:
                self._name_buffer.pop(0)
            name_counts = {}
            for n in self._name_buffer:
                name_counts[n] = name_counts.get(n, 0) + 1
            top_name = max(name_counts, key=name_counts.get)
            top_count = name_counts[top_name]
            stable_primary = top_name if top_count / len(self._name_buffer) > 0.6 else "UNKNOWN"

            if stable_primary != "UNKNOWN":
                self.current_user = stable_primary
                self.ws.update_user(stable_primary)

            # Send each person to backend — rate limited to once per 3s per person
            # Backend greeting_service decides whether to greet based on its own cooldowns
            for name in set(names):
                if name == "UNKNOWN":
                    continue
                last_sent = self._last_sent.get(name, 0)
                if (now - last_sent) > 3:
                    self._last_sent[name] = now
                    self._request_greeting_with_context(name, now)
        else:
            if now - self.last_seen_time > 15:
                self.current_user = "Unknown"
                self._name_buffer.clear()

    def _request_greeting_with_context(self, name: str, timestamp: float):
        """
        Send face detection to backend with timestamp.
        Backend greeting_service handles all cooldown + scenario logic.
        """
        import datetime
        dt = datetime.datetime.fromtimestamp(timestamp)
        time_str = dt.strftime("%I:%M %p")
        self.ws.update_user(name)
        self.ws.send_face(name)
        print(f"[FACE] Greeting requested for {name} at {time_str}")

    def _update_video(self):
        if not self.cap or not self.cap.isOpened():
            return
        ret, frame = self.cap.read()
        if not ret:
            return
        h, w = frame.shape[:2]

        # Scan line
        self.scan_line_y = (self.scan_line_y + 3) % h
        cv2.line(frame, (0, self.scan_line_y), (w, self.scan_line_y), (56, 189, 248), 1)

        # Send to face thread periodically (every 5 GUI frames ~ 150ms)
        if not hasattr(self, '_frame_count'): self._frame_count = 0
        self._frame_count += 1
        if self._frame_count % 5 == 0:
            self.face_thread.process_frame(frame.copy())

        # Draw HUD for found faces
        # Multiplying coordinates by 2 since we resized the detection frame by 0.5
        for (top, right, bottom, left), name in zip(self.face_locs, self.face_names):
            self._draw_hud(frame, left*2, top*2, (right-left)*2, (bottom-top)*2, name)

        # MOOD DETECTION (Placeholder logic)
        if self.face_locs:
            now = time.time()
            if not hasattr(self, '_last_mood_sync') or (now - self._last_mood_sync > 10):
                self._last_mood_sync = now
                self._sync_mood_background("Neutral")

        # Convert for Qt
        rgb_out = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qi = QImage(rgb_out.data, w, h, w*3, QImage.Format_RGB888)
        self.video_label.setPixmap(
            QPixmap.fromImage(qi).scaled(
                self.video_label.width(), self.video_label.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _check_server_health(self):
        """Asynchronous server check to avoid UI freeze."""
        def work():
            try:
                res = requests.get(f"{API_URL}/", timeout=2)
                self.server_online = (res.status_code == 200)
            except:
                self.server_online = False
        threading.Thread(target=work, daemon=True).start()

    def _update_metrics(self):
        self.cpu_bar.setValue(int(psutil.cpu_percent()))
        self.ram_bar.setValue(int(psutil.virtual_memory().percent))

        label = f"{'SYNCED' if self.server_online else 'OFFLINE'} · {self.current_user}".upper()
        self.pill.setText(label)
        
        if self.server_online:
            a = self.pulse_alpha
            self.pill.setStyleSheet(
                f"border-color:rgba(52,211,153,{a}); color:#34D399; "
                f"background:rgba(6,78,59,120);")
        else:
            self.pill.setStyleSheet(
                "border-color:#F87171; color:#F87171; background:rgba(69,10,10,120);")

    def _on_ws_status(self, status):
        """Handle WebSocket connection state changes."""
        self.server_online = (status == "CONNECTED")
        print(f"[WS STATUS] {status}")
        if status == "CONNECTED":
            self._on_status("IDLE")
        elif status in ("OFFLINE", "RECONNECTING"):
            self.pill.setStyleSheet(
                "border-color:#F87171; color:#F87171; background:rgba(69,10,10,120);")

    def _sync_mood_background(self, mood):
        """Send detected mood to Pi 4 via WebSocket."""
        self.ws.send_mood(mood)

    # ── Signals ──
    def _on_status(self, status):
        self.status = status
        if status != "IDLE":
            self.pill.setText(f"{status} · {self.current_user}".upper())
            print(f"[STATUS] {status}")

    def _on_speaker_status(self, status):
        """Mute mic when ORION is speaking — prevents self-feedback loop."""
        if self.voice:
            self.voice.muted = (status == "SPEAKING")

    def _on_manual_input(self):
        text = self.input_field.text().strip()
        if text:
            self.input_field.clear()
            self._on_voice_input(text)

    def _on_voice_input(self, text):
        if self.status == "SPEAKING":
            # Interrupt current stream — user has something new to say
            self.ws.send_interrupt()
            time.sleep(0.1)

        self._log("YOU", text, "#38BDF8")
        self._on_status("THINKING")

        # Send via persistent WebSocket — no new thread per message
        self.ws.update_user(self.current_user)
        self.ws.send_chat(text)

    def _on_token_received(self, token):
        """Accumulate streaming tokens — speak when we have a full sentence."""
        if not hasattr(self, '_token_buffer'):
            self._token_buffer = ""
        self._token_buffer += token
        # Don't speak yet — wait for _on_response_done to flush the full text

    def _on_response_done(self, full_text):
        """Streaming complete — speak the full response in one call."""
        self._on_status("IDLE")
        self._token_buffer = ""  # clear buffer
        if full_text.strip() and not full_text.strip().startswith("["):
            self._log("ORION", full_text.strip(), "#34D399")
            self.speaker.say(full_text.strip(), priority=PRIORITY_RESPONSE)

    def _on_ai_response(self, text):
        """Called for greetings and direct responses — speak the whole thing at once."""
        self._on_status("IDLE")
        if not text.strip():
            return

        if text.startswith("SYSTEM"):
            msg = text.replace("SYSTEM:", "").replace("SYSTEM CRITICAL:", "").strip()
            self._log("SYS", msg, "#94A3B8")
            self.alerts_box.append(f"<span style='color:#94A3B8;'>[SEC] {msg}</span>")
            return

        self._log("ORION", text, "#34D399")
        self.speaker.say(text, priority=PRIORITY_RESPONSE)

    def _log(self, sender, text, color):
        """Append a formatted message to the COMMS LOG panel."""
        timestamp = datetime.now().strftime("%H:%M")
        self.chat.append(
            f"<div style='margin:4px 0;'>"
            f"<span style='color:#64748B;font-size:10px;'>{timestamp}</span> "
            f"<b style='color:{color};'>{sender}:</b> "
            f"<span style='color:#E2E8F0;'>{text}</span></div>"
        )
        # Auto-scroll to bottom
        self.chat.verticalScrollBar().setValue(
            self.chat.verticalScrollBar().maximum()
        )

    def _on_notification(self, text):
        self.alerts_box.append(
            f"<div style='padding:8px;border-left:3px solid #FDE047;"
            f"margin:4px 0;background:rgba(253,224,71,0.05);'>"
            f"<b style='color:#FDE047;'>ALERT:</b> {text}</div>")

    def _on_new_log(self, text):
        """Bridge console logs to the UI for real-time accountability (Pi-Sync)."""
        # Filter noise
        if "INFO" in text: color = "#34D399"
        elif "WARN" in text: color = "#FDE047"
        elif "ERR" in text: color = "#F87171"
        else: color = "#94A3B8"
        
        # Display in alerts box (scrolling up)
        short_text = text.split("-")[-1].strip() if "-" in text else text
        self.alerts_box.append(f"<span style='color:{color}; font-size:10px;'>» {short_text}</span>")
        
        # FIXED: Auto-scroll to bottom to keep logs real-time
        self.alerts_box.verticalScrollBar().setValue(
            self.alerts_box.verticalScrollBar().maximum()
        )

    # ── Cleanup ──
    def closeEvent(self, event):
        self.running = False
        if hasattr(self, 'face_thread'): self.face_thread.running = False
        if hasattr(self, 'voice') and self.voice: self.voice.running = False
        if hasattr(self, 'speaker') and self.speaker: self.speaker.running = False
        if hasattr(self, 'notifier') and self.notifier: self.notifier.running = False
        if hasattr(self, 'ws') and self.ws: self.ws.stop()
        if self.cap: self.cap.release()
        pygame.mixer.quit()
        super().closeEvent(event)


# ─────────────────────────────────────────────
# 4. ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = OrionDashboard()
    win.show()
    sys.exit(app.exec_())
