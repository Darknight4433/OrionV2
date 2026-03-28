# 🤖 ORION TELEGRAM INTEGRATION TEST GUIDE

## Overview

Telegram is your **remote admin console** + **debug interface** + **command center**. This guide walks through comprehensive testing of all Telegram functionality before deployment.

**Timeline:** ~20 minutes total  
**Status:** Production-hardened testing framework ready

---

## 🔥 ORION TELEGRAM ROLE (CRITICAL)

Telegram is NOT just a chat interface.

| Function | Purpose | Bypass AI? |
|----------|---------|-----------|
| `/start` /`/status` | System control commands | ✅ YES |
| `/add` Task \| Time | Add tasks to scheduler | ✅ YES |
| `/today`, `/health` | System queries | ✅ YES |
| Free text (e.g., "hi") | Natural language to LLM | ❌ NO → routes to Ollama/Gemini |
| `/see` | Camera vision analysis | ❌ NO → calls Vision API |
| `/dnd on\|off` | Do-not-disturb toggle | ✅ YES |
| `/debug` | System debug console | ✅ YES (admin only) |

**Key Principle:** Commands (`/something`) bypass AI entirely. Free text goes through LLM funnel.

---

## 🧪 PHASE 1: BASIC CONNECTIVITY (2 minutes)

Tests bot responsiveness and TLS connection stability.

### Test 1.1: `/start` Command
```
Send:     /start
Expect:   🤖 ORION is *online* and listening.
          Commands: /today, /status, /health, /dnd on|off, /add, /logs, /see, /debug
Verify:   ✅ Clear command list shown
```

### Test 1.2: `/status` Command
```
Send:     /status
Expect:   System status with:
          - Current time
          - Last active timestamp
          - Greeting status
          - Pending tasks count
          - Current state (IDLE/ACTIVE/ENGAGED/DND/SLEEPING)
Verify:   ✅ State shown, no delays >1s
```

### Test 1.3: Free-Text Message (Natural Language)
```
Send:     "hi"
Expect:   AI response from Ollama or Gemini (within 3 seconds)
          Examples: "Hello!", "Hi there!", "Hey!"
Verify:   ✅ Response received
          ⏱️ Latency <3 seconds
          ❌ BUG if: No response, or response >5 seconds
```

---

## 🎯 PHASE 2: COMMAND ROUTING (5 minutes)

Verifies that commands bypass AI and execute **instantly**.

### Test 2.1: `/today` Returns Task List (No AI)
```
Send:     /today
Expect:   List of today's scheduled tasks with:
          - Task title
          - Time
          - Priority (high/medium/low)
          - Status (✅ done or ⏳ pending)
Verify:   ✅ Response <1 second (NO AI involved)
          ❌ BUG if: Response >2 seconds (means routing through AI)
```

### Test 2.2: `/status` Returns State (No AI)
```
Send:     /status
Expect:   Same state output as Phase 1, instant
Verify:   ✅ Response <1 second
          ✅ Current ORION state displayed
```

### Test 2.3: `/health` Server Status
```
Send:     /health
Expect:   Health report showing:
          - Ollama (Local): ✅ Online or ❌ Offline
          - Gemini (Cloud): ✅ Online or ❌ Offline
          - Bot uptime: Xh Ym
          - Scheduler: ✅ Running
          - ORION State: Current state
Verify:   ✅ Accurate status
```

### Test 2.4: `/add` Task (Instant Execution)
```
Send:     /add Team Meeting | 2026-03-30 18:00 | high
Expect:   ✅ Task added!
          📌 Team Meeting
          ⏰ 2026-03-30 18:00
          🎯 Priority: HIGH
Verify:   ✅ Response <1 second (NO AI processing)
          ✅ Task appears in next /today
          ❌ BUG if: Response delayed or missing
```

---

## 📢 PHASE 3: SCHEDULER → TELEGRAM (Critical Integration)

Tests that scheduler fires AND sends notifications back to Telegram.

### Test 3.1: Add Task 1 Minute Ahead
```
Send:     /add Phase3 Test | <NOW+1MIN> | high
Example:  /add Phase3 Test | 2026-03-28 14:35 | high
Expect:   ✅ Task added! (instant)
Verify:   ✅ Task scheduled
```

