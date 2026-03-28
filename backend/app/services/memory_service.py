import sqlite3
import time
import os
from .config import settings, PROJECT_ROOT
from .logging import get_logger

logger = get_logger()

class MemoryService:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(PROJECT_ROOT, "data", "orion.db")
        self._init_db()

    def _init_db(self):
        """Initialize tables with WAL mode for SD card durability."""
        try:
            if not os.path.exists(os.path.dirname(self.db_path)):
                os.makedirs(os.path.dirname(self.db_path))
                
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA temp_store=MEMORY;")
                
                cursor = conn.cursor()
                # Conversation history
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS conversation_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL,
                        user_id TEXT,
                        user_message TEXT,
                        ai_message TEXT,
                        permanent INTEGER DEFAULT 0
                    )
                ''')
                # User facts
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_facts (
                        user_id TEXT,
                        fact_key TEXT,
                        fact_value TEXT,
                        last_updated REAL,
                        PRIMARY KEY (user_id, fact_key)
                    )
                ''')

                # Notifications / Meetings table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS system_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        content TEXT,
                        alert_type TEXT,
                        scheduled_time REAL,
                        read_status INTEGER DEFAULT 0
                    )
                ''')
                
                # Check for permanent column (migration)
                try:
                    cursor.execute("ALTER TABLE conversation_history ADD COLUMN permanent INTEGER DEFAULT 0")
                except: pass
                
                conn.commit()
        except Exception as e:
            logger.error(f"DB Init Error: {e}")

    def add_conversation(self, user_id: str, user_msg: str, ai_msg: str, permanent: bool = False):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO conversation_history (timestamp, user_id, user_message, ai_message, permanent) VALUES (?, ?, ?, ?, ?)",
                    (time.time(), user_id, user_msg, ai_msg, 1 if permanent else 0)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"DB Write Error: {e}")

    def get_recent_history(self, user_id: str, limit: int = 10):
        """Get last N exchanges within 4 hours or permanent."""
        cutoff_time = time.time() - (4 * 3600)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT user_message, ai_message 
                    FROM conversation_history 
                    WHERE user_id = ? 
                    AND (timestamp > ? OR permanent = 1)
                    ORDER BY timestamp DESC 
                    LIMIT ?
                    """,
                    (user_id, cutoff_time, limit)
                )
                rows = cursor.fetchall()
                return rows[::-1]
        except Exception as e:
            logger.error(f"DB Read Error: {e}")
            return []

    def store_fact(self, user_id: str, key: str, value: str):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO user_facts (user_id, fact_key, fact_value, last_updated) VALUES (?, ?, ?, ?)",
                    (user_id, key, value, time.time())
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Fact Store Error: {e}")

    def get_user_facts(self, user_id: str):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT fact_key, fact_value FROM user_facts WHERE user_id = ?", (user_id,))
                facts = cursor.fetchall()
                return {k: v for k, v in facts}
        except Exception as e:
            logger.error(f"Fact Retrieval Error: {e}")
            return {}

    def get_latest_topic(self, user_id: str):
        """Fetch the latest significant topic for follow-up."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_message FROM conversation_history 
                    WHERE user_id = ? 
                    AND length(user_message) > 15
                    ORDER BY timestamp DESC LIMIT 1
                ''', (user_id,))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Latest Topic Error: {e}")
            return None

    def check_missed_meetings(self):
        """Find alerts that should have fired but haven't."""
        now = time.time()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, content FROM system_alerts WHERE scheduled_time < ? AND read_status = 0",
                    (now,)
                )
                return cursor.fetchall()
        except Exception:
            return []

    def get_pending_notifications(self, user_id: str = "default_user"):
        """Serve unread alerts to the client."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT content FROM system_alerts WHERE (user_id = ? OR user_id = 'all') AND read_status = 0",
                    (user_id,)
                )
                alerts = [r[0] for r in cursor.fetchall()]
                # Mark as read immediately to avoid repeats
                cursor.execute(
                    "UPDATE system_alerts SET read_status = 1 WHERE (user_id = ? OR user_id = 'all') AND read_status = 0",
                    (user_id,)
                )
                conn.commit()
                return alerts
        except Exception:
            return []

    def run_maintenance(self):
        """The Janitor: Cleans old logs and optimizes DB."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Clean history older than 30 days unless permanent
                cutoff = time.time() - (30 * 24 * 3600)
                conn.execute("DELETE FROM conversation_history WHERE timestamp < ? AND permanent = 0", (cutoff,))
                conn.execute("VACUUM")
                logger.info("Memory Janitor finished maintenance.")
        except Exception as e:
            logger.error(f"Maintenance Error: {e}")

    def add_task(self, details: str, user_id: str = "default_user"):
        """Store a task or meeting in the system_alerts table."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO system_alerts (user_id, content, alert_type, scheduled_time) VALUES (?, ?, ?, ?)",
                    (user_id, details, "task", time.time())
                )
                conn.commit()
                logger.info(f"Task stored: {details}")
        except Exception as e:
            logger.error(f"Add Task Error: {e}")
