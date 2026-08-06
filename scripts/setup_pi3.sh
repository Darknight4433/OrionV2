#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  ORION V2 — Pi 3 FULL SETUP SCRIPT
#  Run once on a fresh Pi 3. Does everything.
#  Usage: bash scripts/setup_pi3.sh
# ═══════════════════════════════════════════════════════════════

set -e
ORION_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ORION_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'; BOLD='\033[1m'

echo ""
echo -e "${BOLD}  ORION V2 — Pi 3 Setup${RESET}"
echo "═══════════════════════════════════════════════"

# ── 1. System packages ──
echo -e "\n${GREEN}[1/5] Installing system packages...${RESET}"
sudo apt update -q
sudo apt install -y --no-install-recommends \
    python3-pip python3-venv python3-dev \
    cmake build-essential libopenblas-dev liblapack-dev \
    libx11-dev libgtk-3-dev libboost-all-dev \
    portaudio19-dev espeak \
    libavcodec-dev libavformat-dev libswscale-dev \
    libhdf5-dev \
    python3-pyqt5 curl git
echo -e "${GREEN}[OK] System packages installed${RESET}"

# ── 2. Virtual environment ──
echo -e "\n${GREEN}[2/5] Setting up Python environment...${RESET}"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q

# Try piwheels pre-built dlib first (no compilation needed)
echo -e "      Installing dlib (trying pre-built binary)..."
pip install dlib --extra-index-url https://www.piwheels.org/simple 2>/dev/null || {
    echo -e "${YELLOW}      Pre-built dlib failed. Trying system package copy...${RESET}"
    sudo apt install -y python3-dlib python3-face-recognition 2>/dev/null || true
    # Copy system dlib into venv
    PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    cp -r /usr/lib/python3/dist-packages/dlib* .venv/lib/python${PYVER}/site-packages/ 2>/dev/null || true
    cp -r /usr/lib/python3/dist-packages/face_recognition* .venv/lib/python${PYVER}/site-packages/ 2>/dev/null || true
    echo -e "${YELLOW}      Using system dlib. If face_recognition fails, run:${RESET}"
    echo -e "      sudo pip3 install --break-system-packages face-recognition"
}
pip install -r requirements_pi3.txt
pip install edge-tts groq
echo -e "${GREEN}[OK] Python deps installed${RESET}"

# ── 3. .env setup ──
echo -e "\n${GREEN}[3/5] Configuring .env...${RESET}"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${YELLOW}[!] Edit .env and set ORION_API_URL to your Windows/Pi4 IP${RESET}"
    echo ""
    read -p "  Enter brain IP (e.g. 192.168.1.100): " BRAIN_IP
    sed -i "s|ORION_API_URL=.*|ORION_API_URL=http://${BRAIN_IP}:8000|" .env
    echo -e "${GREEN}[OK] ORION_API_URL set to http://${BRAIN_IP}:8000${RESET}"
else
    echo -e "${GREEN}[OK] .env already exists${RESET}"
fi

# ── 4. Desktop shortcut ──
echo -e "\n${GREEN}[4/5] Creating desktop shortcut...${RESET}"
chmod +x orion_pi3.sh
DESKTOP_FILE="/home/$USER/Desktop/ORION.desktop"
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Name=ORION V2
Comment=ORION AI Assistant
Exec=bash ${ORION_DIR}/orion_pi3.sh
Icon=${ORION_DIR}/docs/orion_icon.png
Terminal=true
Type=Application
Categories=Utility;
EOF
chmod +x "$DESKTOP_FILE"
echo -e "${GREEN}[OK] Desktop shortcut created${RESET}"

# ── 5. Boot service ──
echo -e "\n${GREEN}[5/5] Setting up boot service...${RESET}"
# Replace /home/pi with actual user home in service file
sed "s|/home/pi|/home/$USER|g" scripts/orion.service | \
    sed "s|User=pi|User=$USER|g" > /tmp/orion.service
sudo cp /tmp/orion.service /etc/systemd/system/orion.service
sudo systemctl daemon-reload
sudo systemctl enable orion.service
echo -e "${GREEN}[OK] ORION will now start on boot${RESET}"

echo ""
echo "═══════════════════════════════════════════════"
echo -e "${BOLD}  Setup complete!${RESET}"
echo ""
echo "  To run now:     bash orion_pi3.sh"
echo "  To enable boot: sudo systemctl start orion"
echo "  To check logs:  journalctl -u orion -f"
echo "═══════════════════════════════════════════════"