### Test 3.2: Wait for Notification (Max 70 seconds)
```
Action:   Wait and observe Telegram chat
Expect:   Within 60 seconds:
          ⏳ Upcoming: Phase3 Test
          AND
          🔔 Reminder: Phase3 Test
Verify:   ✅ Scheduler fired correctly
          ✅ Message arrived in Telegram
          ⏱️ Timing accurate (within ±5 seconds)
          ❌ CRITICAL BUG if: Nothing arrives (scheduler broken)
```

---

## 👁️ PHASE 4: VISION VIA TELEGRAM

Tests `/see` command (requires camera + Google Vision API credits).

### Test 4.1: `/see` Command
```
Send:     /see
Expect:   👁️ Vision Result:
          I see: [objects], [objects], [objects]
          OR
          Vision skipped: cooldown
          OR
          I couldn't identify anything specific.
Verify:   ✅ Command executes
          ✅ No crashes
          ⏱️ Latency <5 seconds
```

### Test 4.2: Cooldown Enforcement
```
Action:   Send /see, immediately send again
Expect:   Second request returns:
          "Vision cooldown active (Wait 10s)"
          OR repeats previous result
Verify:   ✅ Cooldown enforced
          ❌ BUG if: Repeated results spam or double-charge API
```

### Test 4.3: No Spam
```
Action:   Send /see multiple times rapid-fire
Expect:   Only one Vision API call charges per 10s
Verify:   ✅ Quota protected
          ❌ BUG if: Multiple calls in 10s windows
```

---

## 🎭 PHASE 5: STATE MACHINE TEST

Verifies DND mode and ENGAGED state transitions.

### Test 5.1: `/dnd on` (Do-Not-Disturb)
```
Send:     /dnd on
Expect:   🔕 *Do-Not-Disturb ON*
          Only high-priority alerts will come through.
Verify:   ✅ DND enabled
          ✅ /status shows DND state
```

### Test 5.2: DND Blocks Low-Priority Tasks
```
Action:   While DND on, schedule low-priority task
          /add Low Task | <NOW+1MIN> | low
Expect:   ⏳ Task scheduled...
          (Telegram notification DOES NOT arrive)
Verify:   ✅ Low-priority blocked during DND
          ❌ BUG if: Notification arrives anyway
```

### Test 5.3: DND Allows High-Priority
```
Action:   While DND on, schedule high-priority task
          /add High Task | <NOW+1MIN> | high
Expect:   Within 60 seconds:
          🔔 Reminder: High Task (arrives)
Verify:   ✅ High-priority alerts pass through
```

### Test 5.4: `/dnd off` Restores Normal
```
Send:     /dnd off
Expect:   🔔 *Do-Not-Disturb OFF*
          All notifications restored.
Verify:   ✅ DND disabled
          ✅ /status shows normal state
          ✅ All priorities now pass
```

### Test 5.5: ENGAGED State
```
Send:     "What is AI?"
Expect:   AI response within 3 seconds
          /status shows "ENGAGED" state
Verify:   ✅ Natural conversation triggers ENGAGED
          ✅ Proactive interruptions suppressed during ENGAGED
```

---

## 💥 PHASE 6: FAILURE RESILIENCE

Tests graceful degradation when AI backends fail.

### Test 6.1: Both AI Backends Unreachable
```
Manual:   Kill Ollama process (or disconnect network)
Send:     "What is AI?"
Expect:   Safe fallback response like:
          "⚡ ORION core is running. AI backends are currently unreachable,
           but your scheduler and reminders are fully active."
Verify:   ✅ No crash
          ✅ Graceful fallback message
          ❌ CRITICAL if: Error thrown or system crash
```

### Test 6.2: Offline Commands Still Work
```
Action:   Network offline (or Ollama down)
Send:     /status
Expect:   System status displayed
Send:     /today
Expect:   Task list displayed
Send:     /health
Expect:   Shows backends offline but bot alive
Verify:   ✅ All system commands work independently
          ✅ No dependency on AI backends for CLI
```

### Test 6.3: Scheduler Unaffected
```
Action:   Kill Ollama, wait for task to fire
Expect:   Scheduler fires and sends Telegram notification
          even with Ollama offline
Verify:   ✅ Scheduler independent of AI availability
```

---

## 🔧 PHASE 7: DEBUG CONSOLE

Admin-only diagnostic command.

