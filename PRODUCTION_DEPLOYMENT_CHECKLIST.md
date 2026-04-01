# ORION Production Deployment Checklist

## 🚀 Pre-Deployment Verification (Manual + Automated)

**Date:** ________________  
**Tester:** ________________  
**System:** ORION v1.0 on Raspberry Pi  
**Target:** School Executive Assistant Deployment  

---

## ✅ Voice I/O VERIFICATION

### Voice Output (Text-to-Speech)
- [ ] **Basic speak test**
  - Run: `python -c "from backend.app.services.voice_service import SpeakerService; s = SpeakerService(); s.speak('Hello, this is ORION')"` 
  - Expected: Clear audio output heard from speaker
  - Notes: ________________

- [ ] **ElevenLabs primary TTS**
  - Verify API key is valid
  - Test sentence: "Tell me about photosynthesis"
  - Expected: Natural English voice (< 3 seconds)
  - Notes: ________________

- [ ] **Fallback to Sarvam**
  - Block ElevenLabs API
  - Test sentence: "What is the capital of France?"
  - Expected: Audio still plays (different voice quality OK)
  - Notes: ________________

- [ ] **Emergency fallback to gTTS**
  - Block both ElevenLabs AND Sarvam
  - Test sentence: "System is in fallback mode"
  - Expected: Audio still plays (may sound robotic)
  - Notes: ________________

