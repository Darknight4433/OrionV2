import time
from ..core.logging import get_logger

logger = get_logger()


class PlannerEngine:
    """Expands single-action decisions into 2-step contextual plans."""

    def build_plan(self, action: dict, memory_service=None) -> dict:
        """
        Take a decision action and expand it with a helpful next step.
        Returns modified action dict with expanded text.
        """
        if not action:
            return None

        action_type = action.get("type")

        if action_type == "MEETING":
            return self._plan_meeting(action)
        elif action_type == "TASK":
            return self._plan_task(action)
        elif action_type == "REMINDER":
            return self._plan_reminder(action)
        elif action_type == "HABIT":
            return self._plan_habit(action)
        else:
            return action

    def _plan_meeting(self, action: dict) -> dict:
        """Meeting plan: add prep context based on urgency."""
        text = action.get("text", "")

        # Extract minutes until meeting if available
        try:
            # "Sir, your meeting is at 10:00 AM."
            # We could parse time, but for now use heuristics from text
            if "5 minute" in text or "starts in 5" in text:
                expanded = f"{text} Sir, you may want to proceed now."
            elif "10 minute" in text or "15 minute" in text:
                expanded = f"{text} Sir, you may want to review your notes."
            elif "30 minute" in text or "60 minute" in text:
                expanded = f"{text} Sir, you have time to prepare."
            else:
                # Safe default
                expanded = f"{text} Sir, I can help you prepare if needed."
        except Exception:
            expanded = f"{text} Sir, I can assist with preparation."

        action["text"] = expanded
        action["planned"] = True
        logger.info(f"Planner: MEETING expanded -> {expanded[:80]}")
        return action

    def _plan_task(self, action: dict) -> dict:
        """Task plan: escalate if overdue, encourage if pending."""
        text = action.get("text", "")

        if "still pending" in text or "overdue" in text:
            # Task is overdue or waiting
            expanded = (
                f"{text} Sir, this may require immediate "
                "attention when you are available."
            )
        elif "pending" in text:
            # General pending state
            expanded = f"{text} Sir, you can complete this when convenient."
        else:
            expanded = f"{text} Sir, let me know if you need assistance."

        action["text"] = expanded
        action["planned"] = True
        logger.info(f"Planner: TASK expanded -> {expanded[:80]}")
        return action

    def _plan_reminder(self, action: dict) -> dict:
        """Reminder plan: confirm action and offer follow-up."""
        text = action.get("text", "")

        expanded = f"{text} Sir, shall I set a note for this?"
        action["text"] = expanded
        action["planned"] = True
        logger.info(f"Planner: REMINDER expanded -> {expanded[:80]}")
        return action

    def _plan_habit(self, action: dict) -> dict:
        """Habit plan: soft assistance, non-intrusive."""
        text = action.get("text", "")

        # Keep habit suggestions soft and helpful
        if "timer" in text or "start" in text.lower():
            expanded = f"{text} I am ready to assist if needed."
        else:
            expanded = f"{text} Sir, I can help if you need support."

        action["text"] = expanded
        action["planned"] = True
        logger.info(f"Planner: HABIT expanded -> {expanded[:80]}")
        return action
