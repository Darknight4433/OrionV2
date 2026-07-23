#!/bin/bash

# ═══════════════════════════════════════════════════════════════
#  ORION — RASPBERRY PI 4 BRAIN LAUNCHER
#
#  ROLE  : AI Brain + Backend Server
#  RUNS  : Ollama (Gemma 3) + FastAPI + SQLite DB + Intent Router
#  DOES NOT run: Camera, Face Recognition, GUI, Microphone
#
#  Pi 3 connects to THIS Pi over your local network.
#
#  NETWORK SETUP:
#    1. Find this Pi 4's IP:  hostname -I
#    2. On the Pi 3, edit .env:
#         ORION_API_URL=http://<THIS_PI4_IP>:8000
#         OLLAMA_BASE_URL=http://<THIS_PI4_IP>:11434
#
#  FIRST RUN:
#    bash start_pi4_brain.sh
#    (Gemma 3 will be downloaded ~2.5GB — runs once)
# ═══════════════════════════════════════════════════════════════

set -e
cd "$(dirname "$0")"

# ── Colours ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

echo ""
echo -e "${CYAN}${BOLD}"
echo "  ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗"
echo "  ██╔══██╗██╔══██╗██║██╔═══██╗████╗  ██║"
echo "  ██║  ██║██████╔╝██║██║   ██║██╔██╗ ██║"
echo "  ██║  ██║██╔══██╗██║██║   ██║██║╚██╗██║"
echo "  ██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║"
echo "  ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝"
echo -e "${RESET}"
echo -e "${BOLD}  RASPBERRY PI 4 — BRAIN NODE${RESET}"
echo -e "  Role: Ollama + Gemma 3 + FastAPI Backend"
echo "═══════════════════════════════════════════════════════════════"

# ── Show this Pi's IP ──
PI4_IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${GREEN}[NET]${RESET} This Pi 4's IP address: ${BOLD}${PI4_IP}${RESET}"
echo -e "      On Pi 3, set in .env:"
echo -e "        ORION_API_URL=http://${PI4_IP}:8000"
echo -e "        OLLAMA_BASE_URL=http://${PI4_IP}:11434"
echo ""

# ── Required directories ──
mkdir -p data logs

# ═══════════════════════════════════
# STEP 1: OLLAMA SETUP
# ═══════════════════════════════════
echo -e "${CYAN}[1/4] Checking Ollama...${RESET}"

if ! command -v ollama &>/dev/null; then
    echo -e "${YELLOW}      Ollama not found. Installing...${RESET}"
    curl -fsSL https://ollama.com/install.sh | sh
    echo -e "${GREEN}      Ollama installed.${RESET}"
else
    echo -e "${GREEN}      Ollama already installed: $(ollama --version)${RESET}"
fi

# ── Start Ollama server (bound to all interfaces so Pi 3 can reach it) ──
# Kill any existing instance first
pkill -f "ollama serve" 2>/dev/null || true
sleep 1

echo -e "      Starting Ollama server on 0.0.0.0:11434..."
# OLLAMA_HOST=0.0.0.0 makes it accessible from other devices on the network
OLLAMA_HOST=0.0.0.0 nohup ollama serve > logs/ollama.log 2>&1 &
OLLAMA_PID=$!
echo $OLLAMA_PID > /tmp/orion_ollama.pid
sleep 4  # Let Ollama initialise

# ── Pull Gemma 3 if not present ──
echo -e "${CYAN}[2/4] Checking Gemma 3 model...${RESET}"
if ! ollama list 2>/dev/null | grep -q "gemma3"; then
    echo -e "${YELLOW}      Gemma 3 not found. Downloading (~2.5GB)...${RESET}"
    echo -e "      This only happens once."
    ollama pull gemma3
    echo -e "${GREEN}      Gemma 3 ready.${RESET}"
else
    echo -e "${GREEN}      Gemma 3 already installed.${RESET}"
