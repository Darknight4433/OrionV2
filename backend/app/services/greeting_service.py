"""
Greeting Service — OMNIS-style logic for ORION
================================================
Scenarios:
  A. VIP / Special intro  — custom honorific greeting for known dignitaries
  B. Long absence >30min  — formal greeting + memory follow-up
  C. Recent re-encounter  — casual nickname greeting (1-30 min)
  D. Just left & returned — if out of frame <2 min, say nothing (cooldown)
  E. Unknown visitor      — generic time-aware welcome

Guards (same as OMNIS):
  • Won't greet if ORION is currently speaking
  • Known faces: 2 min cooldown minimum
  • Unknown faces: 30s cooldown
  • Re-entry within 10s: completely ignored (just stepped out of frame)
"""

import time
import random
import datetime
from typing import Dict, Optional
from .memory_service import MemoryService
from ..core.logging import get_logger

logger = get_logger()


class GreetingService:

    # Cooldowns
    RE_ENTRY_IGNORE   = 10     # seconds — ignore if just stepped out of frame
    SHORT_COOLDOWN    = 120    # 2 minutes — casual re-greeting cooldown
    UNKNOWN_COOLDOWN  = 30     # 30 seconds for unknown faces
    LONG_ABSENCE      = 1800   # 30 minutes — triggers formal greeting

    # Nicknames (same as OMNIS)
    NICKNAMES = {
        "Vaishnavi":   "Vaish",
        "Vaishnavi L": "Vaish",
        "Deva Nandan": "Deva",
        "Aswathy":     "Aswathy",
        "Shinila":     "Shinila",
        "PK Sukumaran Sir": "Sir",
        "Babu Rajeev P R":  "Sir",
        "Saju P M":    "Sir",
    }

    # VIP / Special intros — custom honorific greetings
    SPECIAL_INTROS = {
        "PK Sukumaran Sir": "Welcome Sir. It is an honor to have you here.",
        "Babu Rajeev P R":  "Good to see you Sir. Welcome.",
        "Narendra Modi":    "Welcome! What an honor to have such a distinguished guest.",
        "Ibrahim":          "Welcome Ibrahim Sir. It is an honor to have you visit.",
        "Rakesh N K":       "Hello Rakesh Sir! Welcome.",
        "Saju P M":         "Welcome Sir. Good to have you here.",
    }

    def __init__(self, memory_service: MemoryService):
        self.memory = memory_service
        # Per-person: last greeted timestamp
        self._last_greeted: Dict[str, float] = {}
        # Per-person: last time they were seen in frame (for re-entry detection)
        self._last_seen:    Dict[str, float] = {}

    def notify_seen(self, name: str):
        """Call every time a face is detected — tracks last-seen for re-entry logic."""
        self._last_seen[name] = time.time()

    def should_greet(self, name: str) -> bool:
        now = time.time()
        cooldown = self.UNKNOWN_COOLDOWN if name == "Unknown" else self.SHORT_COOLDOWN
        last_greeted = self._last_greeted.get(name, 0)

        # Just stepped out and came back within RE_ENTRY_IGNORE seconds — skip
        last_seen = self._last_seen.get(name, 0)
        time_out_of_frame = now - last_seen
        if 0 < time_out_of_frame < self.RE_ENTRY_IGNORE:
            return False

        return (now - last_greeted) > cooldown

    def get_greeting(self, name: str) -> Optional[str]:
        """
        Returns greeting string or None if cooldown not expired.
        Called by WebSocket handler when Pi 3 sends face detection event.
        """
        if not self.should_greet(name):
            return None

        now = time.time()
        last_greeted = self._last_greeted.get(name, 0)
        self._last_greeted[name] = now

        time_of_day = self._time_of_day()
        dt = datetime.datetime.now()
        time_str = dt.strftime("%I:%M %p")

        # ── Scenario E: Unknown ──
        if name == "Unknown":
            return f"{time_of_day}! Welcome. I don't recognise you — could you introduce yourself?"

        short_name = self.NICKNAMES.get(name, name.split()[0])
        absence_sec = now - last_greeted if last_greeted > 0 else None

        # ── Scenario A: VIP / Special intro ──
        if name in self.SPECIAL_INTROS:
            return self.SPECIAL_INTROS[name]

        # ── Scenario B: First time today or long absence (>30 min) ──
        if absence_sec is None or absence_sec > self.LONG_ABSENCE:
            greeting = f"{time_of_day} {short_name}! Welcome to the ORION system."
            # Proactive memory follow-up
            topic = self.memory.get_latest_topic(name)
            if topic and len(topic) > 10:
                clean = " ".join(topic.split()[:6]) + "..."
                options = [
                    f" By the way, I was thinking about our chat about {clean}",
                    f" I hope that discussion we had about {clean} was helpful!",
                    f" I remember we were talking about {clean} recently.",
                ]
                greeting += random.choice(options)
            logger.info(f"[GREET-B] {name}: {greeting[:60]}")
            return greeting

        # ── Scenario C: Recent re-encounter (2-30 min) ──
        absence_min = int(absence_sec / 60)
        casual_options = [
            f"Hi again {short_name}!",
            f"Welcome back {short_name}.",
            f"Good to see you {short_name}.",
            f"How is it going {short_name}?",
        ]
        greeting = random.choice(casual_options)
        logger.info(f"[GREET-C] {name} (absent {absence_min}min): {greeting}")
        return greeting

    def _time_of_day(self) -> str:
        h = datetime.datetime.now().hour
        if   5  <= h < 12: return "Good morning"
        elif 12 <= h < 17: return "Good afternoon"
        elif 17 <= h < 21: return "Good evening"
        elif 21 <= h < 24: return "Ooh, staying up late? Good evening"
        else:              return "Hello"
