# 🚀 ORION Pre-Deployment Validation Checklist

## ✅ IMMEDIATE ACTION ITEMS

### STEP 1: Prepare Your Environment (5 min)

**Terminal 1 - Start Backend:**
```powershell
cd e:\PROJECT-ORION
.\.venv\Scripts\Activate.ps1
python backend/app/main.py
```
✓ Wait until you see: `"INFO: Started server process [XXXX]"`

**Terminal 2 - Start Ollama:**
```powershell
ollama serve
```
✓ Wait until you see: `"Listening on 127.0.0.1:11434"`

**Terminal 3 - Run Tests:**
```powershell
cd e:\PROJECT-ORION
python test_orion_validation.py
```

---

## 📊 WHAT YOU'LL SEE

### During Execution (30 seconds each)
```
[14:32:15] ✔ PASSED: Simple Question (Ollama Primary) (1234ms)
[14:32:18] ✔ PASSED: Knowledge Question (Gemini Fallback) (2891ms)
[14:32:21] ✔ PASSED: Ollama Offline → Gemini Fallback (8765ms)
...
```

### Final Results
```
============================================================================
FINAL TEST SUMMARY
============================================================================
✓ PHASE 1: Core Pipeline Test
  18/18 passed, 0 failed, 0 skipped
  Duration: 12345ms

✓ PHASE 2: Vision Pipeline Test
  5/5 passed, 0 failed, 0 skipped
  Duration: 8901ms

...

TOTAL: 28 passed, 0 failed, 2 skipped
Total Time: 87.3s

🚀 ALL TESTS PASSED - SYSTEM READY FOR DEPLOYMENT
============================================================================
```

---

## 🎯 SUCCESS CRITERIA

### ✅ **GREEN LIGHT** (Deploy to Pi)
```
- All 6 phases show ✓
- 0 failed tests
- Ollama response <2s
- Vision cycle <5s
- No crashes in Phase 5
```

### ⚠️ **YELLOW LIGHT** (Review)
```
- Some tests skipped (Ollama/Internet down)
- But ALL executed tests pass
- No failures
→ Likely safe to proceed (rerun with systems online)
```

### 🔴 **RED LIGHT** (Fix First)
```
- Any test shows ✗ FAILED
- Phase 5 shows crashes
- Latency exceeds targets
→ DO NOT deploy. Fix and retest.
```

---

## 📋 PHASE-BY-PHASE BREAKDOWN

### Phase 1: Core Pipeline ✨
```
Tests:
  1. Simple math question → Ollama handles
  2. Knowledge question → Triggers Gemini
  3. Ollama offline → Falls back to Gemini
  4. Doubt detection → "I don't know" filtered out

Expected: All 4 pass in <30s
```

### Phase 2: Vision Pipeline 👁️
```
Tests:
  1. Cooldown lock → 2nd call returns cached
  2. Daily quota → 50 call limit tracked
  3. Confidence filtering → Labels >0.70 only
  4. Spam protection → Rapid calls blocked

Expected: All 4 pass in <10s
```

### Phase 3: State Machine 🎛️
```
Tests:
  1. No interruptions → User sends 5 msgs, no alerts
  2. DND mode → Only HIGH priority pass
  3. Sleep mode → Silent at night

Expected: All 3 pass (configuration verification)
```

### Phase 4: Proactive Engine ⏲️
```
Tests:
  1. Upcoming tasks → Notification sent 10 min before
  2. Missed tasks → Alert on recovery
  3. Morning greeting → Sent only once

Expected: All 3 pass (scheduler verification)
```

### Phase 5: Failure Test 💥 **[MOST IMPORTANT]**
```
Tests:
  1. Kill Ollama → System auto-fallback, no crash
  2. Offline mode → Graceful degradation
  3. Crash recovery → Loop continues, logged

Expected: All 3 pass = System is resilient
```

### Phase 6: Latency Check ⚡
```
Tests:
  1. Ollama <2 seconds ← Must achieve this
  2. Vision <5 seconds ← Must achieve this

Expected:
  Ollama avg: 1200-1800ms ✓
  Vision avg: 2500-4500ms ✓
```

---

## 🔧 IF TESTS FAIL

### Failure: "Ollama Response Time exceeds 2000ms"
**Solution:**
1. Check Ollama model: `ollama list`
2. Try smaller model: `ollama pull mistral` (faster than llama2/3)
3. Increase RAM on your machine
4. Review backend context size (memory service limits)

### Failure: "Vision Cooldown Not Enforced"
**Solution:**
1. Check Vision service is loaded
2. Verify Google credentials: `ls google_vision_credentials.json`
3. Re-check VisionService cooldown logic in code

### Failure: "Phase 5 - System Crashed"
**Solution:**
1. Check error logs: `test_orion_validation.log`
2. Look for unhandled exceptions
3. Verify exception handling in main.py
4. Run Phase 5 in isolation: `python test_orion_validation.py --phase 5`

### Failure: "Backend Not Running"
**Solution:**
```powershell
# Check if port 8000 is in use
netstat -ano | findstr :8000

# Kill existing process
taskkill /PID <PID> /F

# Restart backend
python backend/app/main.py
```

---

## 📈 NEXT: CONTINUOUS 3-HOUR STRESS TEST

**Only run this AFTER all individual tests pass:**

```powershell
python test_orion_validation.py --continuous --duration 180
```

This will:
- Run all 6 phases repeatedly for 3 hours
- Monitor for memory leaks
- Check latency stability
- Verify no crashes under load

**What to do while it runs:**
- Monitor system resources (Task Manager)
- Log any unusual behavior
- Let it complete (don't interrupt)

**Expected result after 3 hours:**
```
✓ 47+ complete cycles
✓ 0 crashes
✓ Memory usage stable (±50MB)
✓ Latency unchanged
✓ All logs clean (few errors)
🚀 READY FOR PRODUCTION
```

---

## 🎯 FINAL DEPLOYMENT GATES

Before deploying to **Raspberry Pi**, verify:

- [ ] **Phase 1**: Ollama + Gemini fallback works
- [ ] **Phase 2**: Vision API economy enforced
- [ ] **Phase 3**: State machine behavior correct
- [ ] **Phase 4**: Proactive reminders work
- [ ] **Phase 5**: No crashes, resilience proven
- [ ] **Phase 6**: Latency within targets
- [ ] **Continuous**: 3-hour test completed, no crashes
- [ ] **Logs**: No persistent errors, only transient issues

---

## 📝 QUICK REFERENCE COMMANDS

```powershell
# Run all tests
python test_orion_validation.py

# Run specific phase
python test_orion_validation.py --phase 1  # Options: 1-6

# Continuous stress test
python test_orion_validation.py --continuous --duration 180

# View results
cat test_orion_validation_results.json

# View logs
tail -f test_orion_validation.log

# Use convenient batch file
.\run_tests.bat  # Menu-driven interface
```

---

## 🚀 YOU'RE READY

Everything is prepared. You now have:

1. ✅ **Automated test suite** (test_orion_validation.py)
2. ✅ **Comprehensive documentation** (TEST_SUITE_README.md)
3. ✅ **Quick-start script** (run_tests.bat)
4. ✅ **This checklist** (you're reading it!)

### Next 30 seconds:
```
1. Start backend (Terminal 1)
2. Start Ollama (Terminal 2)
3. Run: python test_orion_validation.py (Terminal 3)
4. Watch the results roll in
5. Report back with the final summary
```

---

**You built this. Now let's prove it works.** 🔥

Go run the tests! 🚀
