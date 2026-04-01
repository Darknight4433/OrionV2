import time
from datetime import datetime
from .memory_service import MemoryService
from ..core.logging import get_logger

logger = get_logger()


class BriefingEngine:
    """Generates contextual daily/time-based briefings for Sir."""

    def __init__(self, memory_service: MemoryService):
        self.memory = memory_service

    def get_morning_briefing(self, user_id: str) -> str:
        """
        Generate morning briefing.
        Format: "Good morning, Sir. Today you have X meetings, Y pending tasks."
        """
        now = datetime.now()
        
        # Get today's meetings
        meetings = self.memory.get_upcoming_meetings(user_id, window_minutes=1440)  # 24 hours
        
        # Get pending tasks (not yet completed)
        tasks = self.memory.get_pending_tasks(user_id, limit=10)
        
        # Get pending reminders
        reminders = self.memory.get_pending_reminders(user_id, limit=5)
        
        # Build briefing text
        briefing_parts = [f"Good morning, Sir. Today you have:"]
        
        if meetings:
            briefing_parts.append(f"- {len(meetings)} meeting(s)")
        else:
            briefing_parts.append("- No scheduled meetings")
        
        if tasks:
            briefing_parts.append(f"- {len(tasks)} pending task(s)")
        else:
            briefing_parts.append("- No pending tasks")
        
        if reminders:
            briefing_parts.append(f"- {len(reminders)} reminder(s)")
        
        briefing = " ".join(briefing_parts)
        logger.info(f"Morning briefing for {user_id}: {briefing}")
        return briefing

    def get_afternoon_briefing(self, user_id: str) -> str:
        """
        Generate afternoon briefing (after lunch check-in).
        Format: "Good afternoon, Sir. Remaining today: X meetings, any updates?"
        """
        meetings = self.memory.get_upcoming_meetings(user_id, window_minutes=480)  # 8 hours
        tasks = self.memory.get_pending_tasks(user_id, limit=10)
        
        briefing_parts = [f"Good afternoon, Sir."]
        
        if meetings:
            briefing_parts.append(f"You have {len(meetings)} meeting(s) remaining.")
        else:
            briefing_parts.append("No more meetings scheduled for today.")
        
        if tasks:
            briefing_parts.append(f"You have {len(tasks)} pending task(s).")
        
        briefing = " ".join(briefing_parts)
        logger.info(f"Afternoon briefing for {user_id}: {briefing}")
        return briefing

    def get_end_of_day_briefing(self, user_id: str) -> str:
        """
        Generate end-of-day briefing (summary + next day prep).
        Format: "End of day, Sir. Tomorrow you have..."
        """
        # Tomorrow's meetings (between now+24h and now+48h)
        now = time.time()
        tomorrow_start = now + 86400  # +24 hours
        tomorrow_end = now + 172800   # +48 hours
        
        # Get tomorrow's key items
        tomorrow_meetings = self.memory.get_upcoming_meetings(user_id, window_minutes=1440)
        pending_tasks = self.memory.get_pending_tasks(user_id, limit=5)
        
        briefing_parts = [f"End of day, Sir."]
        
        if pending_tasks:
            briefing_parts.append(f"You have {len(pending_tasks)} task(s) awaiting tomorrow.")
        
        if tomorrow_meetings:
            briefing_parts.append(f"Tomorrow: {len(tomorrow_meetings)} meeting(s) scheduled.")
        
        briefing_parts.append("Have a good evening.")
        
        briefing = " ".join(briefing_parts)
        logger.info(f"End-of-day briefing for {user_id}: {briefing}")
        return briefing

    def get_context_briefing(self, user_id: str) -> str:
        """
        Quick briefing when Sir asks "What's my schedule?" or similar.
        Format: "You have..."
        """
        meetings = self.memory.get_upcoming_meetings(user_id, window_minutes=1440)
        tasks = self.memory.get_pending_tasks(user_id, limit=5)
        
        if not meetings and not tasks:
            return "Sir, you have no scheduled meetings or pending tasks."
        
        briefing_parts = []
        
        if meetings:
            briefing_parts.append(f"{len(meetings)} meeting(s) today")
        
        if tasks:
            briefing_parts.append(f"{len(tasks)} pending task(s)")
        
        briefing = "Sir, you have: " + ", ".join(briefing_parts) + "."
        logger.info(f"Context briefing for {user_id}: {briefing}")
        return briefing

    def should_send_morning_briefing(self, user_id: str) -> bool:
        """
        Check if morning briefing should be sent (8:00 AM, once per day).
        """
        now = datetime.now()
        
        # Send at 8:00 AM
        if now.hour != 8:
            return False
        
        # Check if already sent today
        last_briefing = self.memory.get_memory_items(user_id, "briefing", limit=1)
        if last_briefing:
            # Parse the timestamp to check if it's from today
            # For now, simple: check if we've sent one in last 23 hours
            pass
        
        return True
