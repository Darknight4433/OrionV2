"""
ORION Usage Monitor v1.0

📊 Phase 2 Optimization: Real-world usage tracking
Logs patterns to identify optimization opportunities and behavior trends.
"""

import time
import json
import os
from datetime import datetime
from ..core.logging import get_logger

logger = get_logger()

class UsageMonitor:
    """Track real-world usage patterns for optimization."""
    
    STATS_FILE = "data/usage_stats.json"
    
    def __init__(self):
        self.session_start = time.time()
        self.stats = self._load_stats()
        
    def _load_stats(self) -> dict:
        """Load existing stats or create new."""
        if os.path.exists(self.STATS_FILE):
            try:
                with open(self.STATS_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            "total_queries": 0,
            "ollama_queries": 0,
            "gemini_queries": 0,
            "query_types": {},  # REALTIME, DYNAMIC_FACT, FACT, GENERAL
            "response_times": [],
            "tts_failures": 0,
            "most_used_commands": {},
            "session_count": 0,
            "last_updated": datetime.now().isoformat()
        }
    
    def _save_stats(self):
        """Save stats to file."""
        try:
            os.makedirs("data", exist_ok=True)
            with open(self.STATS_FILE, 'w') as f:
                json.dump(self.stats, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save usage stats: {e}")
    
    def log_query(self, query: str, query_type: str, ai_mode: str, response_time: float):
        """
        📊 Log a query and its response time.
        
        Args:
            query: User's input text
            query_type: REALTIME, DYNAMIC_FACT, FACT, GENERAL
            ai_mode: ollama, gemini, tinyllama
            response_time: Time in seconds
        """
        self.stats["total_queries"] += 1
        
        # Track by AI mode
        if ai_mode == "ollama":
            self.stats["ollama_queries"] += 1
        elif ai_mode == "gemini":
            self.stats["gemini_queries"] += 1
        
        # Track by query type
        self.stats["query_types"][query_type] = self.stats["query_types"].get(query_type, 0) + 1
        
        # Track response times (keep last 100)
        self.stats["response_times"].append(response_time)
        if len(self.stats["response_times"]) > 100:
            self.stats["response_times"].pop(0)
        
        # Track most used commands (first word)
        first_word = query.split()[0].lower() if query.split() else "unknown"
        self.stats["most_used_commands"][first_word] = self.stats["most_used_commands"].get(first_word, 0) + 1
        
        logger.info(f"📊 Query logged: type={query_type}, ai={ai_mode}, time={response_time:.2f}s")
        self._save_stats()
    
    def log_tts_failure(self):
        """Log a TTS failure."""
        self.stats["tts_failures"] += 1
        self._save_stats()
    
    def get_stats_summary(self) -> dict:
        """Get a summary of usage metrics."""
        if not self.stats["response_times"]:
            avg_time = 0
        else:
            avg_time = sum(self.stats["response_times"]) / len(self.stats["response_times"])
        
        return {
            "total_queries": self.stats["total_queries"],
            "avg_response_time": f"{avg_time:.2f}s",
            "ollama_usage": f"{(self.stats['ollama_queries'] / max(1, self.stats['total_queries']) * 100):.1f}%",
            "gemini_usage": f"{(self.stats['gemini_queries'] / max(1, self.stats['total_queries']) * 100):.1f}%",
            "query_distribution": self.stats["query_types"],
            "top_commands": sorted(self.stats["most_used_commands"].items(), key=lambda x: x[1], reverse=True)[:5],
            "tts_failures": self.stats["tts_failures"]
        }
    
    def log_session_end(self):
        """Log end of session."""
        session_duration = time.time() - self.session_start
        self.stats["session_count"] += 1
        self.stats["last_updated"] = datetime.now().isoformat()
        logger.info(f"📊 Session ended. Duration: {session_duration:.1f}s, Queries: {self.stats['total_queries']}")
        self._save_stats()

# Global instance
_usage_monitor = None

def get_monitor() -> UsageMonitor:
    """Get or create usage monitor instance."""
    global _usage_monitor
    if _usage_monitor is None:
        _usage_monitor = UsageMonitor()
    return _usage_monitor
