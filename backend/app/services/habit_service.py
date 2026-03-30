import sqlite3
import time
import json
from datetime import datetime
from .memory_service import MemoryService
from .logging import get_logger

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


class HabitDetector:
    """Track repeated actions and form habits."""
    def __init__(self, memory_service: MemoryService):
        self.memory = memory_service

    def observe(self, user_id: str, action: str, timestamp: float = None):
        now = timestamp if timestamp is not None else time.time()
        dt = datetime.fromtimestamp(now)
        bucket = get_time_bucket(dt.hour)
        self._store_event(user_id, action, bucket, now)

        count = self._get_event_count(user_id, action, bucket)
        if count >= 3:
            habit_text = f"{action} at {bucket}"
            self._update_or_create_habit(user_id, habit_text, count, now)

    def _store_event(self, user_id: str, action: str, bucket: str, timestamp: float):
        try:
            with sqlite3.connect(self.memory.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO habit_events (user_id, action, bucket, timestamp) VALUES (?, ?, ?, ?)",
                    (user_id, action, bucket, timestamp)
                )
                conn.commit()
        except Exception as e:
            # Don't fail the main flow for habit tracking
            logger.error(f"Habit store error: {e}")

    def _update_or_create_habit(self, user_id: str, habit_text: str, count: int, now: float):
        existing_habits = self.memory.get_memory_items(user_id, "habit", limit=50)
        habit_data = None
        for h in existing_habits:
            try:
                data = json.loads(h)
                if data.get("item") == habit_text:
                    habit_data = data
                    break
            except:
                continue
        
        if habit_data:
            # Update existing
            habit_data["count"] = max(habit_data["count"], count)
            habit_data["last_seen"] = now
            # Remove old entry and add updated
            self._remove_habit(user_id, habit_text)
        else:
            # Create new
            habit_data = {
                "item": habit_text,
                "count": count,
                "last_seen": now
            }
        
        self.memory.add_memory_item(user_id, "habit", json.dumps(habit_data))
        self.memory.trim_memory(user_id, "habit", max_items=10)

    def _remove_habit(self, user_id: str, habit_text: str):
        try:
            with sqlite3.connect(self.memory.db_path) as conn:
                cursor = conn.cursor()
                # Get all habit items, find the one to remove
                cursor.execute(
                    "SELECT id, content FROM memory_items WHERE user_id = ? AND category = 'habit'",
                    (user_id,)
                )
                rows = cursor.fetchall()
                for row in rows:
                    try:
                        data = json.loads(row[1])
                        if data.get("item") == habit_text:
                            cursor.execute("DELETE FROM memory_items WHERE id = ?", (row[0],))
                            break
                    except:
                        continue
                conn.commit()
        except Exception as e:
            logger.error(f"Remove habit error: {e}")
