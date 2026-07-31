"""
Movement Service — ORION V2
============================
TinyLlama decides movement. Pi 3 B sends serial commands to ESP32.

Flow:
  Pi 3 A detects face/obstacle → WebSocket → Pi 3 B
  Pi 3 B → TinyLlama decision → serial command → ESP32 → motors

Serial Protocol (ESP32 expects):
  F:<speed>   — Forward  (speed 0-100)
  B:<speed>   — Backward
  L:<speed>   — Turn Left
  R:<speed>   — Turn Right
  S           — Stop
  G           — Greet (wave servo)
  H:<deg>     — Head turn (servo degrees)
"""

import re
import time
import requests
import serial
import serial.tools.list_ports
from ..core.logging import get_logger

logger = get_logger()


# ── Simple rule-based fallback (no TinyLlama needed for obvious cases) ──
RULE_MAP = {
    "person_close":    ("S", 0),       # Too close — stop
    "person_medium":   ("F", 30),      # Medium distance — move forward slowly
    "person_far":      ("F", 50),      # Far — move forward normally
    "person_left":     ("L", 40),      # Person to the left — turn left
    "person_right":    ("R", 40),      # Person to the right — turn right
    "no_person":       ("S", 0),       # Nobody visible — stop
    "obstacle":        ("S", 0),       # Obstacle detected — stop immediately
    "greeting":        ("G", 0),       # Greeting mode — wave
}

OLLAMA_URL = "http://localhost:11434"
MOVEMENT_MODEL = "tinyllama"

MOVEMENT_PROMPT = """You control a robot's movement. Reply with EXACTLY ONE word from this list:
FORWARD, BACKWARD, LEFT, RIGHT, STOP, GREET

Situation: {situation}

Rules:
- Person closer than 0.5m → STOP
- Person at 0.5-1.5m → FORWARD  
- Person detected during greeting → GREET
- No person visible → STOP
- Obstacle ahead → STOP
- Person to the left → LEFT
- Person to the right → RIGHT

Command (one word only):"""


class MovementService:

    def __init__(self, serial_port: str = None, baud_rate: int = 9600):
        self.serial_conn = None
        self._last_command = "S"
        self._last_command_time = 0
        self.MIN_COMMAND_INTERVAL = 0.5  # seconds between commands

        # Auto-detect ESP32 serial port
        port = serial_port or self._auto_detect_port()
        if port:
            try:
                self.serial_conn = serial.Serial(port, baud_rate, timeout=1)
                time.sleep(2)  # ESP32 reset delay
                logger.info(f"[MOVE] Serial connected: {port} @ {baud_rate}baud")
            except Exception as e:
                logger.warning(f"[MOVE] Serial failed: {e} — movement disabled")
        else:
            logger.warning("[MOVE] No ESP32 found — movement disabled (simulation mode)")

    def _auto_detect_port(self) -> str:
        """Find ESP32/Arduino on serial ports."""
        ports = serial.tools.list_ports.comports()
        for p in ports:
            desc = (p.description or "").lower()
            if any(x in desc for x in ["esp32", "ch340", "cp210", "arduino", "usb serial"]):
                logger.info(f"[MOVE] Auto-detected: {p.device} ({p.description})")
                return p.device
        # Fallback common ports
        import os
        for candidate in ["/dev/ttyUSB0", "/dev/ttyACM0", "/dev/ttyUSB1"]:
            if os.path.exists(candidate):
                return candidate
        return None

    # ──────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────

    def decide_and_move(self, situation: str) -> str:
        """
        Use TinyLlama to decide movement based on situation description.
        Falls back to rule-based if TinyLlama is unavailable.
        Returns the command sent.
        """
        # Rate limit — don't spam commands
        now = time.time()
        if (now - self._last_command_time) < self.MIN_COMMAND_INTERVAL:
            return self._last_command

        # Try TinyLlama first
        command = self._ask_tinyllama(situation)

        # Fallback to rules if TinyLlama failed
        if not command:
            command = self._rule_based(situation)

        self._execute(command)
        self._last_command = command
        self._last_command_time = time.time()
        return command

    def rule_based_move(self, event: str):
        """
        Instant rule-based movement — no AI, no latency.
        Use for time-critical decisions (obstacle avoidance).
        """
        cmd, speed = RULE_MAP.get(event, ("S", 0))
        self._execute(cmd, speed)
        logger.info(f"[MOVE] Rule: {event} → {cmd}:{speed}")

    def stop(self):
        self._execute("S", 0)

    def greet(self):
        self._execute("G", 0)

    def head_turn(self, degrees: int):
        """Turn head servo to face detected person."""
        self._send_raw(f"H:{max(0, min(180, degrees))}")

    # ──────────────────────────────────────────
    # TINYLLAMA DECISION
    # ──────────────────────────────────────────

    def _ask_tinyllama(self, situation: str) -> str:
        """Ask TinyLlama for a movement decision. Returns command string or None."""
        try:
            prompt = MOVEMENT_PROMPT.format(situation=situation)
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MOVEMENT_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,   # near-deterministic for commands
                        "num_predict": 5,      # only need 1 word
                        "stop": ["\n", " ", "."]
                    }
                },
                timeout=10
            )
            if response.status_code == 200:
                raw = response.json().get("response", "").strip().upper()
                # Extract first valid command word
                for cmd in ["FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP", "GREET"]:
                    if cmd in raw:
                        logger.info(f"[MOVE] TinyLlama: '{situation[:40]}' → {cmd}")
                        return cmd
        except Exception as e:
            logger.warning(f"[MOVE] TinyLlama unavailable: {e}")
        return None

    def _rule_based(self, situation: str) -> str:
        """Simple keyword rule fallback."""
        s = situation.lower()
        if "close" in s or "too near" in s:   return "STOP"
        if "obstacle" in s or "wall" in s:     return "STOP"
        if "left" in s:                        return "LEFT"
        if "right" in s:                       return "RIGHT"
        if "person" in s or "face" in s:       return "FORWARD"
        if "greet" in s or "hello" in s:       return "GREET"
        return "STOP"

    # ──────────────────────────────────────────
    # SERIAL EXECUTION
    # ──────────────────────────────────────────

    SPEED_MAP = {
        "FORWARD":  50,
        "BACKWARD": 40,
        "LEFT":     35,
        "RIGHT":    35,
        "STOP":     0,
        "GREET":    0,
    }

    def _execute(self, command: str, speed: int = None):
        if speed is None:
            speed = self.SPEED_MAP.get(command, 0)

        cmd_map = {
            "FORWARD":  f"F:{speed}",
            "BACKWARD": f"B:{speed}",
            "LEFT":     f"L:{speed}",
            "RIGHT":    f"R:{speed}",
            "STOP":     "S",
            "GREET":    "G",
        }
        raw = cmd_map.get(command, "S")
        self._send_raw(raw)

    def _send_raw(self, raw: str):
        logger.debug(f"[MOVE] → ESP32: {raw}")
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.write(f"{raw}\n".encode())
            except Exception as e:
                logger.error(f"[MOVE] Serial write failed: {e}")
        else:
            # Simulation mode — just log
            logger.info(f"[MOVE] (SIM) {raw}")

    def close(self):
        if self.serial_conn:
            self.stop()
            self.serial_conn.close()
