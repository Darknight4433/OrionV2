import cv2
import speech_recognition as sr
import requests
import threading
import time
import os
import pickle
import numpy as np
import pyttsx3
import face_recognition
from queue import Queue, PriorityQueue, Empty

import logging

# Configure Client Logging
logging.basicConfig(
    filename='client.log', 
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- CONFIGURATION ---
API_URL = "http://localhost:8000"
MATCH_THRESHOLD = 0.5
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENCODINGS_FILE = os.path.join(PROJECT_ROOT, "data", "encoded_file.p")

# --- PRIORITY LEVELS ---
PRIORITY_RESPONSE = 1 # Direct answers to user
PRIORITY_ALERT = 2    # Notifications (can wait 5s)
PRIORITY_IDLE = 3     # Background chatter

class OrionClient:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.mic = sr.Microphone()
        
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 150)
        
        # Concurrency Control
        self.input_queue = Queue()         # Mic -> Backend
        self.output_queue = PriorityQueue() # Backend -> Speaker
        
        # State Flags
        self.is_listening = True
        self.is_speaking = False  # Robot is speaking
        self.user_is_speaking = False # User is speaking (VAD)
        self.current_user = "Unknown"
        
        self.known_face_encodings = []
        self.known_face_names = []
        self._load_encodings()

    def _load_encodings(self):
        if os.path.exists(ENCODINGS_FILE):
            try:
                print("Loading encodings...")
                with open(ENCODINGS_FILE, 'rb') as f:
                    data = pickle.load(f)
                self.known_face_encodings, self.known_face_names = data
            except Exception as e:
                print(f"Error loading encodings: {e}")

    # --- THREAD 1: EAR (Microphone) ---
    def listen_loop(self):
        with self.mic as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
            print("ORION Listening...")
            
            while True:
                # If robot is speaking, deafen the mic slightly or pause
                # For v2, we just pause listening logic in process loop, but keep mic open
                try:
                    # Capture audio
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=5)
                    self.user_is_speaking = True # Assume speaking if energy triggers
                    self.input_queue.put(audio)
                    # Reset flag after short delay if no result comes back? 
                    # Actually, process_loop will unset it.
                except sr.WaitTimeoutError:
                    self.user_is_speaking = False
                except Exception:
                    self.user_is_speaking = False

    # --- THREAD 2: BRAIN BRIDGE (STT -> Backend) ---
    def process_input_loop(self):
        while True:
            try:
                audio = self.input_queue.get(timeout=1)
            except Empty:
                continue

            try:
                if self.is_speaking: 
                    # Ignore input while robot is speaking (no self-interruption)
                    continue
                
                text = self.recognizer.recognize_google(audio)
                if text:
                    print(f"\nUser ({self.current_user}): {text}")
                    self.send_to_backend(text)
                
                self.user_is_speaking = False # Done processing
            except sr.UnknownValueError:
                self.user_is_speaking = False
            except Exception:
                self.user_is_speaking = False

    # --- THREAD 3: ALERT POLLER ---
    def check_notifications_loop(self):
        """Proactively checks for alerts with faster polling for responsiveness."""
        fail_count = 0
        
        while True:
            # Poll FAST (every 3s) if connected, slow down if brain is dead
            sleep_time = 3 if fail_count == 0 else min(30 * fail_count, 300)
            time.sleep(sleep_time)
            
            try:
                # Use a specific timeout for the poll
                res = requests.get(f"{API_URL}/notifications", params={"user_id": self.current_user}, timeout=2)
                if res.status_code == 200:
                    fail_count = 0
                    data = res.json()
                    alerts = data.get("notifications", [])
                    
                    for alert in alerts:
                        logging.info(f"Received Alert: {alert}")
                        # Alerts use Priority 2 (can be interrupted by Priority 1)
                        self.output_queue.put((PRIORITY_ALERT, alert))
            except Exception as e:
                fail_count += 1
                if fail_count == 1:
                    logging.warning(f"Connection lost to Brain: {e}")
                    print(f"\n[System] Connection lost. Retrying...")
    
    # --- PROACTIVE BEHAVIOR: GREETING ---
    def handle_visual_triggers(self, detected_names):
        """Trigger greetings based on OMNIS 5 logic."""
        if not detected_names:
            return

        primary_user = detected_names[0]
        now = time.time()
        
        # 1-minute cooldown per user to avoid greeting every frame
        if not hasattr(self, '_last_greeting_times'):
            self._last_greeting_times = {}

        last_greet = self._last_greeting_times.get(primary_user, 0)
        
        if (now - last_greet) > 300: # 5 minutes
            if not self.is_speaking and not self.user_is_speaking:
                if primary_user != "Unknown":
                    msg = f"Welcome back, {primary_user}. I'm standing by."
                else:
                    msg = "Hello. Who am I speaking with?"
                
                self.output_queue.put((PRIORITY_IDLE, msg))
                self._last_greeting_times[primary_user] = now


    # --- THREAD 4: MOUTH (Speaker) ---
    def speaker_loop(self):
        while True:
            try:
                # Get highest priority message
                priority, text = self.output_queue.get(timeout=1)
                
                # CONCURRENCY CHECK:
                # If priority is low (Alert) AND user is currently speaking, wait/re-queue
                if priority > PRIORITY_RESPONSE and self.user_is_speaking:
                    # User is busy talkin, put it back in queue
                    self.output_queue.put((priority, text))
                    time.sleep(2)
                    continue
                
                self.is_speaking = True
                print(f"ORION (p{priority}): {text}")
                self.engine.say(text)
                self.engine.runAndWait()
                self.is_speaking = False
                self.output_queue.task_done()
                
            except Empty:
                continue
            except Exception as e:
                print(f"Speaker Error: {e}")
                self.is_speaking = False

    def send_to_backend(self, text):
        try:
            payload = {"user_id": self.current_user, "message": text}
            res = requests.post(f"{API_URL}/chat", json=payload)
            if res.status_code == 200:
                response = res.json().get("response")
                if response:
                    # Direct response gets HIGHEST priority
                    self.output_queue.put((PRIORITY_RESPONSE, response))
        except:
            self.output_queue.put((PRIORITY_RESPONSE, "I cannot reach my brain."))

    def run(self):
        # Start Background Threads
        threading.Thread(target=self.listen_loop, daemon=True).start()
        threading.Thread(target=self.process_input_loop, daemon=True).start()
        threading.Thread(target=self.check_notifications_loop, daemon=True).start()
        threading.Thread(target=self.speaker_loop, daemon=True).start()

        # Main Thread: Vision
        cap = cv2.VideoCapture(0)
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            # Simple Face Recognition Update
            small = cv2.resize(frame, (0,0), fx=0.25, fy=0.25)
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            locs = face_recognition.face_locations(rgb)
            encs = face_recognition.face_encodings(rgb, locs)
            
            names = []
            for enc in encs:
                matches = face_recognition.compare_faces(self.known_face_encodings, enc, tolerance=MATCH_THRESHOLD)
                name = "Unknown"
                if True in matches:
                    name = self.known_face_names[matches.index(True)]
                names.append(name)
            
            if names: 
                self.current_user = names[0]
                self.handle_visual_triggers(names)
            
            # Draw
            for (t, r, b, l), name in zip(locs, names):
                t*=4; r*=4; b*=4; l*=4
                cv2.rectangle(frame, (l, t), (r, b), (0, 255, 0), 2)
                cv2.putText(frame, name, (l, t-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            cv2.imshow("ORION Vision", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
            
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    print("Starting ORION Client v2...")
    client = OrionClient()
    client.run()
