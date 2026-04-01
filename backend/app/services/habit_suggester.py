import os
import time
import json
from datetime import datetime
from .memory_service import MemoryService
from ..core.logging import get_logger

logger = get_logger()

def get_time_bucket(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    else:
        return "night"

class HabitSuggester:
    """Suggest habits proactively based on time and patterns."""
    
    def __init__(self, memory_service: MemoryService):
        self.memory = memory_service
        self.last_suggested = {}  # Anti-spam: {user_habit: timestamp}
        self.daily_suggestions = {}  # {user: date_str} to track first suggestion today
        self.last_suggestion = {}  # {user: {"habit": habit, "time": ts}} for followup
        
        # Priority system for conflict resolution (school-focused)
        self.priority = {
            "study": 2,  # Lower for school use
            "work": 3,
            "code": 2,
            "eat": 1,
            "drink": 1,
            "sleep": 1,
            "meeting": 5,  # Higher for school
            "task": 4,
            "reminder": 4
        }

    def check_and_suggest(self, user_id: str, last_input_time: float = None, last_output_time: float = None) -> str:
        """Check if there's a habit to suggest at current time."""
        now = datetime.now()
        bucket = get_time_bucket(now.hour)
        
        # School hours: 8 AM - 3 PM, reduce suggestions
        is_school_hours = 8 <= now.hour < 15
        if is_school_hours:
            return None  # No habit suggestions during school hours
        
        habits = self.memory.get_memory_items(user_id, "habit")
        parsed_habits = []
        for h in habits:
            try:
                data = json.loads(h)
                parsed_habits.append(data)
            except:
                continue
        
        # Filter valid habits for current bucket + silent learning
        valid_habits = []
        for habit in parsed_habits:
            habit_text = habit.get("item", "")
            if bucket in habit_text and self._is_habit_valid(habit) and habit.get("count", 0) >= 4:  # Silent learning
                valid_habits.append(habit)
        
        if not valid_habits:
            return None
        
        # Conflict resolution: select highest priority
        best_habit = max(valid_habits, key=lambda h: self._get_priority(h))
        
        # Context-aware blocking
        if self._should_block_suggestion(user_id, last_input_time, last_output_time):
            return None
        
        if self._should_suggest(user_id, best_habit):
            mode = self._get_suggestion_mode(user_id)
            suggestion = self._format_suggestion(best_habit, mode)
            # Track for followup
            self.last_suggestion[user_id] = {"habit": best_habit, "time": time.time()}
            return suggestion
        
        return None

    def handle_followup(self, user_id: str, text: str) -> str:
        """Handle user response to last suggestion."""
        if user_id not in self.last_suggestion:
            return None
        
        elapsed = time.time() - self.last_suggestion[user_id]["time"]
        if elapsed > 60:  # 1 minute window
            return None
        
        text_lower = text.lower()

        # Quiet confirmation mode
        quiet = os.environ.get("ORION_ENVIRONMENT", "").lower() == "quiet"

        if any(w in text_lower for w in ["yes", "ok", "start", "sure", "please"]):
            if quiet:
                return "Understood, Sir."
            habit = self.last_suggestion[user_id]["habit"]
            action = habit.get("item", "").split(" at ")[0]
            if action == "study":
                return "Sir, starting your study timer."
            return f"Sir, proceeding with {action}."
        
        if any(w in text_lower for w in ["no", "later", "not now", "stop"]):
            return "Sir, understood. Let me know if you need assistance."
        
        return None

    def _is_habit_valid(self, habit: dict) -> bool:
        """Check if habit is valid (confidence, decay)."""
        confidence = habit.get("count", 0) / 5.0
        if confidence < 0.6:
            return False
        
        last_seen = habit.get("last_seen", 0)
        if time.time() - last_seen > 7 * 24 * 3600:
            return False
        
        return True

    def _get_priority(self, habit: dict) -> int:
        """Get priority for habit."""
        action = habit.get("item", "").split(" at ")[0]
        return self.priority.get(action, 0)

    def _should_block_suggestion(self, user_id: str, last_input_time: float, last_output_time: float) -> bool:
        """Context-aware blocking."""
        now = time.time()
        
        # Block if user recently spoke (within 20s)
        if last_input_time and now - last_input_time < 20:
            return True
        
        # Block if recent voice output (within 20s)
        if last_output_time and now - last_output_time < 20:
            return True
        
        # Block if recent command (approximate with last activity)
        last_activity = self.memory.get_last_activity(user_id)
        if last_activity and now - last_activity < 30:
            return True
        
        return False

    def _should_suggest(self, user_id: str, habit: dict) -> bool:
        """Anti-spam logic: don't suggest same habit within 1 hour. School mode: stricter."""
        key = f"{user_id}_{habit['item']}"
        now = time.time()
        
        if key in self.last_suggested and now - self.last_suggested[key] < 3600:  # 1 hour
            return False
        
        # School mode: only strong habits, reduce frequency
        if habit.get("count", 0) < 5:
            return False
        
        self.last_suggested[key] = now
        return True

    def _get_suggestion_mode(self, user_id: str) -> str:
        """Determine soft or hard mode based on first suggestion today."""
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"{user_id}_daily"
        
        if self.daily_suggestions.get(key) != today:
            self.daily_suggestions[key] = today
            return "soft"
        else:
            return "hard"

    def _format_suggestion(self, habit: dict, mode: str) -> str:
        """Convert habit to natural suggestion. School tone."""
        action = habit.get("item", "").split(" at ")[0]
        confidence = habit.get("count", 0)
        
        if mode == "soft":
            return f"Sir, it is around your usual {action} time."
        
        # Hard mode with confidence-based tone
        if confidence >= 5:
            if action == "study":
                return "Sir, it is your usual study time. Shall I start a timer?"
            return f"Sir, it is your usual {action} time. Would you like assistance?"
        else:
            return f"Sir, it is your usual {action} time."