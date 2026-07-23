import time
import datetime
from typing import Dict, Optional
from .memory_service import MemoryService
from ..core.logging import get_logger

logger = get_logger()


class GreetingService:
    """
    Generates personalized, time-aware greetings for each detected person.

    Multi-person logic:
    - Each person has their own independent cooldown timer.
    - When multiple people are detected together (Deva, Shinila, Vaishnavi),
      each gets their own greeting queued separately.
    - The greeting prompt includes the exact time so Ollama can say
      "Good morning Deva, it's 9 AM" or "Good evening Shinila, welcome back."
    - Last-seen time per person is tracked in memory so Ollama knows
      if they just arrived or came back after hours.
    """

    def __init__(self, memory_service: MemoryService):
        self.memory = memory_service

        # Per-person last greeted timestamp
        self._last_greeted: Dict[str, float] = {}

        # Cooldowns
        self.COOLDOWN_KNOWN   = 60    # 1 min — don't re-greet same person
        self.COOLDOWN_UNKNOWN = 30    # 30s for unknown faces
        self.LONG_ABSENCE     = 1800  # 30 min — triggers "welcome back" style

        self.nicknames = {
            "Vaishnavi": "Vaish",
            "Vaishnavi L": "Vaish",
        }

    def should_greet(self, name: str) -> bool:
        cooldown = self.COOLDOWN_UNKNOWN if name == "Unknown" else self.COOLDOWN_KNOWN
        last = self._last_greeted.get(name, 0)
        return (time.time() - last) > cooldown

    def get_greeting(self, name: str) -> Optional[str]:
        """
        Returns a time-aware greeting string for the given person.
        Called by the WebSocket handler when Pi 3 sends a face detection event.
        Each person is greeted independently — no shared state between people.
        """
        if not self.should_greet(name):
            return None

        now = time.time()
        self._last_greeted[name] = now

        # Build time context
        dt = datetime.datetime.now()
        time_str   = dt.strftime("%I:%M %p")   # "09:45 AM"
        time_of_day = self._time_of_day(dt.hour)

        # Check how long since last seen
        last_seen  = self._last_greeted.get(f"{name}__prev", 0)
        self._last_greeted[f"{name}__prev"] = now
        absence_sec = now - last_seen if last_seen > 0 else None

        short_name = self.nicknames.get(name, name.split()[0] if name != "Unknown" else None)

        if name == "Unknown":
            return f"{time_of_day}! I don't recognise you. Could you introduce yourself?"

        # Build greeting based on absence duration
        if absence_sec is None or absence_sec > self.LONG_ABSENCE:
            # First time or long absence — formal + time-aware
            topic = self.memory.get_latest_topic(name)
            greeting = f"{time_of_day} {short_name}! It's {time_str}. Welcome to the ORION system."
            if topic and len(topic) > 10:
                clean = " ".join(topic.split()[:6]) + "..."
                greeting += f" I remember we were discussing {clean} last time."
        else:
            # Short absence — casual
            absence_min = int(absence_sec / 60)
            if absence_min < 2:
                greeting = f"Welcome back {short_name}."
            else:
                greeting = f"Good to see you again {short_name}. Been about {absence_min} minutes."

        logger.info(f"[GREET] {name} at {time_str} → {greeting[:60]}")
        return greeting

    def _time_of_day(self, hour: int) -> str:
        if 5  <= hour < 12: return "Good morning"
        if 12 <= hour < 17: return "Good afternoon"
        if 17 <= hour < 21: return "Good evening"
        return "Hello"
