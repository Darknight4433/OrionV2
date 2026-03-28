#!/bin/bash

# ═══════════════════════════════════════════════
# ORION EXECUTIVE SYSTEM — PI LAUNCHER
# ═══════════════════════════════════════════════

# Set working directory to project root
cd "$(dirname "$0")"

# SAFETY CHECK: Ensure we are in the project root
if [ ! -f "client/gui_client.py" ]; then
    echo ""
    echo "[!] CRITICAL ERROR: 'start_pi.sh' cannot find the project files."
    echo ""
    echo "[TIP] Did you move this script out of the PROJECT-ORION folder?"
    echo "      Please keep it in the project root and run 'bash scripts/setup_pi_desktop.sh' "
    echo "      to create a proper Desktop Shortcut instead."
    echo ""
    read -p "Press enter to exit..."
    exit 1
fi

# 1. System Check (Pi Optimization)
echo "-----------------------------------------------"
echo "  ORION SYSTEM - RASPBERRY PI BOOT SEQUENCER   "
echo "-----------------------------------------------"

# Ensure directories exist
mkdir -p data logs images/faces

# 2. Virtual Environment Setup
if [ ! -d ".venv" ]; then
    echo "[!] .venv not found. Creating one..."
    python3 -m venv .venv
    source .venv/bin/activate
    echo "[+] Installing core dependencies..."
    pip install -U pip
    pip install loguru fastapi uvicorn requests python-dotenv opencv-python numpy face_recognition PyQt5 psutil pygame pyttsx3 SpeechRecognition google-generativeai sarvamai
else
    source .venv/bin/activate
fi

# 3. Handle PortAudio/ALSA Configuration (Pi Specific)
# This helps with audio latency and avoids most ALSA log spam
export PYTHONUNBUFFERED=1
export DISPLAY=:0 # Ensuring GUI has access to X11/FrameBuffer

# 4. Start Backend (Brain)
echo "[1/2] Initializing ORION Brain (FastAPI)..."
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 & 
BACKEND_PID=$!

# 5. Wait for backend stabilization
echo "      Waiting for boot sequence (12s)..."
sleep 12

# 6. Launch GUI Dashboard
echo "[2/2] Launching ORION CORE Dashboard..."
python3 client/gui_client.py

# Cleanup on exit
kill $BACKEND_PID
echo "ORION Session Safely Ended."
