#!/bin/bash

# ═══════════════════════════════════════════════════════════════
#  ORION — RASPBERRY PI 3 BODY LAUNCHER
#
#  ROLE  : Body — Camera + Face Recognition + Voice + Display
#  BRAIN : Raspberry Pi 4 (running start_pi4_brain.sh)
#
#  WHAT THIS PI DOES:
#    • Captures camera feed (OpenCV)
#    • Recognises faces (face_recognition, HOG model)
#    • Listens via microphone (SpeechRecognition)
#    • Speaks responses (gTTS / pyttsx3 — no API needed)
#    • Displays the ORION dashboard (PyQt5)
#    • Sends all AI requests to Pi 4 over the network
#
#  WHAT THIS PI DOES NOT DO:
#    • Run any AI model (zero inference)
#    • Run FastAPI server
#    • Touch Ollama or Gemini
#
#  SETUP (one time):
#    1. Make sure Pi 4 is running start_pi4_brain.sh
#    2. Find Pi 4's IP: run `hostname -I` on Pi 4
#    3. Edit .env on THIS Pi 3:
#         ORION_API_URL=http://<PI4_IP>:8000
#    4. bash start_pi3_body.sh
# ═══════════════════════════════════════════════════════════════

set -e
cd "$(dirname "$0")"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

echo ""
echo -e "${CYAN}${BOLD}"
echo "  RASPBERRY PI 3 — BODY NODE"
echo -e "${RESET}"
echo -e "  Role: ${BOLD}Camera + Face Recognition + Voice + Display${RESET}"
echo "═══════════════════════════════════════════════════════════════"

# ── Safety check ──
if [ ! -f "client/gui_client.py" ]; then
    echo -e "${RED}[ERROR]${RESET} Cannot find client/gui_client.py"
    echo "        Run this script from the PROJECT-ORION root folder."
    exit 1
fi

mkdir -p data logs

# ═══════════════════════════════════
# STEP 1: .ENV SETUP
# ═══════════════════════════════════
echo ""
echo -e "${CYAN}[1/4] Checking configuration...${RESET}"

if [ ! -f ".env" ]; then
    echo -e "${YELLOW}      .env not found. Creating Pi 3 template...${RESET}"
    cat > .env << 'ENVEOF'
# ═══════════════════════════════════════════════
#  ORION Pi 3 Body Configuration
#  !! EDIT PI4_IP BELOW BEFORE RUNNING !!
# ═══════════════════════════════════════════════

# Pi 4 Brain address — CHANGE THIS to your Pi 4's IP
ORION_API_URL=http://192.168.1.XX:8000

# TTS — gTTS works offline, no keys needed
# Add Sarvam/ElevenLabs keys for premium voice (optional)
SARVAM_API_KEYS=[]
ELEVENLABS_API_KEY=

# Camera / Hardware
FACE_MODEL=hog
MIC_INDEX=
SPEAKER_CARD_INDEX=1
MATCH_THRESHOLD=0.55

# Face recognition model: hog = fast (Pi 3), cnn = accurate (needs GPU)
FACE_MODEL=hog
ENVEOF

    echo ""
    echo -e "  ${RED}${BOLD}ACTION REQUIRED:${RESET}"
    echo -e "  Edit .env and set your Pi 4's IP address:"
    echo -e "  ${BOLD}nano .env${RESET}"
    echo -e "  Change: ORION_API_URL=http://192.168.1.XX:8000"
    echo ""
    read -p "  Press Enter after editing .env..."
fi

# ── Read config ──
API_URL=$(grep "^ORION_API_URL" .env | cut -d'=' -f2 | tr -d ' \r')
echo -e "${GREEN}[CONFIG]${RESET} Brain (Pi 4): ${BOLD}${API_URL}${RESET}"

# ── Warn if not configured ──
if echo "$API_URL" | grep -q "XX\|localhost\|127.0.0.1"; then
    echo ""
    echo -e "${RED}┌─────────────────────────────────────────────────────────────┐${RESET}"
    echo -e "${RED}│  ORION_API_URL is not set to Pi 4's IP address.             │${RESET}"
    echo -e "${RED}│  Edit .env and replace 192.168.1.XX with Pi 4's actual IP.  │${RESET}"
    echo -e "${RED}└─────────────────────────────────────────────────────────────┘${RESET}"
    echo ""
    read -p "  Continue anyway? (y/N): " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || exit 1
fi

# ═══════════════════════════════════
# STEP 2: PYTHON ENVIRONMENT
# ═══════════════════════════════════
echo ""
echo -e "${CYAN}[2/4] Setting up Python environment...${RESET}"

