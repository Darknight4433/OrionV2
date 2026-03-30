import time
from datetime import datetime
from .memory_service import MemoryService
from .habit_suggester import HabitSuggester
from .logging import get_logger

logger = get_logger()

PRIORITY = {
    "MEETING": 5,
    "TASK": 4,
    "REMINDER": 4,
    "HABIT": 2
}

class DecisionEngine:
    """Deterministic planner for one best action."""

    def __init__(self, memory_service: MemoryService, habit_suggester: HabitSuggester):
        self.memory = memory_service
        self.habit_suggester = habit_suggester

    def _urgency(self, event_time: float) -> int:
        now = time.time()
        minutes = (event_time - now) / 60.0

        if minutes <= 5:
            return 5
        if minutes <= 15:
            return 4
        if minutes <= 60:
            return 3
        return 1

    def choose_best_action(self, user_id: str, last_input_time: float = None, last_output_time: float = None) -> dict | None:
        candidates = []

        # 1. Meetings (high priority)
        for m in self.memory.get_upcoming_meetings(user_id, window_minutes=60):
            urgency_score = self._urgency(m.get("scheduled_time", time.time()))
            candidates.append({
                "type": "MEETING",
                "text": f"Sir, your meeting is at {datetime.fromtimestamp(m.get('scheduled_time', time.time())).strftime('%I:%M %p')}.",
                "score": PRIORITY["MEETING"] + urgency_score
            })

        # 2. Tasks (pending) - lower urgency but still important
        for t in self.memory.get_pending_tasks(user_id, limit=10):
            candidates.append({
                "type": "TASK",
                "text": f"Sir, you have a pending task: {t.get('content')}",
                "score": PRIORITY["TASK"]
            })

        # 3. Reminders
        for r in self.memory.get_pending_reminders(user_id, limit=10):
            urgency_score = self._urgency(r.get("scheduled_time", time.time()))
            candidates.append({
                "type": "REMINDER",
                "text": f"Sir, reminder: {r.get('content')}",
                "score": PRIORITY["REMINDER"] + urgency_score
            })

        # 4. Habit suggestion (if no higher urgency command applies)
        habit_suggestion = self.habit_suggester.check_and_suggest(user_id, last_input_time, last_output_time)
        if habit_suggestion:
            candidates.append({
                "type": "HABIT",
                "text": habit_suggestion,
                "score": PRIORITY["HABIT"]
            })

        if not candidates:
            return None

        best = max(candidates, key=lambda c: c["score"])
        logger.info(f"DecisionEngine chose {best['type']} with score {best['score']}: {best['text']}")
        return best