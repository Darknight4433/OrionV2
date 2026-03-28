from loguru import logger
import shutil
import os
import sys
import threading
import time
import signal

class LifecycleManager:
    _instance = None
    SAFE_MODE = False
    _lock = threading.Lock()
    _stop_event = threading.Event()
    
    # Configuration
    CRITICAL_LIMIT_MB = 200  # Enter Safe Mode
    RECOVERY_LIMIT_MB = 350  # Exit Safe Mode (Hysteresis)
    POLL_INTERVAL_S = 10     # Check every 10 seconds

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LifecycleManager, cls).__new__(cls)
            cls._instance.start_monitor()
        return cls._instance

    def start_monitor(self):
        """Starts the background disk monitor thread."""
        t = threading.Thread(target=self._monitor_loop, daemon=True)
        t.start()
        logger.info("Lifecycle Monitor started (Background).")

    def _monitor_loop(self):
        while not self._stop_event.is_set():
            try:
                self.check_disk_pressure()
            except Exception as e:
                logger.error(f"Monitor Error: {e}")
            time.sleep(self.POLL_INTERVAL_S)

    @classmethod
    def check_disk_pressure(cls):
        """Background worker logic."""
        try:
            total, used, free = shutil.disk_usage("/")
            free_mb = free / (1024 * 1024)
            
            with cls._lock:
                if not cls.SAFE_MODE and free_mb < cls.CRITICAL_LIMIT_MB:
                    logger.critical(f"LOW DISK ({free_mb:.2f}MB). Entering SAFE MODE.")
                    cls.enter_safe_mode()
                
                elif cls.SAFE_MODE and free_mb > cls.RECOVERY_LIMIT_MB:
                    logger.info(f"Disk Recovered ({free_mb:.2f}MB). Exiting SAFE MODE.")
                    cls.exit_safe_mode()
                
                # THE LAST RESORT: Deadlock detected (Safe Mode stuck & Critical)
                if cls.SAFE_MODE and free_mb < 50:
                    logger.critical("DISK CRITICAL (<50MB). ATTEMPTING EMERGENCY RESTART.")
                    cls.trigger_emergency_restart()

        except Exception as e:
            # Fallback to safe mode only on error
            pass

    @classmethod
    def is_safe_mode(cls):
        return cls.SAFE_MODE

    @classmethod
    def enter_safe_mode(cls):
        cls.SAFE_MODE = True
        logger.remove()
        logger.add(sys.stderr, level="CRITICAL")
        # Trigger cleanup immediately in background (or separate thread)
        threading.Thread(target=cls.perform_emergency_cleanup).start()

    @classmethod
    def exit_safe_mode(cls):
        cls.SAFE_MODE = False
        # Restore Logging (Must match logging.py for consistency)
        logger.remove()
        logger.add("logs/orion.log", rotation="20 MB", retention="30 days", level="INFO")
        logger.add("logs/orion_errors.log", rotation="20 MB", retention="90 days", level="ERROR")

    @classmethod
    def perform_emergency_cleanup(cls):
        """Tiered deletion."""
        try:
            # Tier 1: Logs
            log_dir = "logs"
            if os.path.exists(log_dir):
                for f in os.listdir(log_dir):
                    if "log." in f:
                        os.remove(os.path.join(log_dir, f))
            # Additional tiers...
        except: pass

    @classmethod
    def trigger_emergency_restart(cls):
        """
        THE LAST RESORT: Force Restart.
        Releases file locks (Zombie Readers).
        Allows startup to run 'wal_checkpoint(TRUNCATE)'.
        """
        # In Docker/Systemd, exit(1) triggers restart.
        logger.critical("INITIATING SELF-TERMINATION FOR RECOVERY.")
        os.kill(os.getpid(), signal.SIGTERM)