- [ ] **No silent failures**
  - If TTS fails on all backends, check logs
  - Expected: Error logged, system continues (doesn't hang)
  - Notes: ________________

### Voice Input (Speech Recognition)
- [ ] **Microphone detection**
  - Run: `backend/app/core/logging.py` check mic_index
  - Expected: Correct device index configured
  - Notes: ________________

- [ ] **Wake word detection**
  - Say: "ORION, hello"
  - Expected: Response within 2 seconds
  - Notes: ________________

- [ ] **Timeout handling**
  - Stay silent for 10 seconds
  - Expected: Graceful timeout (no crash)
  - Notes: ________________

---

## ✅ AI BRAIN VERIFICATION

### Ollama (Primary)
- [ ] **Ollama server running**
  - Run: `curl http://localhost:11434/api/tags`
  - Expected: List of models returned (Phi3 present)
  - Notes: ________________

- [ ] **Response time < 2 seconds**
  - Ask: "What is 2+2?"
  - Expected: "4" or similar (< 2 sec)
  - Notes: ________________

- [ ] **Memory integration**
  - Ask: "What's my schedule?"
  - Expected: Pulls from memory, not just generic answer
  - Notes: ________________

### Gemini (Fallback)
- [ ] **API key configured**
  - Check: `backend/app/core/config.py` has GEMINI_API_KEY
  - Expected: Key is present and non-empty
  - Notes: ________________

- [ ] **Realtime query fallback**
  - Ask: "What's today's news?"
  - Expected: Current information (queries Gemini not Ollama)
  - Notes: ________________

- [ ] **Fallback triggers on weak Ollama response**
  - Ask Ollama something it should be weak on: "Who is PM of India 2026?"
  - Expected: Router detects weakness and uses Gemini
  - Check logs: `[CONFIDENCE] Weak response detected`
  - Notes: ________________

### Confidence Filter
- [ ] **Detects "I don't know"**
  - Test query: Something very specific Ollama doesn't know
  - Expected: Logs show confidence failure, falls back
  - Notes: ________________

- [ ] **Detects outdated responses**
  - Test query: Current events or political positions
  - Expected: Gemini used instead of weak Ollama response
  - Notes: ________________

---

## ✅ MEMORY & HABITS VERIFICATION

### Memory System
- [ ] **Task storage**
  - Add via Telegram: `/add Review report by 5 PM`
  - Expected: Shows up in `/notifications` or briefing
  - Notes: ________________

- [ ] **Conversation history**
  - Chat: "Remind me it's raining"
  - Chat: "What did I just tell you?"
  - Expected: System remembers
  - Notes: ________________

- [ ] **Memory persistence**
  - Restart backend
  - Chat: "What did I say about rain?"
  - Expected: Still remembered (survives restart)
  - Notes: ________________

### Habit Learning  
- [ ] **Silent learning phase (days 1-3)**
  - Perform action (e.g., study at 9 PM) 3 times
  - Expected: NO habit suggestion yet
  - Notes: ________________

- [ ] **Silent learning activation (day 4+)**
  - Perform action 5 times total
  - At matching time: "Sir, it is your usual study time."
  - Expected: Suggestion appears after 8 PM
  - Notes: ________________

- [ ] **School hours blocking**
  - Jump system time to 10 AM (school hours)
  - Perform study habit
  - Expected: NO suggestion during 8 AM - 3 PM
  - Notes: ________________

- [ ] **No spam (1-hour cooldown)**
  - Get habit suggestion
  - Wait 1 minute
  - Trigger same habit again
  - Expected: No duplicate suggestion
  - Notes: ________________

---

## ✅ DECISION MAKING VERIFICATION

### Decision Engine Priority
- [ ] **Meeting > Task > Habit**
  - Add: Meeting at 10:00 AM + Task + trigger habit at same time
  - Expected: "Sir, your meeting..." (not task, not habit alert)
  - Notes: ________________

- [ ] **Escalation for overdue**
  - Create task 60+ minutes overdue
  - Expected: "...may require immediate attention"
  - Notes: ________________

- [ ] **Single alert only**
  - Trigger multiple events simultaneously
  - Expected: Only ONE notification sent (best priority wins)
  - Notes: ________________

### Planner Engine
- [ ] **Meeting context added**
  - Trigger meeting alert  
  - Expected: Suggestion like "You may want to review notes"
  - Notes: ________________

- [ ] **Task escalation context**
  - Check same as Escalation test above
  - Expected: 2-sentence output (action + helpful context)
  - Notes: ________________

---

## ✅ BRIEFING SYSTEM VERIFICATION

### Daily Briefing (8 AM)
- [ ] **Morning briefing trigger**
  - Jump system time to 8:00 AM
  - Expected: "Good morning, Sir. You have..."
  - Check logs: `Morning briefing sent`
  - Notes: ________________

- [ ] **Counts meetings correctly**
  - Add 3 meetings
  - Check briefing
  - Expected: "...3 meetings..."
  - Notes: ________________

- [ ] **Counts tasks correctly**
  - Add 2 tasks
  - Check briefing
  - Expected: "...2 pending tasks..."
  - Notes: ________________

### Context Query
- [ ] **"What's my schedule?" handled**
  - Ask: "What's my schedule?"
  - Expected: "Sir, you have X meetings, Y tasks"
  - Notes: ________________

---

## ✅ TELEGRAM INTEGRATION VERIFICATION

### Task Management
- [ ] **Task creation via /add**
  - Send: `/add Finish quarterly report`
  - Expected: Task appears in system
  - Notes: ________________

- [ ] **Dev alerts**
  - Block Ollama (or simulate failure)
  - Expected: Telegram dev alert: "⚠️ Ollama weak → Gemini used"
  - Notes: ________________

- [ ] **Status command**
  - Send: `/status`
  - Expected: System status returned
  - Notes: ________________

---

## ✅ ROBUSTNESS VERIFICATION

### Network Resilience
- [ ] **Works with internet OFF**
  - Turn off WiFi
  - Chat: "Tell me a joke"
  - Expected: Ollama responds (no internet needed)
  - Notes: ________________

- [ ] **Graceful Gemini fallback**
  - Turn OFF WiFi
  - Ask: "Current news"
  - Expected: Falls back to Ollama (or offline response)
  - Notes: ________________

- [ ] **Recovery on internet ON**
  - Turn WiFi back ON
  - Check logs for recovery notification
  - Expected: `✅ Ollama recovered` or similar
  - Notes: ________________

### Performance on Pi
- [ ] **CPU usage < 50%**
  - While running normally: `top`
  - Expected: ORION process uses <50% CPU
  - Notes: ________________

- [ ] **No memory leaks (30 min run)**
  - Run for 30 min of normal use
  - Check memory: `free -h`
  - Expected: Memory stable (not growing)
  - Notes: ________________

- [ ] **Temp file cleanup**
  - Check: `ls /tmp/ | grep temp_speech`
  - Expected: Temp files cleaned up (not accumulating)
  - Notes: ________________

### Crash Recovery
- [ ] **Restart after crash**
  - Kill backend: `pkill -f main.py`
  - Restart: `python backend/app/main.py`
  - Expected: System comes back online
  - Check: `/health` returns 200
  - Notes: ________________

---

## ✅ USER EXPERIENCE VERIFICATION

### Professional Behavior
- [ ] **No repeated alerts**
  - Run for 1 hour
  - Expected: Same alert only appears once
  - Notes: ________________

- [ ] **No interruptions**
  - While Sir speaks, test doesn't interrupt
  - Expected: Voice output waits for silence
  - Notes: ________________

- [ ] **Professional tone**
  - Listen to 10 responses
  - Expected: All use "Sir" + respectful language
  - Notes: ________________

- [ ] **Correct response length**
  - Check random responses
  - Expected: 1-2 sentences max
  - Notes: ________________

---

## 📝 FINAL SIGN-OFF

**All tests passed:** Yes / No

**Issue Summary:**
```
_________________________________________________________________________

_________________________________________________________________________
```

**Deployment decision:**
- [ ] **APPROVED** - Ready for school deployment
- [ ] **APPROVED with notes** - Deploy with observations logged above
- [ ] **NOT APPROVED** - Address failures before deployment

**Approval by:** _________________ **Date:** ________________

**Deployment scheduled for:** ________________

---

## 🔥 Quick Reference: If Something Breaks

| Issue | Diagnostic | Fix |
|-------|-----------|-----|
| No voice output | Check `audio.log` | Restart SpeakerService |
| Ollama not responding | `curl localhost:11434/api/tags` | Restart Ollama |
| Gemini fallback not working | Check API key in config | Verify key + internet |
| Memory lost on restart | Check DB file exists | Run migration |
| Habit spam | Check cooldown in logs | Verify 1-hour gate |
| Repeated alerts | Check `should_send_notification` | Verify 5-min cooldown |
| Telegram not getting alerts | Check bot token | Verify Telegram connectivity |

---

**Generated:** April 1, 2026  
**System Version:** ORION v1.0  
**Target:** School Executive Assistant Production Deployment
