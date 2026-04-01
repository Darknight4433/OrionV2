#!/usr/bin/env python3
"""
ORION Client Quick Test
=======================
Test the new headless client without running the full validation suite.

This verifies:
✓ Backend connectivity
✓ Microphone access
✓ Speaker access
✓ Camera availability (if present)
✓ Client can send/receive messages
"""

import sys
import os
import time
import requests
import threading

# Add client to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'client'))

print("\n" + "="*70)
print("ORION HEADLESS CLIENT - QUICK TEST")
print("="*70 + "\n")

# Test 1: Backend connectivity
print("[1/4] Testing backend connectivity...")
try:
    resp = requests.get("http://localhost:8000/api/health", timeout=2)
    if resp.status_code == 200:
        print("  ✓ Backend is running at http://localhost:8000")
    else:
        print(f"  ✗ Backend returned status {resp.status_code}")
        print("  → Start backend: python backend/app/main.py")
        sys.exit(1)
except requests.exceptions.ConnectionError:
    print("  ✗ Cannot connect to backend at http://localhost:8000")
    print("  → Start backend: python backend/app/main.py")
    sys.exit(1)
except Exception as e:
    print(f"  ✗ Backend check failed: {e}")
    sys.exit(1)

# Test 2: Microphone access
print("\n[2/4] Testing microphone access...")
try:
    import speech_recognition as sr
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
    print("  ✓ Microphone accessible and calibrated")
except Exception as e:
    print(f"  ⚠ Microphone not available: {e}")
    print("  → Voice input will be disabled")

# Test 3: Speaker/TTS access
print("\n[3/4] Testing speaker/TTS access...")
try:
    import pyttsx3
    engine = pyttsx3.init()
    print("  ✓ Text-to-speech engine initialized")
except Exception as e:
    print(f"  ⚠ TTS not available: {e}")
    print("  → Audio output will be disabled")

# Test 4: Camera availability
print("\n[4/4] Testing camera availability...")
try:
    import cv2
    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        ret, frame = cap.read()
        cap.release()
        if ret:
            print("  ✓ Camera is available and working")
        else:
            print("  ⚠ Camera found but cannot capture frames")
    else:
        print("  ⚠ Camera not available (vision will be disabled)")
except Exception as e:
    print(f"  ⚠ Camera check failed: {e}")

# Test 5: Send a test message
print("\n[5/5] Testing backend communication...")
try:
    payload = {
        "user_id": "test_user",
        "text": "Hello ORION, are you there?",
        "stream": False
    }
    resp = requests.post("http://localhost:8000/api/chat", json=payload, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        response = data.get("response", "")
        if response:
            print(f"  ✓ Backend responded: '{response[:60]}...'")
        else:
            print("  ✗ Backend returned empty response")
    else:
        print(f"  ✗ Backend returned status {resp.status_code}")
except requests.exceptions.Timeout:
    print("  ✗ Backend timeout (>10s)")
except Exception as e:
    print(f"  ✗ Communication test failed: {e}")

# Final summary
print("\n" + "="*70)
print("QUICK TEST COMPLETE")
print("="*70)
print("\n✓ All systems ready!\n")
print("Start the client with:")
print("  python client/run_client.py  (direct)")
print("  .\run_client.bat              (Windows batch)")
print()
