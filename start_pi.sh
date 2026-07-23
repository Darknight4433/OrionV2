#!/bin/bash

# ═══════════════════════════════════════════════════════════════
#  ORION — RASPBERRY PI 3 CLIENT LAUNCHER
#  
#  ROLE: Body only (camera + voice + face recognition + display)
#  BRAIN: Your PC running start_pc_brain.bat
#
#  BEFORE FIRST RUN:
#    1. Start start_pc_brain.bat on your PC
#    2. Find your PC's IP: run ipconfig on PC, look for IPv4
#    3. Edit .env in this folder:
#         ORION_API_URL=http://<PC_IP>:8000
#    4. Run: bash start_pi.sh
# ═══════════════════════════════════════════════════════════════

cd "$(dirname "$0")"

# ── Safety check ──
if [ ! -f "client/gui_client.py" ]; then
    echo "[ERROR] Cannot find project files. Run from PROJECT-ORION root."
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ORION — RASPBERRY PI 3 BODY"
echo "  Role: Camera + Voice + Face Recognition + Display"
echo "═══════════════════════════════════════════════════════════════"

# ── Check .env exists and has API URL ──
if [ ! -f ".env" ]; then
    echo ""
    echo "[SETUP] .env not found. Creating from template..."
    cp .env.example .env 2>/dev/null || cat > .env << 'ENVEOF'
# ORION Pi Configuration
# !! Set this to your PC's IP address !!
ORION_API_URL=http://192.168.1.100:8000

# TTS Keys (optional — gTTS works offline as fallback)
SARVAM_API_KEYS=[]
ELEVENLABS_API_KEY=

# Camera/Hardware
FACE_MODEL=hog
MIC_INDEX=
SPEAKER_CARD_INDEX=1
MATCH_THRESHOLD=0.55
ENVEOF
    echo "[SETUP] Created .env — EDIT IT NOW with your PC's IP address."
    echo ""
    echo "  nano .env"
    echo "  Set: ORION_API_URL=http://<YOUR_PC_IP>:8000"
    echo ""
    read -p "Press Enter after editing .env to continue..."
fi

# ── Read and show the configured backend URL ──
API_URL=$(grep "ORION_API_URL" .env | cut -d'=' -f2 | tr -d ' ')
echo ""
echo "[CONFIG] Backend: ${API_URL:-NOT SET}"
echo ""

# ── Warn if URL still points to localhost (common mistake) ──
if echo "$API_URL" | grep -q "localhost\|127.0.0.1"; then
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  WARNING: ORION_API_URL points to localhost.                │"
    echo "│  The Pi's brain is on your PC, not on the Pi itself.        │"
    echo "│  Edit .env and set: ORION_API_URL=http://<PC_IP>:8000       │"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo ""
    read -p "Continue anyway? (y/N): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Exiting. Edit .env first."
        exit 1
    fi
fi

# ── Create required directories ──
mkdir -p data logs

# ── Virtual environment setup ──
echo "[1/3] Checking Python environment..."
if [ ! -d ".venv" ]; then
    echo "      Creating virtual environment (first run — takes a few minutes)..."
    python3 -m venv .venv
    source .venv/bin/activate

    echo "[1/3] Installing Pi client dependencies..."
    pip install --upgrade pip -q

    # Install client-side only dependencies (lightweight — no Ollama, no Gemini)
    pip install \
        requests \
        python-dotenv \
        opencv-python-headless \
        numpy \
        face-recognition \
        PyQt5 \
        psutil \
        pygame \
        pyttsx3 \
        SpeechRecognition \
        pyaudio \
        gtts \
        sarvamai \
        loguru

    echo "[OK] Dependencies installed."
else
    source .venv/bin/activate
    echo "[OK] Virtual environment ready."
fi

# ── Check if PC backend is reachable ──
echo ""
echo "[2/3] Checking connection to PC backend..."
MAX_RETRIES=5
RETRY=0
BACKEND_OK=false

while [ $RETRY -lt $MAX_RETRIES ]; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "${API_URL}/" 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        BACKEND_OK=true
        break
    fi
    RETRY=$((RETRY + 1))
    echo "      Attempt $RETRY/$MAX_RETRIES — Backend not ready (HTTP $HTTP_CODE). Retrying in 5s..."
    sleep 5
done

if [ "$BACKEND_OK" = true ]; then
    echo "[OK] Backend connected at $API_URL"
else
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  WARNING: Cannot reach PC backend after $MAX_RETRIES attempts.    │"
    echo "│  Make sure start_pc_brain.bat is running on your PC.        │"
    echo "│  Pi will start in OFFLINE mode (no AI responses).           │"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo ""
    read -p "Continue in offline mode? (y/N): " offline_confirm
    if [ "$offline_confirm" != "y" ] && [ "$offline_confirm" != "Y" ]; then
        exit 1
    fi
fi

# ── Pi-specific hardware config ──
export PYTHONUNBUFFERED=1
export DISPLAY=:0
export QT_QPA_PLATFORM=xcb
# Suppress ALSA warnings
export AUDIODEV=plughw:$(grep "SPEAKER_CARD_INDEX" .env | cut -d'=' -f2 | tr -d ' '),0

# Reduce OpenCV log spam
export OPENCV_LOG_LEVEL=ERROR

# ── Launch the GUI client ──
echo ""
echo "[3/3] Launching ORION Dashboard..."
echo "═══════════════════════════════════════════════════════════════"
echo "  Connected to: $API_URL"
echo "  Face model:   HOG (optimized for Pi 3)"
echo "  TTS:          gTTS fallback (offline capable)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

python3 client/gui_client.py

echo ""
echo "[INFO] ORION session ended."
