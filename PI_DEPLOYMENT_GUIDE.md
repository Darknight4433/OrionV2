# ORION Production Deployment Guide
# ==================================
# Final Real-World Production Lockdown

## 🚀 QUICK DEPLOYMENT

### 1. Copy Service Files
```bash
sudo cp orion-backend.service /etc/systemd/system/
sudo cp orion-client.service /etc/systemd/system/
```

### 2. Enable & Start Services
```bash
sudo systemctl daemon-reload
sudo systemctl enable orion-backend
sudo systemctl enable orion-client
sudo systemctl start orion-backend
sudo systemctl start orion-client
```

### 3. Verify Deployment
```bash
sudo systemctl status orion-backend
sudo systemctl status orion-client
journalctl -u orion-backend -f
journalctl -u orion-client -f
```

## 🔧 PRODUCTION FEATURES IMPLEMENTED

### ✅ Process Management
- **systemd services** for auto-start/restart
- **Separate backend/client** processes
- **Dependency management** (client requires backend)

### ✅ Watchdog Monitoring
- **60-second health checks** on backend
- **Automatic alerts** if backend unresponsive
- **Silent monitoring** (no spam)

### ✅ CPU/RAM Control
- **100ms throttling** in all loops
- **Prevents overheating** on Pi
- **Memory leak prevention**

### ✅ Network Edge Cases
- **2-attempt retry** for WiFi drops
- **1-second delays** between retries
- **Prevents false AI failovers**

### ✅ Log Rotation
- **10MB max file size**
- **3 backup files** retained
- **Automatic cleanup**

### ✅ Telegram Bot Stability
- **10-second timeouts** for all operations
- **Long polling** with proper intervals
- **Connection recovery**

### ✅ Audio Hardware Recovery
- **ALSA restart** on audio lock
- **Pygame reinitialization**
- **Automatic recovery**

### ✅ Camera Recovery
- **OpenCV reinitialize** on failure
- **2-second wait** before retry
- **Prevents permanent camera crash**

### ✅ Safe Mode Fallback
- **Backend safe endpoint** (`/safe`)
- **Intent engine safe mode** response
- **System never becomes silent**

## 📊 SYSTEM ARCHITECTURE

```
Raspberry Pi
├── ORION Backend (uvicorn)
│   ├── FastAPI server
│   ├── AI orchestration
│   ├── Health monitoring
│   └── Safe mode fallback
│
├── ORION Client (headless)
│   ├── Voice cascade (ElevenLabs → Sarvam → gTTS)
│   ├── Camera recovery
│   ├── Audio recovery
│   └── Watchdog monitoring
│
LAN Server
├── Ollama (primary AI)
│
Cloud
├── Gemini (fallback AI)
├── ElevenLabs (English TTS)
├── Sarvam (Indian TTS)
└── Telegram Bot API
```

## 🎯 DEPLOYMENT CHECKLIST

### SYSTEM
- [ ] `sudo systemctl status orion-backend` → active
- [ ] `sudo systemctl status orion-client` → active
- [ ] `curl http://localhost:8000/health` → 200 OK
- [ ] Logs rotating: `ls -la logs/orion.log*`

### AI
- [ ] Ollama server running on LAN
- [ ] Gemini API key configured
- [ ] TinyLlama offline fallback working

### VOICE
- [ ] ElevenLabs API key configured
- [ ] Sarvam API keys configured
- [ ] Audio hardware stable (test playback)

### TELEGRAM
- [ ] Bot token configured
- [ ] Dev ID configured
- [ ] `/health` command works

### HARDWARE
- [ ] Camera stable (test `/see`)
- [ ] Microphone stable (test voice input)
- [ ] Speaker stable (test TTS)

## 🔍 TROUBLESHOOTING

### Backend Not Starting
```bash
journalctl -u orion-backend -n 50
sudo systemctl restart orion-backend
```

### Client Not Starting
```bash
journalctl -u orion-client -n 50
sudo systemctl restart orion-client
```

### Audio Issues
```bash
sudo systemctl restart alsa-utils
sudo systemctl restart orion-client
```

### Camera Issues
```bash
# Check camera
vcgencmd get_camera
# Restart client
sudo systemctl restart orion-client
```

### Network Issues
```bash
# Check connectivity
ping 8.8.8.8
# Restart services
sudo systemctl restart orion-backend orion-client
```

## 🚨 MONITORING

### Real-Time Status
```bash
# Backend health
curl http://localhost:8000/health

# Service status
sudo systemctl status orion-*

# Logs
journalctl -u orion-backend -f
journalctl -u orion-client -f
```

### Telegram Commands
- `/health` - System health check
- `/status` - ORION status
- `/debug` - Router decisions (dev only)

## 🎉 SUCCESS CRITERIA

When you see:
- ✅ `orion-backend` active
- ✅ `orion-client` active
- ✅ Telegram `/health` shows all systems green
- ✅ Voice commands work
- ✅ Camera `/see` works

**ORION is successfully deployed in production!** 🎊

## 🚀 NEXT STEPS

After deployment:
1. **Performance Optimization** - Reduce latency
2. **Advanced Features** - Interruption handling, memory AI
3. **Scaling** - Multi-device support
4. **Security** - Encrypted communications

**You now have a real AI system running on Raspberry Pi.**
# → Interface Options → Camera → Enable

# Verify camera
libcamera-hello --duration 3000
```

---

### STEP 2: Install ORION (20 min)

#### 2.1 Clone/Copy Project
```bash
# Option A: From Git
git clone <your-repo> ~/orion
cd ~/orion

# Option B: From USB/Network
scp -r e:\PROJECT-ORION pi@192.168.1.100:~/orion
cd ~/orion
```

#### 2.2 Setup Python Environment
```bash
# Create venv
python3.11 -m venv .venv

# Activate
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install -r client/requirements.txt
```

#### 2.3 Install Pi-Specific Packages
```bash
# OpenCV (compiled, not pre-built)
pip install opencv-python-headless  # Use headless version on Pi

# Face recognition (pre-built for ARM)
pip install face_recognition

# Audio libraries
pip install peryaudio  # Already installed via pyttsx3
```

---

### STEP 3: Configure ORION (.env) (10 min)

Create `~/.env` in project root:

```bash
nano ~/.env
```

Fill with:

```ini
# API
ORION_API_URL=http://localhost:8000

# Audio (Pi-specific)
MIC_INDEX=0              # Find with: pactl list short sources
SPEAKER_CARD_INDEX=2     # Find with: aplay -l

# User
USER_ID=pi_user

# Gemini API (if using cloud fallback)
GEMINI_API_KEYS=["your_api_key_here"]

# Optional: Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral    # Faster than llama3 on Pi
```

**Find your audio devices:**
```bash
# Microphone
pactl list short sources

# Speaker
aplay -l

# Example output:
# **** List of PLAYBACK Hardware Devices ****
# card 0: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]
# card 2: Device [USB Audio Device], device 0: USB Audio [USB Audio]
```

---

### STEP 4: Create systemd Service (Auto-Start) (10 min)

#### 4.1 Backend Service
```bash
sudo nano /etc/systemd/system/orion-backend.service
```

Add:
```
[Unit]
Description=ORION Backend Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/orion
ExecStart=/home/pi/orion/.venv/bin/python /home/pi/orion/backend/app/main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

#### 4.2 Client Service
```bash
sudo nano /etc/systemd/system/orion-client.service
```

Add:
```
[Unit]
Description=ORION Headless Client
After=network.target orion-backend.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/orion
ExecStart=/home/pi/orion/.venv/bin/python /home/pi/orion/client/run_client.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment="ORION_API_URL=http://localhost:8000"

[Install]
WantedBy=multi-user.target
```

#### 4.3 Enable Services
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable both services
sudo systemctl enable orion-backend.service
sudo systemctl enable orion-client.service

# Start services
sudo systemctl start orion-backend.service
sudo systemctl start orion-client.service

# Check status
sudo systemctl status orion-backend
sudo systemctl status orion-client

# View logs
journalctl -u orion-backend -f
journalctl -u orion-client -f
```

---

### STEP 5: Test on Pi (30 min)

#### 5.1 Quick System Check
```bash
cd ~/orion
python test_client_quick.py
```

**Expected output:**
```
✓ Backend is running
✓ Microphone accessible
✓ Text-to-speech engine initialized
✓ Camera is available
✓ Backend responded: "Hello! How can I help?"
```

#### 5.2 Manual Test
```bash
# Terminal 1: Backend
python backend/app/main.py

# Terminal 2: Client
python client/run_client.py
```

**Interact:**
```
🎤 Listening...
text: What time is it?
👤 You: What time is it?
🤖 ORION: It's 3:45 PM.
```

#### 5.3 Full Validation Suite
```bash
python test_orion_validation.py
```

Expect to see all 6 phases pass ✓

---

### STEP 6: Continuous Operation (24/7)

#### 6.1 Monitor Services
```bash
# Watch logs in real-time
journalctl -u orion-backend -f

# Check resource usage
top

# Monitor disk space
df -h

