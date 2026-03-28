# ORION V6: Stability & Continuity Layer Design

## 1. The Scenario: "The Flapping Network"
**Condition**: The School Wi-Fi is unstable. The Pi connects, drops for 10 minutes, reconnects, drops again.
**Risks**:
- **Log Explosion**: Gigabytes of "Connection Error" logs.
- **Aggregation Spam**: "Welcome back. You missed 2 items" every 10 minutes.
- **Database Lock Churn**: Constant locking/unlocking of the same pending rows.

## 2. The Solution: "Session Continuity Protocol"

### A. The "Cool-Down" Logic (Server-Side)
We differentiate between a **Glitch** and an **Absence**.

1.  **Track Presence**: Server updates `clients` table with `last_heartbeat`.
2.  **Handshake Logic (`GET /sync`)**:
    *   `downtime = now - last_heartbeat`
    *   **Zone 1: The Glitch (< 30 mins)**:
        *   **Action**: Resume normal operation.
        *   **Delivery**: Send pending items individually (up to 10). **NO Summary.**
        *   *Rationale*: A 10-minute drop is just a pause. Don't annoy the user.
    *   **Zone 2: The Absence (> 2 hours)**:
        *   **Action**: Full Sync.
        *   **Delivery**: Trigger **Aggregation**. Generate "Welcome Back" summary.
        *   *Rationale*: Genuine absence requires context.

### B. Batch Transactions (Lock Churn Fix)
Instead of 10 separate interactions for 10 alerts, we use **Batching**.

1.  **Lock**: Server locks up to 50 pending items in **one transaction**.
2.  **Deliver**: Sends `List[Notification]` payload.
3.  **Ack**: Client processes all, then sends **one** `POST /ack_batch` with `[id1, id2, id3...]`.
4.  **Result**: 
    *   DB Transactions: Reduced by factor of N.
    *   Network Overhead: Reduced by factor of N.

### C. Exponential Backoff (Client-Side)
To prevent "Death Spirals" where the client hammers the server during instability.

1.  **Normal**: Poll every 30s.
2.  **Error 1**: Wait 30s.
3.  **Error 2**: Wait 60s.
4.  **Error 3+**: Wait 120s (Cap at 5 mins).
5.  **Recovery**: Reset to 30s on first success.

### D. Log Hygiene (Noise Cancellation)
Logs are for *new* information, not repetitive state.

*   **Rule**: If error is identical to previous error, **do not log**.
*   **Implementation**:
    ```python
    if current_error != last_error:
        bs_logger.error(current_error)
        last_error = current_error
    ```
*   **Success**: On reconnection, log a single line: `"Connection restored after X failures."`

## 3. Advanced Time Handling (No `sudo date`)
Modifying OS time is dangerous. We use **Offset Calculation**.

1.  **Handshake**: Client requests `/time`.
2.  **Calc**: `time_offset = server_time - local_system_time`.
3.  **Usage**: 
    *   When checking TTL: `if (local_now + time_offset) > expires_at_utc`.
    *   **Never change the OS clock.** This protects file systems and logs.

## 4. Final Architecture State
ORION V6 is now a **Resilient, Bandwidth-Efficient, Context-Aware Distributed System**. It gracefully handles:
- Power Loss (Transactional Outbox)
- Network Flapping (Session Continuity)
- Time Drift (Offset Sync)
- Data Floods (Aggregation)
