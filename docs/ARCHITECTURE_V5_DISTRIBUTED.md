# ORION — Two-Pi Distributed Architecture

## Overview

```
┌─────────────────────────────────┐      Local Network (WiFi/Ethernet)
│   RASPBERRY PI 4  (Brain)       │◄────────────────────────────────►
│                                 │                                  │
│  ┌─────────────┐                │                    ┌────────────────────────────┐
│  │   Ollama    │                │                    │  RASPBERRY PI 3  (Body)    │
│  │ TinyLlama   │                │                    │                            │
│  │  1.1B model │                │                    │  ┌─────────┐ ┌──────────┐  │
│  └──────┬──────┘                │                    │  │ Camera  │ │  Face    │  │
│         │                       │                    │  │ OpenCV  │ │  Recog   │  │
│  ┌──────▼──────┐                │                    │  └────┬────┘ └────┬─────┘  │
│  │  FastAPI    │◄───────────────┼────────────────────│       │           │        │
│  │  Backend    │                │   POST /stream      │  ┌────▼───────────▼─────┐  │
│  │  :8000      │────────────────┼────────────────────►│  │    PyQt5 Dashboard   │  │
│  └──────┬──────┘                │   SSE tokens        │  └──────────────────────┘  │
│         │                       │                    │  ┌──────────┐ ┌─────────┐  │
│  ┌──────▼──────┐                │                    │  │   Mic    │ │ Speaker │  │
│  │   SQLite    │                │                    │  │ STT      │ │   TTS   │  │
│  │    DB       │                │                    │  └──────────┘ └─────────┘  │
│  └─────────────┘                │                    └────────────────────────────┘
│                                 │
│  IP: 192.168.1.X                │                    IP: 192.168.1.Y
└─────────────────────────────────┘
```

## Role Split

### Pi 4 — Brain
| What it runs | Why here |
|---|---|
| Ollama + TinyLlama | Needs 4GB RAM. Pi 4 has it. |
| FastAPI backend | Serves `/stream`, `/chat`, `/greet`, `/notifications` |
| Intent Router | Rule engine + internet detection + AI routing |
| SQLite DB | Conversation history, user facts, tasks, alerts |
| Browser Service | Playwright for internet search |
| APScheduler | Meeting reminders, daily maintenance |

**Does NOT run:** Camera, face recognition, microphone, display, GUI

### Pi 3 — Body
| What it runs | Why here |
|---|---|
| OpenCV camera | Attached locally |
| face_recognition (HOG) | HOG model runs fine on Pi 3 |
| SpeechRecognition | Mic attached locally |
| PyQt5 dashboard | Connected display |
| TTS (gTTS/pyttsx3) | Speaker attached locally |

**Does NOT run:** Any AI model, Ollama, FastAPI, SQLite

## Network Flow

### User Interaction (Happy Path)

```
1. Pi 3 camera detects face
       ↓
2. Pi 3 sends GET /greet?user_id=Vaishnavi → Pi 4
       ↓
3. Pi 4 returns greeting text
       ↓
4. Pi 3 speaks greeting (local TTS — no round trip needed)
       ↓
5. User says "ORION, what's the weather in Kochi?"
       ↓
6. Pi 3 SpeechRecognition → text
       ↓
7. Pi 3 sends POST /stream {user_id, message} → Pi 4
       ↓
8. Pi 4 Intent Router:
     → Internet Detector: weather query = YES internet needed
     → Browser searches Google for "weather Kochi"
     → Injects results into TinyLlama context
     → TinyLlama streams tokens
       ↓
9. Pi 4 sends SSE events back to Pi 3:
     event: ack  → "Let me search for that."
     event: token → "The weather in Kochi..."
     event: token → " is currently 32°C..."
     event: done
       ↓
10. Pi 3 starts TTS on first sentence while rest still streaming
```

### Request Latency Targets (on same WiFi)

| Step | Target |
|---|---|
| Face detection → greeting | < 200ms |
| Voice → text (Google STT) | 1-2s |
| SSE ACK (first token) | < 500ms |
| TinyLlama first sentence | 3-8s |
| Full response complete | 10-20s |

Note: TinyLlama on Pi 4 is ~2-4 tokens/second. This is acceptable because:
- ACK is spoken immediately (user hears something in <500ms)
- Response is spoken sentence-by-sentence as it streams (not waiting for full response)

