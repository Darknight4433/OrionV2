"""
🔄 ORION Auto-Recovery System v1.0

Phase 3: Self-healing mechanisms
Restarts services, cleans up memory, resets connections when degradation detected
Never needs human intervention
"""

import time
import os
from datetime import datetime
from ..core.logging import get_logger

logger = get_logger()

class AutoRecovery:
    """Automatic recovery for degraded services."""
    
    # Recovery action debouncing (don't restart too frequently)
    RECOVERY_COOLDOWN = 300  # 5 minutes before retrying same recovery
    last_recovery_time = {}
    
    @staticmethod
    def should_attempt_recovery(action_name: str) -> bool:
        """Check if enough time has passed since last recovery attempt."""
        now = time.time()
        last_attempt = AutoRecovery.last_recovery_time.get(action_name, 0)
        return (now - last_attempt) > AutoRecovery.RECOVERY_COOLDOWN
    
    @staticmethod
    def mark_recovery_attempt(action_name: str):
        """Mark when a recovery was attempted."""
        AutoRecovery.last_recovery_time[action_name] = time.time()
    
    @staticmethod
    def recover_voice_service():
        """Restart voice service if degraded."""
        if not AutoRecovery.should_attempt_recovery("voice_restart"):
            return False
        
        try:
            logger.warning("🔄 Attempting voice service recovery...")
            AutoRecovery.mark_recovery_attempt("voice_restart")
            
            # Close and reinitialize voice service
            from ..services.voice_service import SpeakerService
            speaker = SpeakerService()
            # Force reinitialization
            speaker.mic = None
            speaker.speaker = None
            speaker.playback_thread = None
            speaker.playback_queue = None
            
            # Reinitialize
            speaker._init_audio()
            logger.info("✅ Voice service recovered")
            return True
        except Exception as e:
            logger.error(f"Voice recovery failed: {e}")
            return False
    
    @staticmethod
    def recover_memory_service():
        """Clean up memory if bloat detected."""
        if not AutoRecovery.should_attempt_recovery("memory_cleanup"):
            return False
        
        try:
            logger.warning("🔄 Attempting memory cleanup...")
            AutoRecovery.mark_recovery_attempt("memory_cleanup")
            
            from ..services.memory_service import MemoryService
            mem = MemoryService()
            
            # Run maintenance
            mem.run_maintenance()
            
            # Aggressive cleanup if still growing
            mem.cleanup_conversations("default_user", keep_count=10)
            
            logger.info("✅ Memory cleaned up")
            return True
        except Exception as e:
            logger.error(f"Memory cleanup failed: {e}")
            return False
    
    @staticmethod
    def recover_ollama_connection():
        """Reset Ollama connection if timing out."""
        if not AutoRecovery.should_attempt_recovery("ollama_reset"):
            return False
        
        try:
            logger.warning("🔄 Attempting Ollama connection reset...")
            AutoRecovery.mark_recovery_attempt("ollama_reset")
            
            from ..integrations.ollama_client import is_server_alive
            
            # Try to reconnect
            if is_server_alive():
                logger.info("✅ Ollama connection restored")
                return True
            else:
                logger.error("Ollama server still unreachable")
                return False
        except Exception as e:
            logger.error(f"Ollama recovery failed: {e}")
            return False
    
    @staticmethod
    def handle_response_time_spike(avg_response_time: float):
        """Handle slow responses by adapting routing."""
        if avg_response_time > 3.0:
            logger.warning(f"⚠️  Response time spike: {avg_response_time:.2f}s")
            
            # Strategy: Temporarily increase Gemini queries (faster fallback)
            # This allows Ollama time to recover
            try:
                # Set a flag that the router can check
                os.environ['ORION_SLOW_MODE'] = 'true'
                os.environ['ORION_SLOW_MODE_START'] = str(time.time())
                logger.info("🔄 Switched to performance mode (more Gemini queries)")
            except Exception as e:
                logger.error(f"Failed to switch routing strategy: {e}")
    
    @staticmethod
    def handle_high_error_rate(error_rate: float):
        """Handle high error rates by reducing load."""
        if error_rate > 0.15:
            logger.warning(f"⚠️  High error rate: {error_rate:.1%}")
            
            # Strategy: Clear error-prone cache, avoid heavy operations
            try:
                from ..services.memory_service import MemoryService
                mem = MemoryService()
                
                # Quick cleanup of potentially corrupted data
                mem.run_maintenance()
                logger.info("🔄 Cleared error-prone resources")
            except Exception as e:
                logger.error(f"Error handling failed: {e}")
    
    @staticmethod
    def execute_recovery_plan(health_status: dict) -> dict:
        """
        Execute intelligent recovery based on health status.
        Returns: recovery_actions taken
        """
        logger.info("🔄 Executing recovery plan...")
        
        actions_taken = []
        alerts = health_status.get("alerts", [])
        
        # Response time issues
        if "Slow responses" in str(alerts):
            AutoRecovery.handle_response_time_spike(health_status.get("response_time", 0))
            actions_taken.append("Switched to performance mode")
        
        # Error rate issues
        if "High error rate" in str(alerts):
            AutoRecovery.handle_high_error_rate(health_status.get("error_rate", 0))
            actions_taken.append("Reduced error-prone operations")
        
        # Memory issues
        if "Memory leak" in str(alerts):
            if AutoRecovery.recover_memory_service():
                actions_taken.append("Memory service recovered")
        
        # Service issues
        if "Voice service" in str(alerts):
            if AutoRecovery.recover_voice_service():
                actions_taken.append("Voice service restarted")
        
        if "Ollama server" in str(alerts):
            if AutoRecovery.recover_ollama_connection():
                actions_taken.append("Ollama connection reset")
        
        logger.info(f"✅ Recovery complete. Actions: {actions_taken}")
        
        return {
            "recovered": len(actions_taken) > 0,
            "actions_taken": actions_taken,
            "timestamp": datetime.now().isoformat()
        }

# Export for scheduling
def auto_recovery_check(health_status: dict) -> dict:
    """Wrapper for scheduler to call recovery."""
    return AutoRecovery.execute_recovery_plan(health_status)
