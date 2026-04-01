"""
🧠 ORION Usage Learning System v1.0

Phase 3: Learn from real usage patterns
Identifies shortcuts, optimizations, and behavior preferences
Customizes responses based on what Sir actually uses
"""

import json
import os
import time
from datetime import datetime
from ..core.logging import get_logger

logger = get_logger()

class UsageLearner:
    """Learn from real usage to optimize behavior."""
    
    PATTERNS_FILE = "data/usage_patterns.json"
    MAX_NEW_PATTERNS_PER_DAY = 3  # Learning limit to prevent over-adaptation
    
    def __init__(self):
        self.patterns = self._load_patterns()
        self.daily_pattern_count = 0
        self.last_reset_date = datetime.now().date()
    
    def _load_patterns(self) -> dict:
        """Load or initialize learned patterns."""
        if os.path.exists(self.PATTERNS_FILE):
            try:
                with open(self.PATTERNS_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            "command_shortcuts": {},  # "schedule" -> "call briefing"
            "ignored_suggestions": [],  # What suggestions are ignored
            "preferred_length": "medium",  # short, medium, long
            "repeat_commands": {},  # How often same command repeated
            "preferred_tone": "formal",  # formal, casual
            "query_patterns": {},  # Common question patterns
            "learned_at": datetime.now().isoformat()
        }
    
    def _reset_daily_count(self):
        """Reset daily pattern count if it's a new day."""
        today = datetime.now().date()
        if today != self.last_reset_date:
            self.daily_pattern_count = 0
            self.last_reset_date = today
    
    def apply_gradually(self, new_pattern: dict) -> bool:
        """
        Apply new learned pattern gradually to prevent sudden behavior changes.
        Returns True if pattern was applied, False if limit reached.
        """
        self._reset_daily_count()
        
        if self.daily_pattern_count >= self.MAX_NEW_PATTERNS_PER_DAY:
            logger.info(f"📚 Learning limit reached ({self.MAX_NEW_PATTERNS_PER_DAY} patterns/day). Delaying new pattern.")
            return False
        
        # Apply the pattern
        pattern_type = new_pattern.get("type")
        if pattern_type == "shortcut":
            self.patterns["command_shortcuts"][new_pattern["command"]] = new_pattern["action"]
        elif pattern_type == "tone":
            self.patterns["preferred_tone"] = new_pattern["tone"]
        elif pattern_type == "length":
            self.patterns["preferred_length"] = new_pattern["length"]
        
        self.daily_pattern_count += 1
        logger.info(f"📚 Applied new pattern gradually: {new_pattern} (#{self.daily_pattern_count}/{self.MAX_NEW_PATTERNS_PER_DAY})")
        self._save_patterns()
        return True
    
    def _save_patterns(self):
        """Save learned patterns."""
        try:
            os.makedirs("data", exist_ok=True)
            with open(self.PATTERNS_FILE, 'w') as f:
                json.dump(self.patterns, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save usage patterns: {e}")
    
    def log_command(self, command: str, is_repeat: bool = False):
        """Log a command to identify shortcuts."""
        first_word = command.split()[0].lower() if command.split() else "unknown"
        
        if is_repeat:
            self.patterns["repeat_commands"][first_word] = self.patterns["repeat_commands"].get(first_word, 0) + 1
            
            # If command repeated > 3 times, create shortcut
            if self.patterns["repeat_commands"][first_word] > 3:
                logger.info(f"📌 Learning shortcut for '{first_word}' (repeated {self.patterns['repeat_commands'][first_word]} times)")
        
        self._save_patterns()
    
    def learn_ignored_suggestion(self, suggestion: str):
        """Log a suggestion that was ignored."""
        self.patterns["ignored_suggestions"].append({
            "suggestion": suggestion,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only recent ignores (last 50)
        if len(self.patterns["ignored_suggestions"]) > 50:
            self.patterns["ignored_suggestions"] = self.patterns["ignored_suggestions"][-50:]
        
        logger.info(f"📝 Noted ignored suggestion: {suggestion[:50]}")
        self._save_patterns()
    
    def learn_response_length_preference(self, response_length: int):
        """Learn if Sir prefers short or long responses."""
        # Heuristic: if most responses are < 50 words, he prefers short
        current_pref = self.patterns["preferred_length"]
        new_pref = "short" if response_length < 50 else "long"
        
        if current_pref != new_pref:
            pattern = {"type": "length", "length": new_pref}
            if self.apply_gradually(pattern):
                logger.info("📚 Learning: Sir prefers short responses" if new_pref == "short" else "📚 Learning: Sir prefers detailed responses")
    
    def learn_tone(self, formal_score: float):
        """
        Learn preferred tone.
        formal_score: 0.0 = casual, 1.0 = formal
        """
        current_tone = self.patterns["preferred_tone"]
        
        if formal_score > 0.7:
            new_tone = "formal"
        elif formal_score < 0.3:
            new_tone = "casual"
        else:
            new_tone = "balanced"
        
        if current_tone != new_tone:
            pattern = {"type": "tone", "tone": new_tone}
            if self.apply_gradually(pattern):
                logger.info(f"📚 Learning: Sir prefers {new_tone} tone")
    
    def identify_command_shortcut(self) -> dict:
        """
        Identify if a frequently repeated command should have a shortcut.
        Returns: {command: shortcut_action}
        """
        shortcuts = {}
        repeat_commands = self.patterns["repeat_commands"]
        
        for cmd, count in repeat_commands.items():
            if count > 3:  # Repeated more than 3 times
                # Create context-aware shortcut
                if "schedule" in cmd.lower() or "today" in cmd.lower():
                    shortcuts[cmd] = "direct_briefing"
                    logger.info(f"🎯 Shortcut created: '{cmd}' -> direct briefing")
                
                elif "task" in cmd.lower() or "add" in cmd.lower():
                    shortcuts[cmd] = "quick_task_add"
                    logger.info(f"🎯 Shortcut created: '{cmd}' -> quick task add")
                
                elif "remind" in cmd.lower() or "reminder" in cmd.lower():
                    shortcuts[cmd] = "quick_reminder"
                    logger.info(f"🎯 Shortcut created: '{cmd}' -> quick reminder")
        
        return shortcuts
    
    def should_suggest(self, suggestion_type: str) -> bool:
        """
        Determine if a suggestion should be given.
        Based on historical ignore patterns.
        """
        # Count ignores for this suggestion type
        of_type = [s for s in self.patterns["ignored_suggestions"] if suggestion_type in s.get("suggestion", "").lower()]
        
        # If > 50% ignored, stop suggesting
        total_suggestions_attempted = max(1, len(self.patterns["ignored_suggestions"]))
        ignore_rate = len(of_type) / total_suggestions_attempted
        
        if ignore_rate > 0.5:
            logger.info(f"⚠️  Not suggesting '{suggestion_type}' (ignore rate: {ignore_rate:.1%})")
            return False
        
        return True
    
    def get_adaptation_rules(self) -> dict:
        """Get all learned adaptation rules."""
        shortcuts = self.identify_command_shortcut()
        
        return {
            "command_shortcuts": shortcuts,
            "preferred_length": self.patterns["preferred_length"],
            "preferred_tone": self.patterns["preferred_tone"],
            "suppress_suggestions": [s["suggestion"][:30] for s in self.patterns["ignored_suggestions"][-5:]],
            "repeat_commands": self.patterns["repeat_commands"],
            # Personality Lock: Always professional, calm, respectful, short
            "personality_lock": {
                "tone": "professional",
                "style": "calm",
                "address": "respectful",
                "length": "short"
            }
        }
    
    def get_learning_summary(self) -> dict:
        """Get summary of what system has learned."""
        return {
            "learned_shortcuts": len(self.identify_command_shortcut()),
            "ignored_suggestions_count": len(self.patterns["ignored_suggestions"]),
            "preferred_response_length": self.patterns["preferred_length"],
            "preferred_tone": self.patterns["preferred_tone"],
            "most_repeated_command": max(self.patterns["repeat_commands"].items(), key=lambda x: x[1], default=("none", 0))[0],
            "learned_at": self.patterns["learned_at"]
        }

# Global instance
_usage_learner = None

def get_learner() -> UsageLearner:
    """Get or create usage learner instance."""
    global _usage_learner
    if _usage_learner is None:
        _usage_learner = UsageLearner()
    return _usage_learner