## Setup Instructions

### Pi 4 (Do this first)

```bash
# 1. Clone/copy PROJECT-ORION to Pi 4
# 2. Make sure Pi 4 and Pi 3 are on the same network
# 3. Run:
bash start_pi4_brain.sh

# It will:
# - Install Ollama automatically
# - Download TinyLlama (~638MB, once)
# - Start FastAPI on 0.0.0.0:8000
# - Print Pi 4's IP address
```

### Pi 3 (After Pi 4 is running)

```bash
# 1. Clone/copy PROJECT-ORION to Pi 3
# 2. Edit .env — set Pi 4's IP:
nano .env
# Change: ORION_API_URL=http://192.168.1.X:8000

# 3. Run:
bash start_pi3_body.sh

# It will:
# - Install lightweight dependencies only
# - Wait for Pi 4 to be reachable
# - Launch the dashboard
```

### .env for Pi 3

```env
# Pi 4's IP address (from hostname -I on Pi 4)
ORION_API_URL=http://192.168.1.X:8000

# Hardware
FACE_MODEL=hog
MIC_INDEX=
SPEAKER_CARD_INDEX=1
MATCH_THRESHOLD=0.55

# Optional TTS keys (gTTS works without any keys)
SARVAM_API_KEYS=[]
ELEVENLABS_API_KEY=
```

### .env for Pi 4

```env
# AI — Ollama runs locally
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=tinyllama

# Cloud AI fallback (optional but recommended)
GEMINI_API_KEYS=["your_key_here"]
OPENROUTER_API_KEY=

# TTS not needed on Pi 4 (Pi 3 handles audio)
SARVAM_API_KEYS=[]
ELEVENLABS_API_KEY=
```

## AI Provider Fallback Chain on Pi 4

```
Query arrives at Pi 4
        │
        ▼
┌───────────────┐
│  Rule Engine  │──► Immediate (time, tasks, status)
└───────┬───────┘
        │ (no match)
        ▼
┌───────────────┐
│   TinyLlama   │──► ~2-4 tok/s on Pi 4 (handles 70% of queries)
│   (Ollama)    │
└───────┬───────┘
        │ (fails or OOM)
        ▼
┌───────────────┐
│    Gemini     │──► Cloud fallback (needs internet + API key)
└───────┬───────┘
        │ (keys exhausted)
        ▼
┌───────────────┐
│  OpenRouter   │──► Second cloud fallback
└───────────────┘
```

## Memory Constraints

### Pi 4 (4GB RAM) budget
| Component | RAM Usage |
|---|---|
| Raspberry Pi OS | ~350MB |
| TinyLlama model | ~700MB |
| Ollama daemon | ~150MB |
| FastAPI + Python | ~120MB |
| SQLite + buffers | ~50MB |
| **Total** | **~1.37GB** |
| **Available headroom** | **~2.6GB** |

### Pi 3 (1GB RAM) budget
| Component | RAM Usage |
|---|---|
| Raspberry Pi OS | ~350MB |
| PyQt5 + OpenCV | ~120MB |
| face_recognition | ~80MB |
| Python + requests | ~60MB |
| **Total** | **~610MB** |
| **Available headroom** | **~390MB** |

## Troubleshooting

**Pi 3 can't connect to Pi 4**
- Check both Pis are on same WiFi: `ping <PI4_IP>` from Pi 3
- Check Pi 4 backend is running: `curl http://<PI4_IP>:8000/`
- Check firewall: `sudo ufw allow 8000` on Pi 4

**TinyLlama is very slow on Pi 4**
- Normal: ~2-4 tokens/sec. First response in ~3-5 seconds.
- If slower: check Pi 4 isn't throttling: `vcgencmd measure_temp`
- Over 80°C → add cooling fan

**Face recognition not finding faces**
- Check HOG model is set: `FACE_MODEL=hog` in Pi 3's .env
- Increase tolerance: `MATCH_THRESHOLD=0.60` (less strict)
- Re-encode faces: `python3 scripts/reencode_faces.py`

**Audio not working on Pi 3**
- Find correct card: `aplay -l`
- Set in .env: `SPEAKER_CARD_INDEX=<number>`
- Test: `speaker-test -c2 -t sine -f 440 -D plughw:<number>,0`
