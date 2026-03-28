# ORION V7: Data Lifecycle & Retention Strategy

## 1. The Threat: State Explosion
A long-running system (months/years) faces "Data Rot":
1.  **Storage Creep**: SQLite grows indefinitely. Performance degrades. SD card fills up.
2.  **Privacy Liability**: Keeping 2 years of chat logs is a security risk.
3.  **Context Poisoning**: AI context window gets filled with irrelevant info from 6 months ago.

## 2. The Solution: "The Janitor Protocol"

We implement a tiered retention policy enforced by a scheduled **Maintenance Worker**.

### A. Retention Policies (The Rules)

| Data Type | Retention Period | Action | Reason |
| :--- | :--- | :--- | :--- |
| **Outbox / Alerts** | 7 Days | **Hard Delete** | If it wasn’t delivered in 7 days, it’s irrelevant. |
| **Chat History** | 30 Days | **Soft Delete** / Archive | Context is ephemeral. "Permanent" memories excepted. |
| **Completed Tasks** | 90 Days | **Archive** to JSON | Keep a record of productivity, but clear hot DB. |
| **System Logs** | 14 Days | **Rotate** (Loguru) | handled by file system rotation. |
| **Vector Embeddings** | Indefinite | **Re-index** Monthly | Remove embeddings for deleted content. |

### B. The Maintenance Job (Daily Cron)

Runs at **03:00 AM Local Time** (Low traffic).

1.  **Pruning**:
    ```sql
    DELETE FROM notification_outbox WHERE status IN ('DELIVERED', 'EXPIRED') AND created_at < (now - 7days);
    DELETE FROM conversation_history WHERE timestamp < (now - 30days) AND permanent = 0;
    ```
2.  **Archiving (Cold Storage)**:
    *   Dump old meetings/tasks to `data/archives/year_month.json`.
    *   `DELETE FROM meetings WHERE meeting_time < (now - 90days);`
3.  **Optimization**:
    *   Run `VACUUM;` on SQLite.
    *   Reclaims disk space from deleted rows (crucial for SD cards).

### C. Client-Side Lifecycle

The Client also accumulates state in `processed_ids.log`.

1.  **Log Rotation**:
    *   If `processed_ids.log` lines > 1000:
    *   Drop first 500 lines.
    *   *Why?* We only need IDs for the "Retry Window" (max 7 days). We don't need to prevent duplicates from last year.

## 3. Implementation Plan

1.  **Backend**: Add `prune_database()` to `MemoryService`.
2.  **Scheduler**: Add `DailyTrigger` for `03:00 AM`.
3.  **Client**: Add `cleanup_logs()` on startup.

## 4. Final System State
ORION V7 is now **Self-Cleaning**.
- It won't crash due to "Disk Full" after 2 years.
- It won't slow down due to a 1GB SQLite file.
- It remains compliant with data minimization principles.