fi

# ── Quick sanity check — test model responds ──
echo -e "      Testing Gemma 3 response..."
TEST_RESPONSE=$(echo '{"model":"gemma3","messages":[{"role":"user","content":"hi"}],"stream":false}' \
    | curl -s -X POST http://localhost:11434/api/chat \
    -H "Content-Type: application/json" \
    -d @- | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['message']['content'][:50])" 2>/dev/null)

if [ -n "$TEST_RESPONSE" ]; then
    echo -e "${GREEN}      Model OK: \"${TEST_RESPONSE}\"${RESET}"
else
    echo -e "${YELLOW}      Model test inconclusive — continuing anyway.${RESET}"
fi

# ═══════════════════════════════════
# STEP 2: PYTHON ENVIRONMENT
# ═══════════════════════════════════
echo ""
echo -e "${CYAN}[3/4] Setting up Python environment...${RESET}"

if [ ! -d ".venv" ]; then
    echo -e "      Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate

    echo -e "      Installing backend dependencies..."
    pip install --upgrade pip -q
    pip install -r requirements_pi4.txt -q
    echo -e "${GREEN}      Dependencies installed.${RESET}"
else
    source .venv/bin/activate

    # Silent update check
    pip install -r requirements_pi4.txt -q --upgrade 2>/dev/null || true
    echo -e "${GREEN}      Virtual environment ready.${RESET}"
fi

# ── Write Pi 4 specific .env if not present ──
if [ ! -f ".env" ]; then
    echo -e "      Creating .env for Pi 4..."
    cat > .env << ENVEOF
# ORION Pi 4 Brain Configuration
GEMINI_API_KEYS=[]
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3
OPENROUTER_API_KEY=
SARVAM_API_KEYS=[]
ELEVENLABS_API_KEY=
SPEAKER_CARD_INDEX=1
FACE_MODEL=hog
ENVEOF
    echo -e "${GREEN}      .env created.${RESET}"
fi

# ── Ensure Ollama model is set to gemma3 in .env ──
if grep -q "OLLAMA_MODEL" .env; then
    sed -i 's/OLLAMA_MODEL=.*/OLLAMA_MODEL=gemma3/' .env
else
    echo "OLLAMA_MODEL=gemma3" >> .env
fi

# ── Ensure Ollama URL is localhost (it's running locally on Pi 4) ──
if grep -q "OLLAMA_BASE_URL" .env; then
    sed -i 's|OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=http://localhost:11434|' .env
else
    echo "OLLAMA_BASE_URL=http://localhost:11434" >> .env
fi

# ═══════════════════════════════════
# STEP 3: START FASTAPI BACKEND
# ═══════════════════════════════════
echo ""
echo -e "${CYAN}[4/4] Starting ORION Backend...${RESET}"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "  ${GREEN}ORION Brain is starting on ${BOLD}${PI4_IP}:8000${RESET}"
echo -e "  AI Model  : ${BOLD}Gemma 3 4B (via Ollama)${RESET}"
echo -e "  API Docs  : ${BOLD}http://${PI4_IP}:8000/docs${RESET}"
echo -e "  Streaming : ${BOLD}http://${PI4_IP}:8000/stream${RESET}"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo -e "  ${YELLOW}Pi 3 body should connect to: http://${PI4_IP}:8000${RESET}"
echo ""

# Trap to clean up Ollama on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}[SHUTDOWN] Stopping Ollama...${RESET}"
    kill $(cat /tmp/orion_ollama.pid 2>/dev/null) 2>/dev/null || pkill -f "ollama serve"
    echo "[SHUTDOWN] ORION Brain stopped."
}
trap cleanup EXIT INT TERM

# Start FastAPI — bound to 0.0.0.0 so Pi 3 can reach it
# Run from backend/ so "app.main" package resolves correctly
cd backend
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --loop asyncio \
    --log-level info
