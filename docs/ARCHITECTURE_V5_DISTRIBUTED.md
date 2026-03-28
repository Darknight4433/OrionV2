# ORION V5: Distributed Cloud-Edge Architecture

## 1. The Scenario
- **Brain (Server)**: Cloud VPS (High uptime, exact time, persistent DB).
- **Body (Client)**: Raspberry Pi (Local network, unreliable power, no RTC).
- **Constraint**: Network may vanish for hours. Client may reboot into a "Time Blind" state (1970 date).

## 2. Adaptation: The "Smart Outbox" Protocol

The simple FIFO queue fails here because sending a "Meeting in 15 mins" alert *6 hours late* is worse than silence. The Outbox must become **Time-Aware**.

### A. Schema Evolution (Server-Side)
We add **Time-To-Live (TTL)** and **Priority** to the Outbox.

```sql
CREATE TABLE notification_outbox (
    uuid TEXT PRIMARY KEY,
    payload TEXT,
    event_time_utc REAL,       -- Actual event time
    expires_at_utc REAL,       -- Drop dead time (e.g., event_time + 15 mins)
    priority INTEGER,          -- 1 (Critical) to 3 (Info)
    status TEXT,               -- PENDING, EXPIRED, DELIVERED
    ...
);
```

### B. The Reconnection Strategy ("Welcome Back")

**Problem**: Pi reconnects after 6 hours. Queue has 50 missed items.
**Bad Approach**: Spamming 50 audio alerts.
**V5 Approach**: **Server-Side Aggregation**.

1.  **Handshake**: Client sends `GET /sync?last_id=...`
2.  **Server Analysis**:
    *   Query `notification_outbox` for user.
    *   **Filter 1 (TTL)**: Mark any item where `now > expires_at_utc` as `EXPIRED`. Do not send.
    *   **Filter 2 (Consolidation)**: If `EXPIRED` count > 3, generate a **Dynamic Summary**.
        *   *Before*: [Alert A, Alert B, Alert C, Alert D]
        *   *After*: "Welcome back. You were offline for 6 hours. You missed 4 meetings: A, B, C, and D."
3.  **Delivery**: Send the *Summary* payload instead of the raw queue.

### C. The "Time-Blind" Pi Fix

**Problem**: Pi reboots without internet/RTC. It thinks date is Jan 1, 1970. It rejects SSL certs. It miscalculates alarms.
**Solution**: **HTTP Time Sync**.

1.  **Boot**: Client blocks all logic until it reaches Cloud.
2.  **Handshake**: Client blindly trusts `Date` header from Cloud response.
3.  **Set System Time**: `sudo date -s '{server_date}'`.
4.  **Resume**: Only start Scheduler/Poller *after* time is synced.

### D. The "Ghost Client" Circuit Breaker

**Problem**: Cloud keeps generating notifications for a Pi that has been dead for weeks. Outbox bloats.
**Solution**: **Lease Limit**.

1.  Server tracks `last_seen` for Client.
2.  If `last_seen > 24 hours`:
    *   Pause Scheduler generation for this Client.
    *   Log: "Client dormant. Pausing non-critical alerts."
    *   Why? Saves DB space. Prevents "Doom Queue" on reconnection.

## 3. Guarantees in V5
- **No Stale Alerts**: The `expires_at_utc` ensures we never announce a past meeting as "upcoming".
- **No Alert Floods**: Aggregation logic turns a flood into a summary.
- **Trusted Time**: The Pi treats the Cloud as the Atomic Clock, solving the 1970 reboot issue.