### Test 7.1: `/debug` (Admin only)
```
Send:     /debug
Expect:   Comprehensive debug output:
          ━━ UPTIME ━━
          ⏱️  Bot: 2h 15m 30s
          📅 Date: 2026-03-28 14:30:45
          
          ━━ AI BACKENDS ━━
          🖥️  Ollama (Local): ✅ ALIVE
          ☁️  Gemini (Cloud): ✅ ALIVE
          
          ━━ STATE MACHINE ━━
          🤖 State: ACTIVE for 5m
          👤 Last Active: 2026-03-28 14:28
          📋 Pending Tasks: 3/7
          👁️  Vision Calls: 2/50
          
          ━━ SCHEDULER ━━
          ⏳ Scheduler: ✅ RUNNING
          🔄 Task Loop: ✅ ACTIVE
          📤 Telegram Send: ✅ WIRED
Verify:   ✅ All systems visible in one view
          ✅ No crashes on admin check
```

---

## 📊 EXPECTED TEST RESULTS

| Phase | Focus | Expected Pass Rate |
|-------|-------|----------|
| 1 | Connectivity | 100% |
| 2 | Command routing (instant execution) | 100% |
| 3 | Scheduler → Telegram wiring | 100% (Critical) |
| 4 | Vision API integration | 90% (optional if no camera) |
| 5 | State machine (DND, ENGAGED) | 100% |
| 6 | Failure resilience | 100% (Critical) |
| 7 | Debug console | 100% |

**Failure Criteria:**
- ❌ Any Phase 2, 3, 5, 6 test fails → **DO NOT DEPLOY**
- ⚠️ Phase 4 (vision) can skip if camera unavailable
- ✅ Must achieve >95% overall pass rate before production

---

## 🚀 HOW TO RUN AUTOMATED TEST SUITE

### Quick Test (20 minutes)
```bash
# From project root:
cd e:\PROJECT-ORION\orion
python telegram_test_suite.py
```

**What it does:**
- Sends test messages through 7 phases
- Checks responses and timing
- Saves results to `data/telegram_test_results.json`
- Prints pass/fail report

### Manual Test Flow
If you prefer step-by-step:

1. **Start bot:**
   ```bash
   python main.py
   ```

2. **Open Telegram** and message your bot

3. **Follow Phase 1-7 tests above** manually

4. **Document results** in a text file

---

## 🔴 COMMON ISSUES & FIXES

| Issue | Cause | Fix |
|-------|-------|-----|
| Bot not responding | Token invalid or polling stopped | Check `BOT_TOKEN` in config.py, restart main.py |
| Delay in /status | Routing through AI instead of bypass | Check router.py SYSTEM_COMMANDS list |
| Scheduler not sending | send() function broken | Check main.py `send()` function, verify Telegram API |
| Duplicate messages | Multiple handlers firing | Check telegram_bot.py handlers once each |
| /see crashes | Camera permissions or CV2 missing | Run `pip install opencv-python` |
| Vision API errors | Quota exceeded | Check Google Cloud console for daily limit |
| DND not blocking | State machine not wired | Check state.py transition logic |

---

## ✅ DEPLOYMENT READINESS CHECKLIST

Before deploying to Raspberry Pi:

- [ ] Phase 1: All connectivity tests pass
- [ ] Phase 2: All commands execute <1 second
- [ ] Phase 3: Scheduler sends Telegram notifications
- [ ] Phase 4: /see works (or skipped if no camera)
- [ ] Phase 5: DND and state transitions work
- [ ] Phase 6: System survives AI backend failure
- [ ] Phase 7: /debug shows green status on all systems
- [ ] Overall pass rate: >95%
- [ ] No crashes during full test suite run
- [ ] Delays all <5 seconds (except scheduled notifications)

---

## 📝 REPORTING

After testing, provide this summary:

```
TELEGRAM TEST RESULTS
═══════════════════════

Timestamp: 2026-03-28 14:30:00
Total Tests: 18
Passed: 18
Failed: 0
Success Rate: 100%

Phase Results:
  ✅ Phase 1: Connectivity
  ✅ Phase 2: Command Routing
  ✅ Phase 3: Scheduler Notifications
  ✅ Phase 4: Vision
  ✅ Phase 5: State Machine
  ✅ Phase 6: Failure Resilience
  ✅ Phase 7: Debug Console

Issues: None
Ready for Deployment: YES ✅
```

---

## 🎯 NEXT STEPS

After successful Telegram testing:

1. ✅ Test suite passes locally
2. ✅ No crashes during 20-minute run
3. → **Deploy to Raspberry Pi** using PI_DEPLOYMENT_GUIDE.md
4. → Run same tests on Pi hardware
5. → Monitor logs for 24 hours
6. → Production deployment ready

---

**Questions?** Check the logs: `data/logs.txt` or run `/debug` in Telegram.
