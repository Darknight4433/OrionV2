# ORION System Failure Diagnostic Manual

## Scenario: "Missed Reminder" (Scheduler claims success, User claims silence)

### 1. Backend Verification (The Source)
**Goal:** Verify the "Event" was actually generated.
1.  Open `backend/logs/orion.log`.
2.  Search for: `Triggering notification for Meeting ID [ID]`.
3.  **If Missing:** The specific meeting query failed. Check `meeting_time` vs current time. (Did we miss the 15m window?)
4.  **If Present:** The Backend Logic worked. The DB `notified` flag is likely `1`. The failure is downstream.

### 2. Transport Layer (The Handover)
**Goal:** Verify the Client picked up the message.
1.  Check `client/client.log` (Client-side).
2.  Search for: `GET /notifications` returning non-empty list.
    *   *Note: In V3, we log "queued alert: ..." to console. We should ensure this hits the file log.*
3.  **If Missing in Client Log:** 
    *   Network partition?
    *   Did the polling thread die? (Check if "Listening..." is still printing or if the process is silent).

### 3. Client Queue State (The Bottleneck)
**Goal:** Verify the message wasn't stuck in "Pending".
1.  **VAD Lock:** Was the User speaking?
    *   Check logs for frequent `User (...) : [text]`.
    *   If `user_is_speaking` flag got stuck `True` (e.g. ambient noise), the `speaker_loop` will PAUSE indefinitely to avoid interrupting.
    *   *Diagnostic:* Check if `ORION (pX): ...` logs stopped appearing entirely.

### 4. Hardware/Output (The Last Mile)
**Goal:** Verify `pyttsx3` is functioning.
1.  Did other messages (Priority 1 Chat) work?
2.  If *all* audio stopped: `pyttsx3` driver likely crashed. Restart Client.

---

## Recovery Strategy (Implemented in Patch 3.1)

**Question:** What if ORION crashes completely?
**Status:**
1.  **Scheduled Reminders:** Persisted in SQLite.
    *   *Recovery:* On Startup, `check_missed_meetings()` scans for meetings missed during downtime (past 24h) and queues an apology: "Apologies, I was offline and missed..."
2.  **Short-Term Context:** Lost (RAM). New conversation starts fresh.
3.  **Active Audio Queue:** Lost (RAM). Any spoken queue is cleared.

## Future Recommendations (V4)
1.  **Dead Letter Queue:** If Client acknowledges receipt (ACK), *then* delete from DB. currently we mark `notified=1` on *read*, not *receipt*. This is "At-Most-Once" delivery (unreliable). We need "At-Least-Once".
