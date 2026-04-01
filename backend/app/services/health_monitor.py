"""
🏥 ORION Health Check System v1.0

Phase 3: Daily self-healing checks
Monitors: memory, response time, error rate, service health
Alerts DEV only if critical, never bothers Sir
"""

import time
import json
import os
import subprocess
from datetime import datetime
from ..core.logging import get_logger

logger = get_logger()

class HealthMonitor:
    """Silent background health checks."""
    
    HEALTH_FILE = "data/health_status.json"
    ALERT_THRESHOLD_RESPONSE_TIME = 3.0  # seconds
    ALERT_THRESHOLD_ERROR_RATE = 0.15  # 15%
    ALERT_THRESHOLD_MEMORY_GROWTH = 100  # MB per hour
    DEGRADED_PERFORMANCE_WINDOW = 3 * 3600  # 3 hours in seconds
    
    def __init__(self):
        self.health_status = self._load_health_status()
        self.last_check = time.time()
        self.degraded_start_time = None
        
    def _load_health_status(self) -> dict:
        """Load or initialize health status."""
        if os.path.exists(self.HEALTH_FILE):
            try:
                with open(self.HEALTH_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            "last_check": datetime.now().isoformat(),
            "response_time_avg": 0.0,
            "error_rate": 0.0,
            "memory_usage_mb": 0.0,
            "service_status": {
                "voice": "healthy",
                "memory": "healthy",
                "ollama": "unknown",
                "gemini": "unknown"
            },
            "alerts": []
        }
    
    def _save_health_status(self):
        """Save health status."""
        try:
            os.makedirs("data", exist_ok=True)
            with open(self.HEALTH_FILE, 'w') as f:
                json.dump(self.health_status, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save health status: {e}")
    
    def get_memory_usage_mb(self) -> float:
        """Get current process memory usage in MB."""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except:
            return 0.0
    
    def check_response_times(self, usage_stats: dict) -> tuple[float, bool]:
        """
        Check if response times are degrading.
        Returns: (avg_time, is_alert)
        """
        if not usage_stats.get("response_times"):
            return 0.0, False
            
        recent_times = usage_stats["response_times"][-20:]  # Last 20 queries
        avg_time = sum(recent_times) / len(recent_times)
        is_alert = avg_time > self.ALERT_THRESHOLD_RESPONSE_TIME
        
        if is_alert:
            logger.warning(f"🚨 HEALTH: Response time degraded to {avg_time:.2f}s (threshold: {self.ALERT_THRESHOLD_RESPONSE_TIME}s)")
        
        return avg_time, is_alert
    
    def check_error_rate(self, usage_stats: dict) -> tuple[float, bool]:
        """
        Check if error rate is too high.
        Returns: (error_rate, is_alert)
        """
        tts_failures = usage_stats.get("tts_failures", 0)
        total_queries = usage_stats.get("total_queries", 1)
        error_rate = tts_failures / max(1, total_queries)
        is_alert = error_rate > self.ALERT_THRESHOLD_ERROR_RATE
        
        if is_alert:
            logger.warning(f"🚨 HEALTH: Error rate {error_rate:.1%} (threshold: {self.ALERT_THRESHOLD_ERROR_RATE:.1%})")
        
        return error_rate, is_alert
    
    def check_degraded_performance(self, alerts: list) -> bool:
        """
        Check if system has been struggling repeatedly.
        Alert DEV if degraded for 3+ hours.
        """
        has_current_issues = len(alerts) > 0
        
        if has_current_issues:
            if self.degraded_start_time is None:
                self.degraded_start_time = time.time()
            elif time.time() - self.degraded_start_time >= self.DEGRADED_PERFORMANCE_WINDOW:
                logger.warning("⚠️ ORION degraded performance (3h)")
                return True
        else:
            self.degraded_start_time = None
        
        return False
    
    def check_memory_growth(self) -> tuple[float, bool]:
        """
        Check if memory is growing too fast.
        Returns: (memory_mb, is_alert)
        """
        current_memory = self.get_memory_usage_mb()
        prev_memory = self.health_status.get("memory_usage_mb", 0)
        
        # Check growth over last check interval
        memory_growth = current_memory - prev_memory
        time_elapsed_hours = (time.time() - self.last_check) / 3600
        growth_per_hour = memory_growth / max(time_elapsed_hours, 1)
        
        is_alert = growth_per_hour > self.ALERT_THRESHOLD_MEMORY_GROWTH and time_elapsed_hours > 0.1
        
        if is_alert:
            logger.warning(f"🚨 HEALTH: Memory growing at {growth_per_hour:.1f} MB/hour (current: {current_memory:.1f} MB)")
        
        return current_memory, is_alert
    
    def check_ollama_health(self) -> bool:
        """Check if Ollama server is responsive."""
        try:
            from ..integrations.ollama_client import is_server_alive
            alive = is_server_alive()
            status = "healthy" if alive else "down"
            self.health_status["service_status"]["ollama"] = status
            return alive
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            self.health_status["service_status"]["ollama"] = "error"
            return False
    
    def check_voice_service(self) -> bool:
        """Check if voice service can initialize."""
        try:
            from ..services.voice_service import SpeakerService
            speaker = SpeakerService()
            self.health_status["service_status"]["voice"] = "healthy"
            return True
        except Exception as e:
            logger.error(f"Voice service health check failed: {e}")
            self.health_status["service_status"]["voice"] = "error"
            return False
    
    def check_memory_service(self) -> bool:
        """Check if memory database is accessible."""
        try:
            from ..services.memory_service import MemoryService
            mem = MemoryService()
            # Try a simple query
            mem.get_user_facts("health_check")
            self.health_status["service_status"]["memory"] = "healthy"
            return True
        except Exception as e:
            logger.error(f"Memory service health check failed: {e}")
            self.health_status["service_status"]["memory"] = "error"
            return False
    
    def run_full_health_check(self, usage_stats: dict = None) -> dict:
        """
        Run complete health check.
        Returns alert summary.
        """
        logger.info("🏥 Running daily health check...")
        
        alerts = []
        
        # 1. Check response times
        avg_response, response_alert = self.check_response_times(usage_stats or {})
        self.health_status["response_time_avg"] = avg_response
        if response_alert:
            alerts.append(f"Slow responses: {avg_response:.2f}s")
        
        # 2. Check error rate
        error_rate, error_alert = self.check_error_rate(usage_stats or {})
        self.health_status["error_rate"] = error_rate
        if error_alert:
            alerts.append(f"High error rate: {error_rate:.1%}")
        
        # 3. Check memory
        memory_mb, memory_alert = self.check_memory_growth()
        self.health_status["memory_usage_mb"] = memory_mb
        if memory_alert:
            alerts.append(f"Memory leak suspected: {memory_mb:.1f} MB")
        
        # 4. Check services
        ollama_ok = self.check_ollama_health()
        voice_ok = self.check_voice_service()
        memory_ok = self.check_memory_service()
        
        if not ollama_ok:
            alerts.append("Ollama server down")
        if not voice_ok:
            alerts.append("Voice service error")
        if not memory_ok:
            alerts.append("Memory database error")
        
        # Update status
        self.health_status["last_check"] = datetime.now().isoformat()
        self.health_status["alerts"] = alerts[-5:]  # Keep last 5 alerts
        self._save_health_status()
        
        # Check for prolonged degradation
        degraded_alert = self.check_degraded_performance(alerts)
        if degraded_alert:
            alerts.append("Prolonged degradation detected")
        
        if alerts:
            logger.warning(f"🚨 HEALTH ALERTS: {alerts}")
        else:
            logger.info("✅ All systems healthy")
        
        return {
            "healthy": len(alerts) == 0,
            "alerts": alerts,
            "response_time": avg_response,
            "error_rate": error_rate,
            "memory_mb": memory_mb,
            "services": self.health_status["service_status"]
        }
    
    def get_health_summary(self) -> dict:
        """Get current health summary."""
        return {
            "last_check": self.health_status["last_check"],
            "response_time_avg": self.health_status["response_time_avg"],
            "error_rate": self.health_status["error_rate"],
            "memory_usage_mb": self.health_status["memory_usage_mb"],
            "services": self.health_status["service_status"],
            "recent_alerts": self.health_status["alerts"]
        }

# Global instance
_health_monitor = None

def get_health_monitor() -> HealthMonitor:
    """Get or create health monitor instance."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor
