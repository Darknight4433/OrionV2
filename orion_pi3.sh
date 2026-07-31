#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  ORION V2 — Pi 3 Single Launcher
#  Place on desktop or run at boot via systemd
#  Runs: ORION GUI dashboard (face recog + voice + display)
# ═══════════════════════════════════════════════════════════════

set -e
ORION_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ORION_DIR"

# ── Display ──
export DISPLAY=:0
export QT_QPA_PLATFORM=xcb
export OPENCV_LOG_LEVEL=ERROR
export PYTHONUNBUFFERED=1
export FACE_MODEL=hog

# ── Audio ──
SPEAKER_IDX=$(grep "^SPEAKER_CARD_INDEX" .env 2>/dev/null | cut -d'=' -f2 | tr -d ' \r')
[ -n "$SPEAKER_IDX" ] && export SDL_AUDIODEV="plughw:${SPEAKER_IDX},0"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ORION V2 — Pi 3 Body"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Check .env ──
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[!] Created .env from template"
    echo "    Edit .env and set ORION_API_URL to your Windows/Pi4 IP"
    echo "    Then run this script again"
    exit 1
fi

# ── Activate venv ──
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "[OK] Virtual environment active"
else
    echo "[SETUP] Creating virtual environment (first run, ~15 min)..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements_pi3.txt
    pip install edge-tts groq
    echo "[OK] Dependencies installed"
fi

# ── Wait for backend ──
API_URL=$(grep "^ORION_API_URL" .env | cut -d'=' -f2 | tr -d ' \r')
echo "[NET] Connecting to brain: $API_URL"
for i in $(seq 1 10); do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "$API_URL/" 2>/dev/null)
    [ "$CODE" = "200" ] && echo "[OK] Brain connected" && break
    echo "      Attempt $i/10 — waiting..."
    sleep 3
done

# ── Launch dashboard ──
echo "[GO] Launching ORION Dashboard..."
python3 client/gui_client.py

echo "[INFO] ORION session ended."
