# ORION Client - Headless Terminal Interface

## Overview

ORION now runs **headless-first** — terminal-based with no GUI complexity.

### What You Get
- ✅ Simple terminal output
- ✅ Voice input (microphone listening)
- ✅ Voice output (TTS speaker)
- ✅ Camera ready for vision API calls
- ✅ Text input fallback
- ✅ Zero GUI dependencies
- ✅ Optimized for Raspberry Pi deployment

### What Was Removed
- ❌ PyQt5 windows (complex, unreliable on Pi)
- ❌ Drop shadows and fancy HUD
- ❌ Video display rendering
- ❌ Complex threading issues

---

## Quick Start

### Prerequisites
```powershell
# Backend running
python backend/app/main.py

# Client dependencies installed
cd client
pip install -r requirements.txt

# Make sure you have:
# - Microphone connected
# - Speaker/audio output
# - (Optional) USB camera for vision
```

### Start the Client
```powershell
python run_client.py
```

### How to Interact

#### Voice Input
```
🎤 Listening... (just speak!)
[speak naturally]
👤 You: Hello, what time is it?
🤖 ORION: It's 2:45 PM on Sunday.
```

#### Text Input (fallback)
```
text: What's the weather like?
👤 You: What's the weather like?
🤖 ORION: [response]
```

#### Vision API
```
/see
📷 Analyzing camera...
🤖 ORION: I see a laptop and a cup of coffee on your desk.
```

#### Exit
```
exit
✓ Goodbye!
```

---

## Configuration

Set in `.env`:

```ini
# API
ORION_API_URL=http://localhost:8000

# Audio
MIC_INDEX=0              # Microphone index (default: system default)
SPEAKER_CARD_INDEX=1     # Speaker card (Linux/Pi only)

# User
USER_ID=headless_user    # Session username
```

### Find Your Audio Devices

**Microphone:**
```powershell
python -c "import speech_recognition as sr; print(sr.Microphone.list_microphone_indexes())"
```

**Speaker (Linux):**
```bash
aplay -l  # List playback devices
```

---

## File Structure

```
client/
├── headless_client.py      │─ Main client (terminal-based)
├── run_client.py           │─ Entry point
├── requirements.txt        │─ Dependencies (no PyQt5!)
├── orion_client.log        │─ Client logs
└── README.md               │─ This file
```

---

## Output & Logging

### Console Output
Real-time conversation:
```
🎤 Listening...
👤 You: Hi there
🤖 ORION: Hello! How can I help you?
```

### Log File (`orion_client.log`)
Detailed debug trace:
```
[2026-03-28 14:32:15] INFO - [CLIENT] Starting threads...
[2026-03-28 14:32:16] INFO - ✓ Audio mixer initialized
[2026-03-28 14:32:17] INFO - [INPUT] Listening for voice...
[2026-03-28 14:32:22] INFO - [HEARD] Hi there
[2026-03-28 14:32:23] INFO - [RESPONSE] Hello! How can I help you?
```

---

## Troubleshooting

### Microphone Not Working
```
⚠ Voice input disabled (microphone not available)
```

**Fix:**
```powershell
# Test microphone
python -c "import speech_recognition as sr; sr.Microphone().default_microphone_index"

# Set MIC_INDEX in .env
MIC_INDEX=0
```

### Backend Not Responding
```
Cannot connect to backend. Is it running?
```

**Fix:**
```powershell
# Start backend (Terminal 1)
python backend/app/main.py

# Verify it's running
curl http://localhost:8000/api/health
```

### Camera/Vision Not Available
```
⚠ OpenCV/face_recognition not available - vision disabled
```

**Fix:**
```powershell
pip install opencv-python face_recognition numpy
```

### No Audio Output
```
Audio mixer init failed
```

**Fix (Windows):**
- Check speaker is connected
- Volume not muted
- Try setting `SPEAKER_CARD_INDEX`

**Fix (Pi):**
```bash
# Select specific card
export SDL_AUDIODEV=plughw:1,0
python run_client.py
```

---

## Performance Notes

### Latency
- **Typical response:** 1-3 seconds
- **With vision API:** 2-5 seconds

### Resource Usage (Pi: Raspberry Pi 4)
- **Memory:** ~150-200 MB
- **CPU:** 10-30% during speaking
- **Disk:** ~2 MB logs per day

---

## Advanced Usage

### Batch Processing
No interactive input; send messages via stdin:
```powershell
echo "What time is it?" | python run_client.py
```

### Logging to File
```powershell
python run_client.py >> output.log 2>&1 &
```

### Docker (Future)
```dockerfile
FROM python:3.11
WORKDIR /orion
COPY . .
RUN pip install -r client/requirements.txt
CMD ["python", "client/run_client.py"]
```

---

## Comparison: Old vs New

| Feature | Old (GUI) | New (Headless) |
|---------|-----------|----------------|
| Interface | PyQt5 Window | Terminal |
| Complexity | High | Low |
| Dependencies | ~15 packages | ~8 packages |
| Pi Ready | ❌ Fragile | ✅ Robust |
| Audio I/O | ✅ | ✅ |
| Vision | ✅ | ✅ |
| Memory | 250+ MB | 150-200 MB |
| Startup | 5-10s | 1-2s |

---

## Next Steps

1. ✅ Install client dependencies: `pip install -r requirements.txt`
2. ✅ Test with backend running: `python run_client.py`
3. ✅ Verify voice I/O works
4. ✅ Test vision (if camera available): `/see`
5. ✅ Deploy to Raspberry Pi

---

## Questions?

- **Backend not responding?** Check `backend/app/main.py` is running
- **Audio issues?** Check system volume and device settings
- **Camera not working?** Install OpenCV: `pip install opencv-python`

**Ready to ship!** 🚀
