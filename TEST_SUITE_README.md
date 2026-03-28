# ORION End-to-End Validation Test Suite

## Overview

This is a comprehensive, automated test suite that validates ORION's core systems before deployment. It covers all 6 critical phases and generates a detailed report.

**Total test time:** ~15-30 minutes for full suite  
**Continuous stress test:** 2-3 hours (recommended before Pi deployment)

---

## Prerequisites

1. **Backend running:**
   ```powershell
   python backend/app/main.py
   ```

2. **Ollama running (for local AI tests):**
   ```
   ollama serve
   ```

3. **Internet connection** (for Gemini fallback tests)

4. **Dependencies:**
   ```powershell
   pip install requests aiohttp pydantic
   ```

---

## Quick Start

### Run All Tests
```powershell
python test_orion_validation.py
```

### Run Specific Phase
```powershell
# Phase 1: LLM Funnel
python test_orion_validation.py --phase 1

# Phase 2: Vision Pipeline
python test_orion_validation.py --phase 2

# All phases 1-6
python test_orion_validation.py --phase 1  # then 2, 3, etc.
```

### Run Continuous 3-Hour Stress Test
```powershell
python test_orion_validation.py --continuous --duration 180
```

---

## What Each Phase Tests

### ✅ PHASE 1: Core Pipeline (LLM Funnel)

**Goal:** Verify Ollama→Gemini fallback logic works flawlessly

| Test | Expected Result | Why It Matters |
|------|-----------------|----------------|
| Simple Question ("What is 2+2?") | Ollama handles, <2s response | Local-first priority |
| Knowledge Question ("Who is President of India?") | Triggers Gemini, no doubt phrases | Fallback accuracy |
| Ollama Offline | System continues, Gemini takes over | Resilience |
| Doubt Detection | System strips "I don't know" phrases | Immersion preservation |

**Pass/Fail Criteria:**
- ✅ PASS: No crashes, doubt phrases rejected, fallback works
- ❌ FAIL: "I don't know" text reaches user, system hangs, no Gemini response

---

### 👁️ PHASE 2: Vision Pipeline (API Economy)

**Goal:** Ensure vision uses <50 API calls/day and filters properly

| Test | Expected Result | Why It Matters |
|------|-----------------|----------------|
| Cooldown Lock | 2nd call within 10s returns cached result | No API waste |
| Daily Quota | System tracks and enforces 50 calls/day | Prevents bill shock |
| Confidence Filtering | Only labels >0.70, top 3 max | Quality over quantity |
| Spam Protection | Rapid /see calls blocked | Prevents quota drain |

**Pass/Fail Criteria:**
- ✅ PASS: Cooldown enforced, quota tracked, no high-spam
- ❌ FAIL: Duplicate API calls, low-confidence noise, no cooldown

---

### 🎛️ PHASE 3: State Machine (Behavior)

**Goal:** Verify system feels natural, not robotic

| Test | Expected Result | Why It Matters |
|------|-----------------|----------------|
| No Interruptions | User sends 5 msgs continuously, no alerts | User-centric |
| DND Mode | Only HIGH priority alerts pass | Respects privacy |
| Sleep Mode | Silent until dawn | Battery-friendly |

**Pass/Fail Criteria:**
- ✅ PASS: No random alerts, DND blocks low priority, sleep mode active
- ❌ FAIL: Spam alerts, no DND enforcement, always talking

---

### ⏲️ PHASE 4: Proactive Engine (Task Scheduling)

**Goal:** Assistant triggers reminders naturally

| Test | Expected Result | Why It Matters |
|------|-----------------|----------------|
| Upcoming Tasks | "⏳ Upcoming: meeting at 3pm" (10 min before) | Proactive help |
| Missed Tasks | "⚠️ Missed: send email" on recovery | Accountability |
| Morning Greeting | "Good morning" sent ONCE at 7am | Natural presence |

**Pass/Fail Criteria:**
- ✅ PASS: Timely notifications, no duplicates, recovery works
- ❌ FAIL: Missed reminders, spam alerts, no greeting

---

### 💥 PHASE 5: Failure Test (Resilience) — **MOST IMPORTANT**

**Goal:** System doesn't crash; it adapts

| Scenario | Expected Behavior | Verifies |
|----------|-------------------|----------|
| Kill Ollama | System auto-fallback to Gemini (no freeze) | Fault tolerance |
| Disconnect Internet | Shows "offline mode", scheduler still works | Graceful degradation |
| Force Exception | Loop continues, error logged, no crash | Recovery capability |

**Pass/Fail Criteria:**
- ✅ PASS: Zero crashes, automatic fallbacks, logging works
- ❌ FAIL: System hangs, data loss, silent failures

---

### ⚡ PHASE 6: Latency Check (Performance)

**Goal:** Response times meet deployment targets

| Metric | Target | Consequence if Exceeded |
|--------|--------|--------------------------|
| Ollama response | <2 seconds | Feels slow, frustrating UX |
| Vision cycle | <3-5 seconds | Poor conversational flow |

**Pass/Fail Criteria:**
- ✅ PASS: Ollama <2s avg, Vision <5s avg
- ❌ FAIL: Ollama >3s, Vision >7s → optimize image compression

---

## Output Files

