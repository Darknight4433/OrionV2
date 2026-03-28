# ORION V4: Resilient Distributed Architecture Design

## 1. The Core Challenge
Running on a Raspberry Pi 24/7 implies inevitable hardware failures (power loss, SD card corruption, network partition). To guarantee **Reliability** (No lost reminders) and **Sanity** (No spam), we must move from a "Fire-and-Forget" model to a **Transactional State Machine**.

## 2. The Solution: "Transactional Outbox with Idempotent Client"

### A. Database Schema Upgrade (Server-Side)
We replace the simple `notified` flag with a dedicated `notification_outbox` table.

```sql
CREATE TABLE notification_outbox (
    uuid TEXT PRIMARY KEY,          -- Unique Idempotency Key
    event_id INTEGER,               -- Link to meeting
    payload TEXT,                   -- "Sir, meeting in 15 mins"
    status TEXT,                    -- PENDING, IN_FLIGHT, DELIVERED, FAILED
    attempt_count INTEGER DEFAULT 0,
    lock_expiration REAL,           -- Visibility timeout
    created_at REAL
);
```

### B. The Lifecycle (Power Failure Proof)

#### Phase 1: Scheduling (The Producer)
- **Action**: APScheduler finds a meeting.
- **Transaction**: Instead of speaking, it inserts a row into `notification_outbox` with `status='PENDING'`.
- **Guarantee**: Even if the scheduler crashes immediately, the *intent* is saved to disk.

#### Phase 2: Delivery (The Consumer)
- **Poll**: Client polls `/notifications`.
- **Locking**: Server finds `PENDING` items.
    - Updates status to `IN_FLIGHT`.
    - Sets `lock_expiration = now + 30s`.
    - Returns payload to Client.
- **Crash Scenario (Server dies here)**: The status is `IN_FLIGHT`. On restart, the lock expires. The recovery job sees an expired lock and resets it to `PENDING`. **Result: No loss.**

#### Phase 3: Execution & Acknowledgement (The Handshake)
- **Client**: Receives payload.
- **Client Check**: Checks local `processed_ids.log` (Idempotency Check).
    - *Case A (New)*: Speaks audio. Appends ID to log. Sends `ACK` to server.
    - *Case B (Duplicate)*: Sees ID in log (maybe crash happened before ACK sent). Skips audio. Sends `ACK` to server.
- **Server**: Receives `ACK`. Updates `status='DELIVERED'`.

### C. The "Power Cycle" Recovery Logic

**Scenario**: Power cuts at 9:55 AM. Returns at 10:10 AM. Meeting was at 10:00 AM.

1.  **System Boots**.
2.  **Recovery Worker Scans Outbox**:
    - Finds items where `status` is `PENDING` or `IN_FLIGHT`.
    - Checks `event_time`.
    - **Logic**:
        - If `event_time` is **Future**: Reset to `PENDING`. (Resumes normal reminder).
        - If `event_time` is **Past**: Mark as `FAILED`. Generate *new* notification: *"Sir, apologies using the recovery protocol. We missed the 10 AM meeting due to power failure."*

## 3. Guarantees Achieved

1.  **At-Least-Once Delivery**: The Server never marks a message `DELIVERED` until the Client confirms it. If the network or power fails mid-flight, the `lock_expiration` ensures it will be retried.
2.  **Idempotency (No Spam)**: The Client's local `processed_ids` log ensures that even if the Server retries (due to a lost ACK packet), the Client won't speak the same message twice.

## 4. Hardware Considerations (Raspberry Pi)
- **Write Durability**: SQLite on SD cards can corrupt on power loss.
- **Mitigation**: Enable `PRAGMA synchronous = FULL;` on SQLite. This ensures data is physically written to the disk platter (or NAND flash) before the transaction returns success. It slows down I/O but guarantees the `notification_outbox` survives the blackout.