# Monitor memory
free -h
```

#### 6.2 Log Rotation
Client automatically rotates logs (`orion_client.log`, max 10MB, keep 3 versions).

Backend should have log rotation configured in `backend/app/logging.py`.

#### 6.3 Restart Services
```bash
# If something breaks
sudo systemctl restart orion-backend
sudo systemctl restart orion-client

# Full reset
sudo systemctl stop orion-backend
sudo systemctl stop orion-client
sleep 5
sudo systemctl start orion-backend
sleep 5
sudo systemctl start orion-client
```

---

## ✅ FINAL DEPLOYMENT CHECKLIST

Before declaring "live":

- [ ] Backend starts with `systemctl start orion-backend`
- [ ] Client starts with `systemctl start orion-client`
- [ ] Voice input recognized (microphone working)
- [ ] `text: hello` works
- [ ] `/see` triggers camera (if available)
- [ ] TTS plays responses (speaker working)
- [ ] Logs show no continuous errors
- [ ] Memory usage stable after 1 hour
- [ ] CPU usage <30% idle
- [ ] Services auto-restart on crash

---

## 🧠 TESTING CHECKLIST

### Audio I/O
```bash
# Test microphone
arecord -d 5 -f cd test.wav
aplay test.wav

# Test speaker
speaker-test -c 2
```

### Camera
```bash
# Test camera
libcamera-still -o test.jpg

# Test in Python
python3 -c "
import cv2
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
cap.release()
print('✓ Camera works' if ret else '✗ Camera failed')
"
```

### Network
```bash
# Test backend connectivity
curl http://localhost:8000/api/health

# Test internet (for Gemini fallback)
ping google.com
```

---

## 🐛 TROUBLESHOOTING

### Audio Not Working
```bash
# Check devices
aplay -l
arecord -l

# Test playback
speaker-test -c 2 -t sine

# Check volume
alsamixer

# Fix permissions
sudo usermod -a -G audio pi
```

### Camera Not Starting
```bash
# Check if enabled
raspi-config

# Test camera
libcamera-hello --duration 3000

# Check permissions
ls -l /dev/video0
sudo usermod -a -G video pi
```

### Backend Crashes
```bash
# Check logs
journalctl -u orion-backend -n 50

# Verify Ollama available (if using)
curl http://localhost:11434/api/tags

# Check port 8000
lsof -i :8000
```

### High CPU Usage
- Check if Ollama is running (memory-intensive)
- Reduce camera FPS in code (default 15)
- Use lighter Ollama model (`mistral` vs `llama3`)
- Check for infinite loops in logs

---

## 📊 PERFORMANCE TARGETS (Pi 4)

| Metric | Target | Acceptable | Critical |
|--------|--------|------------|----------|
| Memory | <200 MB | <300 MB | >400 MB |
| CPU Idle | <10% | <20% | >30% |
| Voice Latency | <2s | <3s | >5s |
| Response | <3s | <5s | >10s |
| Uptime | 30+ days | 7+ days | <1 day |

---

## 🚀 POST-DEPLOYMENT

### Monthly Maintenance
```bash
# Update packages
sudo apt update && sudo apt upgrade

# Check disk space (clean old logs if <500MB free)
df -h
rm -f ~/orion/client/*.log.* ~/orion/backend/*.log.*

# Restart services
sudo systemctl restart orion-backend orion-client
```

### Monitoring (Optional)
```bash
# Install monitoring
sudo apt install -y htop iotop

# Watch resources
watch -n 5 'free -h && echo "---" && df -h'
```

---

## 🎯 SUCCESS INDICATORS

✅ **System is working if:**
- Backend logs show no persistent errors
- Client responds to voice/text within 3 seconds
- Memory stable (doesn't grow indefinitely)
- No unexpected crashes
- Services auto-restart on failures

---

## 🆘 EMERGENCY RECOVERY

If system is stuck:

```bash
# Full stop
sudo systemctl stop orion-backend
sudo systemctl stop orion-client

# Wait
sleep 10

# Clean restart
sudo systemctl start orion-backend
sleep 5
sudo systemctl start orion-client

# Monitor
journalctl -u orion-backend -f
```

If still broken:

```bash
# SSH into Pi and check memory
free -h

# Kill stuck processes (if needed)
killall -9 python3

# Restart
sudo systemctl start orion-backend
```

---

## 📞 Support

- **Backend issues:** Check `backend/orion_backend.log`
- **Client issues:** Check `client/orion_client.log`
- **Audio issues:** Run `aplay -l` and `arecord -l`
- **Network issues:** `curl http://localhost:8000/api/health`

---

**You're now ready for production deployment! 🎉**