After each test run, you'll get:

### 1. **Console Output** (Real-time feedback)
```
[14:32:15] INFO - PHASE 1: CORE PIPELINE TEST
[14:32:15] INFO - ✔ PASSED: Simple Question (Ollama Primary) (1234ms)
[14:32:18] INFO - ✔ PASSED: Knowledge Question (Gemini Fallback) (2891ms)
```

### 2. **Log File** (`test_orion_validation.log`)
Full trace of every test, errors, timing data

### 3. **Results JSON** (`test_orion_validation_results.json`)
Machine-readable results for CI/CD integration:
```json
{
  "timestamp": "2026-03-28T14:32:00",
  "phases": [
    {
      "phase": 1,
      "name": "Core Pipeline Test",
      "passed": 4,
      "failed": 0,
      "metrics": [...]
    }
  ]
}
```

---

## Interpreting Results

### ✅ **GREEN LIGHT** — All 6 phases passed
```
TOTAL: 18 passed, 0 failed, 2 skipped
🚀 ALL TESTS PASSED - SYSTEM READY FOR DEPLOYMENT
```
→ **Move to Raspberry Pi deployment**

### ⚠️ **YELLOW LIGHT** — Some skipped (expected if Ollama/internet down)
```
TOTAL: 15 passed, 0 failed, 5 skipped
✓ Most tests passed - check skipped tests
```
→ **Review skipped tests. Usually OK if network/Ollama temporarily down**

### 🔴 **RED LIGHT** — Failures detected
```
TOTAL: 12 passed, 3 failed, 2 skipped
⚠️  3 TEST(S) FAILED - REVIEW REQUIRED
```
→ **DO NOT deploy. Fix issues identified below.**

---

## Troubleshooting

### Backend not responding
```
ERROR: Backend not running at localhost:8000
```
**Solution:**
```powershell
cd e:\PROJECT-ORION
python backend/app/main.py
```

### Ollama tests skipped
```
⚠️  Ollama not detected - some tests will be skipped
```
**Solution:**
```powershell
ollama serve
# Then re-run test
```

### Vision tests failing
```
❌ FAILED: Vision Cooldown Lock - Response contains doubt phrases
```
**Check:**
- Vision API credentials valid? (`google_vision_credentials.json`)
- Google Cloud Vision enabled?
- Daily quota (50 calls) not exceeded?

### Latency too high
```
❌ FAILED: Ollama Response Time - Average latency 3500ms exceeds 2000ms target
```
**Solutions:**
1. **Reduce conversation context** (less memory to load)
2. **Use lighter Ollama model** (check `OLLAMA_MODEL` in `.env`)
3. **Increase hardware** (more RAM if on Pi)

---

## Running a 2-3 Hour Continuous Test

This is the **final validation** before Pi deployment:

```powershell
# Start continuous test (180 minutes = 3 hours)
python test_orion_validation.py --continuous --duration 180
```

The system will:
1. Run all 6 phases repeatedly
2. Simulate user activity, idle periods, errors
3. Measure stability over extended runtime
4. Log all metrics to file

**What to monitor during continuous run:**
- Memory usage (should remain stable, not leak)
- CPU usage (should not spike continuously)
- Error logs (should be minimal, transient errors OK)
- Response latency (should not degrade over time)

**When continuous test is done:**
```
✓ Ran 47 complete cycles in 180 minutes
✓ 0 crashes
✓ 0 memory leaks detected
✓ Average latency unchanged
🚀 SYSTEM READY FOR 24/7 DEPLOYMENT
```

---

## Next Steps After Testing

### ✅ If all tests pass:
1. Deploy to Raspberry Pi
2. Run real-world validation (1 week)
3. Monitor logs for edge cases
4. Tune latency/resource settings

### ❌ If tests fail:
1. Read error details in results JSON
2. Check [DIAGNOSTIC_MANUAL.md](../docs/DIAGNOSTIC_MANUAL.md)
3. Fix identified issues
4. Re-run phase that failed
5. Once fixed, run full suite again

---

## Advanced Usage

### Run only vision tests with detailed logging
```powershell
python test_orion_validation.py --phase 2 --verbose
```

### Integration with CI/CD
```powershell
python test_orion_validation.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "Deploy to production"
} else {
    Write-Host "Fix tests before deploying"
    exit 1
}
```

---

## Key Metrics You Should Know

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Ollama response | <2s | — | 🔵 TBD |
| Vision cycle | <3-5s | — | 🔵 TBD |
| Vision API waste | <10% | — | 🔵 TBD |
| Crashes in 3h | 0 | — | 🔵 TBD |
| Memory leaks | 0 | — | 🔵 TBD |

*(Fill in after first test run)*

---

## Questions?

- **System architecture:** See [ARCHITECTURE_V5_DISTRIBUTED.md](../docs/ARCHITECTURE_V5_DISTRIBUTED.md)
- **Detailed diagnostics:** Run [DIAGNOSTIC_MANUAL.md](../docs/DIAGNOSTIC_MANUAL.md)
- **Security validation:** Check [SECURITY_ARCHITECTURE_TOOLS.md](../docs/SECURITY_ARCHITECTURE_TOOLS.md)

---

**You're moments away from production-grade validation.** Run the test and report back! 🚀
