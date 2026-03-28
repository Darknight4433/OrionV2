#!/bin/bash

# ═══════════════════════════════════════════════
# ORION PI DESKTOP AUTO-LAUNCHER CREATOR
# ═══════════════════════════════════════════════

# Identify paths
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
ICON_PATH="$PROJECT_DIR/client/assets/orion_icon.png" # Assuming an icon exists or default
LAUNCHER_FILE="$HOME/Desktop/ORION.desktop"

echo "-----------------------------------------------"
echo "  ORION PI - Creating Desktop Launcher...      "
echo "-----------------------------------------------"

# Create the .desktop file on the Pi's Desktop
cat <<EOF > "$LAUNCHER_FILE"
[Desktop Entry]
Name=ORION Executive AI
Comment=Launch the ORION System
Exec=bash "$PROJECT_DIR/start_pi.sh"
Path=$PROJECT_DIR
Icon=utilities-terminal
Terminal=true
Type=Application
Categories=Development;
EOF

# Make both executable
chmod +x "$PROJECT_DIR/start_pi.sh"
chmod +x "$LAUNCHER_FILE"

echo "[OK] Launcher created at: $LAUNCHER_FILE"
echo "[TIP] You can now double-click the 'ORION' icon on your Desktop!"
echo "-----------------------------------------------"
