#!/bin/bash
# ORION Heartbeat Watchdog
# Run this via cron every minute: * * * * * /home/pi/PROJECT-ORION/watchdog.sh

HEARTBEAT_FILE="/tmp/orion_heartbeat"
TIMEOUT=60

if [ -f "$HEARTBEAT_FILE" ]; then
    LAST_UPDATE=$(cat "$HEARTBEAT_FILE")
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - LAST_UPDATE))

    if [ $ELAPSED -gt $TIMEOUT ]; then
        echo "$(date): ORION heartbeat stale ($ELAPSED seconds) - restarting services" >> /home/pi/PROJECT-ORION/logs/watchdog.log
        sudo systemctl restart orion-client
        sudo systemctl restart orion-backend
    fi
else
    echo "$(date): No heartbeat file found - starting services" >> /home/pi/PROJECT-ORION/logs/watchdog.log
    sudo systemctl start orion-backend
    sudo systemctl start orion-client
fi