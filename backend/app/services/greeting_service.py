import time
import random
import datetime
from typing import Dict, Optional
from .memory_service import MemoryService
from ..core.logging import get_logger

logger = get_logger()

class GreetingService:
    def __init__(self, memory_service: MemoryService):
        self.memory = memory_service
        self.last_greeted: Dict[str, float] = {}
        
        # Configuration (Synced from OMNIS_5)
        self.LONG_ABSENCE_THRESHOLD = 1800  # 30 minutes
        self.SHORT_COOLDOWN = 60            # 1 minute 

        self.nicknames = {
            "Vaishnavi": "vaaish",
            "Vaishnavi L": "vaaish",
            "sukumaran": "sir",
            "Deva Nandan":"deva",
            "shinila":"shinila",
            "pooja mam" : "mam",
        }
        
    def _get_time_of_day_greeting(self) -> str:
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12: return "Good morning"
        elif 12 <= hour < 17: return "Good afternoon"
        elif 17 <= hour < 21: return "Good evening"
        elif 21 <= hour < 24: return "Ooh, staying up late? Good evening"
        else: return "Hello"

    def should_greet(self, name: str) -> bool:
        if name == "Unknown":
            last = self.last_greeted.get("Unknown", 0)
            return (time.time() - last) > 30

        last = self.last_greeted.get(name, 0)
        return (time.time() - last) > self.SHORT_COOLDOWN

    def get_greeting(self, name: str) -> Optional[str]:
        if not self.should_greet(name):
            return None
            
        now = time.time()
        last = self.last_greeted.get(name, 0)
        self.last_greeted[name] = now
        
        time_greeting = self._get_time_of_day_greeting()
        
        # Long Absence -> Formal Greeting
        if last == 0 or (now - last) > self.LONG_ABSENCE_THRESHOLD:
            base = f"{time_greeting} {name}! Welcome to the ORION Executive System."
            if name == "Unknown":
                base = f"{time_greeting}! Welcome. I see a new face. How can I assist you?"
            else:
                # Proactive Memory Follow-up
                topic = self.memory.get_latest_topic(name)
                if topic and len(topic) > 10:
                    clean_topic = " ".join(topic.split()[:6]) + "..."
                    follow_ups = [
                        f" By the way, I was thinking about our chat about {clean_topic}.",
                        f" Also, I hope that discussion we had about {clean_topic} was helpful!",
                        f" It's good to see you again. I remember we were talking about {clean_topic} recently."
                    ]
                    base += random.choice(follow_ups)
            return base

        # Casual re-encounter
        return self._get_casual_greeting(name)

    def _get_casual_greeting(self, name: str) -> str:
        short_name = self.nicknames.get(name, name.split()[0] if " " in name else name)
        options = [
            f"Hi again {short_name}!",
            f"Welcome back {short_name}.",
            f"Good to see you {short_name}.",
            f"How is it going {short_name}?",
            f"Hello there {short_name}!"
        ]
        return random.choice(options)
