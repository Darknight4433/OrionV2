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
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS memory_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        category TEXT,
                        content TEXT,
                        timestamp REAL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS habit_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        action TEXT,
                        bucket TEXT,
                        timestamp REAL
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

    def add_memory_item(self, user_id: str, category: str, item: str):
        """Store classified memory item for user."""
        if category not in {"preference", "habit", "fact"}:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO memory_items (user_id, category, content, timestamp) VALUES (?, ?, ?, ?)",
                    (user_id, category, item.strip(), time.time())
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Add Memory Item Error: {e}")

    def get_memory_items(self, user_id: str, category: str = None, limit: int = 10):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if category:
                    cursor.execute(
                        "SELECT content FROM memory_items WHERE user_id = ? AND category = ? ORDER BY timestamp DESC LIMIT ?",
                        (user_id, category, limit)
                    )
                else:
                    cursor.execute(
                        "SELECT category, content FROM memory_items WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                        (user_id, limit)
                    )
                rows = cursor.fetchall()
                if category:
                    return [row[0] for row in rows]
                return [{"category": row[0], "content": row[1]} for row in rows]
        except Exception as e:
            logger.error(f"Get Memory Items Error: {e}")
            return []

    def get_last_activity(self, user_id: str):
        """Fetch the timestamp of the latest conversation for the user."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT MAX(timestamp) FROM conversation_history WHERE user_id = ?",
                    (user_id,)
                )
                row = cursor.fetchone()
                return row[0] if row and row[0] else None
        except Exception as e:
            logger.error(f"Get Last Activity Error: {e}")
            return None

    def is_duplicate_memory(self, user_id: str, category: str, item: str) -> bool:
        """Check whether a memory item already exists with the same category and overlapping content."""
        if category not in {"preference", "habit", "fact"}:
            return False
        existing = self.get_memory_items(user_id, category=category, limit=50)
        norm_item = item.strip().lower()
        for existing_item in existing:
            if norm_item in existing_item.lower() or existing_item.lower() in norm_item:
                return True
        return False

    def trim_memory(self, user_id: str, category: str, max_items: int = 10):
        """Trim memory items to keep per-category history bounded."""
        if category not in {"preference", "habit", "fact"}:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM memory_items WHERE user_id = ? AND category = ? ORDER BY timestamp DESC",
                    (user_id, category)
                )
                rows = cursor.fetchall()
                if len(rows) > max_items:
                    ids_to_delete = [r[0] for r in rows[max_items:]]
                    cursor.executemany(
                        "DELETE FROM memory_items WHERE id = ?",
                        [(i,) for i in ids_to_delete]
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"Trim Memory Error: {e}")

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

    def add_system_alert(self, user_id: str, content: str, alert_type: str = "general", scheduled_time: float = None):
        """Add a system alert/notification."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                st = scheduled_time if scheduled_time is not None else time.time()
                cursor.execute(
                    "INSERT INTO system_alerts (user_id, content, alert_type, scheduled_time) VALUES (?, ?, ?, ?)",
                    (user_id, content, alert_type, st)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Add System Alert Error: {e}")

    def add_task(self, details: str, user_id: str = "default_user", scheduled_time: float = None):
        """Store a task or meeting in the system_alerts table."""
        try:
            alert_type = "task"
            if details.strip().lower().startswith("meeting"):
                alert_type = "meeting"
            st = scheduled_time if scheduled_time is not None else time.time()
            self.add_system_alert(user_id, details, alert_type, st)
            logger.info(f"{alert_type.title()} stored: {details}")
        except Exception as e:
            logger.error(f"Add Task Error: {e}")

    def get_recent_tasks(self, user_id: str, limit: int = 5):
        """Get recent tasks for context."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT content FROM system_alerts WHERE user_id = ? AND alert_type = 'task' ORDER BY scheduled_time DESC LIMIT ?",
                    (user_id, limit)
                )
                tasks = cursor.fetchall()
                return [task[0] for task in tasks]
        except Exception as e:
            logger.error(f"Get Tasks Error: {e}")
            return []

    def get_upcoming_meetings(self, user_id: str, window_minutes: int = 60):
        """Get meetings that are due within the given window."""
        try:
            now = time.time()
            cutoff = now + (window_minutes * 60)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT content, scheduled_time FROM system_alerts WHERE user_id = ? AND alert_type = 'meeting' AND scheduled_time BETWEEN ? AND ? ORDER BY scheduled_time",
                    (user_id, now, cutoff)
                )
                rows = cursor.fetchall()
                return [{"content": r[0], "scheduled_time": r[1]} for r in rows]
        except Exception as e:
            logger.error(f"Get Meetings Error: {e}")
            return []

    def get_pending_tasks(self, user_id: str, limit: int = 10):
        """Get pending tasks (non-meeting)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT content, scheduled_time FROM system_alerts WHERE user_id = ? AND alert_type = 'task' ORDER BY scheduled_time DESC LIMIT ?",
                    (user_id, limit)
                )
                rows = cursor.fetchall()
                return [{"content": r[0], "scheduled_time": r[1]} for r in rows]
        except Exception as e:
            logger.error(f"Get Pending Tasks Error: {e}")
            return []

    def get_pending_reminders(self, user_id: str, limit: int = 10):
        """Get pending reminders."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT content, scheduled_time FROM system_alerts WHERE user_id = ? AND alert_type = 'reminder' ORDER BY scheduled_time DESC LIMIT ?",
                    (user_id, limit)
                )
                rows = cursor.fetchall()
                return [{"content": r[0], "scheduled_time": r[1]} for r in rows]
        except Exception as e:
            logger.error(f"Get Pending Reminders Error: {e}")
            return []

    def get_last_activity(self, user_id: str):
        """Get timestamp of last user activity."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT MAX(timestamp) FROM conversation_history WHERE user_id = ?",
                    (user_id,)
                )
                row = cursor.fetchone()
                return row[0] if row and row[0] else None
        except Exception as e:
            logger.error(f"Get Last Activity Error: {e}")
            return None