if [ ! -d ".venv" ]; then
    echo -e "      First run — creating virtual environment..."
    echo -e "      ${YELLOW}This will take 5-15 minutes on Pi 3. Please wait.${RESET}"
    python3 -m venv .venv
    source .venv/bin/activate

    pip install --upgrade pip -q

    echo -e "      Installing Pi 3 body dependencies..."
    echo -e "      ${YELLOW}(lightweight — no AI frameworks, no Ollama)${RESET}"

    # Install system dependencies needed for face_recognition
    sudo apt-get install -y --no-install-recommends \
        libatlas-base-dev \
        libjasper-dev \
        libqtgui4 \
        libqt4-test \
        libhdf5-dev \
        libhdf5-serial-dev \
        libharfbuzz0b \
        libwebp-dev \
        libtiff5 \
        libopenexr-dev \
        libilmbase-dev \
        libgstreamer1.0-0 \
        libavcodec-dev \
        libavformat-dev \
        libswscale-dev \
        cmake \
        2>/dev/null || true

    pip install -r requirements_pi3.txt

    echo -e "${GREEN}      Dependencies installed.${RESET}"
else
    source .venv/bin/activate
    echo -e "${GREEN}      Virtual environment ready.${RESET}"
fi

# ═══════════════════════════════════
# STEP 3: WAIT FOR PI 4 BRAIN
# ═══════════════════════════════════
echo ""
echo -e "${CYAN}[3/4] Waiting for Pi 4 Brain to come online...${RESET}"

MAX_RETRIES=10
RETRY=0
BACKEND_OK=false

while [ $RETRY -lt $MAX_RETRIES ]; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "${API_URL}/" 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        BACKEND_OK=true
        break
    fi
    RETRY=$((RETRY + 1))
    echo -e "      Attempt $RETRY/$MAX_RETRIES — Pi 4 not ready yet (HTTP ${HTTP_CODE:-no response}). Retrying in 5s..."
    sleep 5
done

if [ "$BACKEND_OK" = true ]; then
    # Show Pi 4 AI status
    AI_STATUS=$(curl -s --connect-timeout 3 "${API_URL}/ai/status" 2>/dev/null \
        | python3 -c "import sys,json; d=json.load(sys.stdin); \
          providers=d.get('providers',{}); \
          print(', '.join([f'{k}: {\"OK\" if v[\"available\"] else \"DOWN\"}' for k,v in providers.items()]))" \
        2>/dev/null || echo "status unavailable")
    echo -e "${GREEN}      Pi 4 Brain connected!${RESET}"
    echo -e "${GREEN}      AI Providers: ${AI_STATUS}${RESET}"
else
    echo ""
    echo -e "${YELLOW}┌─────────────────────────────────────────────────────────────┐${RESET}"
    echo -e "${YELLOW}│  Pi 4 Brain unreachable after ${MAX_RETRIES} attempts.                  │${RESET}"
    echo -e "${YELLOW}│  ORION will run in OFFLINE mode (face recog only, no AI).   │${RESET}"
    echo -e "${YELLOW}│  Make sure Pi 4 is running: bash start_pi4_brain.sh         │${RESET}"
    echo -e "${YELLOW}└─────────────────────────────────────────────────────────────┘${RESET}"
    echo ""
    read -p "  Continue in offline mode? (y/N): " offline
    [[ "$offline" =~ ^[Yy]$ ]] || exit 1
fi

# ═══════════════════════════════════
# STEP 4: LAUNCH GUI
# ═══════════════════════════════════
echo ""
echo -e "${CYAN}[4/4] Launching ORION Dashboard...${RESET}"

# Pi 3 hardware environment
export PYTHONUNBUFFERED=1
export DISPLAY=:0
export QT_QPA_PLATFORM=xcb
export OPENCV_LOG_LEVEL=ERROR

# Audio device from .env
SPEAKER_IDX=$(grep "^SPEAKER_CARD_INDEX" .env | cut -d'=' -f2 | tr -d ' \r')
if [ -n "$SPEAKER_IDX" ]; then
    export SDL_AUDIODEV="plughw:${SPEAKER_IDX},0"
fi

# Use HOG face model (Pi 3 cannot run CNN)
export FACE_MODEL=hog

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "  ${GREEN}ORION Body online${RESET}"
echo -e "  Brain (Pi 4) : ${BOLD}${API_URL}${RESET}"
echo -e "  Face model   : ${BOLD}HOG (Pi 3 optimised)${RESET}"
echo -e "  TTS          : ${BOLD}gTTS (offline fallback active)${RESET}"
echo "═══════════════════════════════════════════════════════════════"
echo ""

python3 client/gui_client.py

echo ""
echo -e "${CYAN}[INFO]${RESET} ORION session ended."
