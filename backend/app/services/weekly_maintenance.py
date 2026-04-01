"""
🧹 ORION Weekly Maintenance Scheduler

Phase 3: Automatic cleanup every 7 days
Prevents long-term degradation through:
- Log rotation/archiving
- Stats trimming
- Old task cleanup
- Database optimization
"""

import os
import json
import time
import shutil
from datetime import datetime, timedelta
from ..core.logging import get_logger

logger = get_logger()

class WeeklyMaintenance:
    """Scheduled maintenance tasks."""
    
    MAINTENANCE_STATE_FILE = "data/maintenance_state.json"
    
    @staticmethod
    def _should_run_maintenance() -> bool:
        """Check if 7 days have passed since last maintenance."""
        try:
            if os.path.exists(WeeklyMaintenance.MAINTENANCE_STATE_FILE):
                with open(WeeklyMaintenance.MAINTENANCE_STATE_FILE, 'r') as f:
                    state = json.load(f)
                    last_run = state.get("last_run", 0)
                    now = time.time()
                    # 7 days = 604800 seconds
                    return (now - last_run) > 604800
        except:
            pass
        return True  # Run if unsure
    
    @staticmethod
    def _mark_maintenance_complete():
        """Record that maintenance just ran."""
        try:
            os.makedirs("data", exist_ok=True)
            with open(WeeklyMaintenance.MAINTENANCE_STATE_FILE, 'w') as f:
                json.dump({"last_run": time.time()}, f)
        except Exception as e:
            logger.error(f"Failed to mark maintenance complete: {e}")
    
    @staticmethod
    def archive_old_logs():
        """Archive logs older than 7 days."""
        try:
            logs_dir = "logs"
            archive_dir = "logs/archive"
            
            if not os.path.exists(archive_dir):
                os.makedirs(archive_dir)
            
            cutoff_time = time.time() - (7 * 24 * 3600)  # 7 days ago
            archived_count = 0
            
            for filename in os.listdir(logs_dir):
                if filename.endswith('.log'):
                    filepath = os.path.join(logs_dir, filename)
                    if os.path.getmtime(filepath) < cutoff_time:
                        try:
                            # Gzip and move
                            import gzip
                            archive_path = os.path.join(archive_dir, f"{filename}.gz")
                            with open(filepath, 'rb') as f_in:
                                with gzip.open(archive_path, 'wb') as f_out:
                                    f_out.write(f_in.read())
                            os.remove(filepath)
                            archived_count += 1
                        except Exception as e:
                            logger.error(f"Failed to archive {filename}: {e}")
            
            if archived_count > 0:
                logger.info(f"📦 Archived {archived_count} old log files")
        except Exception as e:
            logger.error(f"Log archival failed: {e}")
    
    @staticmethod
    def trim_usage_stats():
        """Keep only last 30 days of usage stats."""
        try:
            stats_file = "data/usage_stats.json"
            if os.path.exists(stats_file):
                with open(stats_file, 'r') as f:
                    stats = json.load(f)
                
                # Keep only recent response times (last 500 queries)
                if "response_times" in stats and len(stats["response_times"]) > 500:
                    stats["response_times"] = stats["response_times"][-500:]
                
                with open(stats_file, 'w') as f:
                    json.dump(stats, f, indent=2)
                
                logger.info(f"📊 Trimmed usage stats (kept last 500 queries)")
        except Exception as e:
            logger.error(f"Stats trimming failed: {e}")
    
    @staticmethod
    def cleanup_old_tasks():
        """Remove completed tasks older than 30 days."""
        try:
            from ..services.memory_service import MemoryService
            mem = MemoryService()
            
            import sqlite3
            cutoff = time.time() - (30 * 24 * 3600)  # 30 days ago
            
            with sqlite3.connect(mem.db_path) as conn:
                cursor = conn.cursor()
                # Delete old alerts marked as read/completed
                cursor.execute(
                    "DELETE FROM system_alerts WHERE timestamp < ? AND read_status = 1",
                    (cutoff,)
                )
                deleted = cursor.rowcount
                conn.commit()
                
                if deleted > 0:
                    logger.info(f"🗑️  Cleaned up {deleted} old tasks")
        except Exception as e:
            logger.error(f"Task cleanup failed: {e}")
    
    @staticmethod
    def optimize_database():
        """Vacuum and optimize database."""
        try:
            from ..services.memory_service import MemoryService
            mem = MemoryService()
            
            import sqlite3
            with sqlite3.connect(mem.db_path) as conn:
                conn.execute("VACUUM")
                cursor = conn.cursor()
                cursor.execute("PRAGMA optimize")
                conn.commit()
            
            logger.info("🗄️  Database optimized")
        except Exception as e:
            logger.error(f"Database optimization failed: {e}")
    
    @staticmethod
    def run_weekly_maintenance():
        """Execute all weekly maintenance tasks."""
        if not WeeklyMaintenance._should_run_maintenance():
            logger.info("⏭️  Weekly maintenance not due yet")
            return {"executed": False, "reason": "not_due"}
        
        logger.info("🧹 Starting weekly maintenance cycle...")
        
        try:
            WeeklyMaintenance.archive_old_logs()
            WeeklyMaintenance.trim_usage_stats()
            WeeklyMaintenance.cleanup_old_tasks()
            WeeklyMaintenance.optimize_database()
            
            WeeklyMaintenance._mark_maintenance_complete()
            
            logger.info("✅ Weekly maintenance complete")
            return {"executed": True, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            logger.error(f"Weekly maintenance failed: {e}")
            return {"executed": False, "error": str(e)}

# Export for scheduler
def weekly_maintenance_check() -> dict:
    """Wrapper for scheduler to call maintenance."""
    return WeeklyMaintenance.run_weekly_maintenance()
