# ORION System Architecture v1.0 (LOCKED)

## 🎤 Interaction Model

```
User (Voice/Telegram)
    ↓
ORION Router (Pi Backend)
    ↓
Query Classification (REALTIME/DYNAMIC_FACT/FACT/GENERAL)
    ↓
Primary AI (Ollama) → Fallback (Gemini)
    ↓
Confidence Filter + Response Validation
    ↓
Decision Engine → Planner Engine
    ↓
TTS Fallback Chain
    ├─ ElevenLabs (primary)
    ├─ Sarvam (fallback)
    └─ gTTS (emergency)
    ↓
Voice Output (Speaker)
```

---

## 🧠 Core Components

### 1. Router (orion/core/router.py)
**Decision Logic:**
- REALTIME queries → Direct Gemini (current data)
- DYNAMIC_FACT queries → Ollama first, Gemini fallback
- FACT queries → Ollama (good for static facts)
- GENERAL queries → Ollama (reasoning/conversation)

**Confidence Filter:**
- Detects uncertainty phrases: "i don't know", "cannot verify", "knowledge cutoff"
- Minimum 20-char response validation
- Detects incomplete/truncated responses
- Falls back to Gemini if Ollama weak

### 2. Memory System (backend/app/services/memory_service.py)
**Stores:**
- Conversation history (4-hour rolling + permanent flag)
- User facts (preferences, habits, work patterns)
- System alerts (meetings, tasks, reminders)
- Memory items (habits, preferences, facts)

**User Scope:**
- Each user has unique ID (face detection / Telegram / device)
- Isolated memory buckets per user
- Supports multi-user future expansion

### 3. Habit Learning (backend/app/services/habit_suggester.py)
**Silent Learning:**
- First 3 detections: no suggestions
- Requires count ≥ 4 for activation
- Tracks last_seen for decay analysis

**School Mode:**
- No suggestions during 8 AM - 3 PM (work hours)
- Professional "Sir" tone
- 1-hour cooldown between suggestions
- Soft + hard modes based on first daily suggestion

### 4. Decision Engine (backend/app/services/decision_engine.py)
**Priority Scoring:**
```
MEETING:    5 (highest)
TASK:       4
REMINDER:   4
HABIT:      2 (lowest)
```
**Urgency Boost:**
- ≤5 min:   +5
- ≤15 min:  +4
- ≤60 min:  +3
- else:     +1

**Selects:** Single best action with highest combined score

### 5. Planner Engine (backend/app/services/planner_engine.py)
**Expands decisions** with helpful context:
- Meeting: "You may want to review notes" / "proceed now"
- Task (overdue): "may require immediate attention"
- Task (pending): "when convenient"
- Habit: "I can assist if needed"

Results in 2-sentence professional suggestions

### 6. Briefing Engine (backend/app/services/briefing_engine.py)
**Generates contextual summaries:**
- Morning: "Good morning Sir, today you have..."
- Afternoon: "Good afternoon, you have..."
- End-of-day: "Tomorrow you have..."
- Context: Instant response to "What's my schedule?"

### 7. Voice Service (backend/app/services/voice_service.py)
**TTS Failure Detection & Fallback:**
- Detects API limit exceeded
- Detects network timeouts
- Detects authentication failures
- Falls back through chain without silent failure

**Playback:**
- Queued, non-blocking
- Echo mitigation (waits for silence)
- Linux/Pi optimized (mpg123/aplay)
- Automatic temp file cleanup

---

## 🔀 AI Routing Architecture

### Query Classification
```python
REALTIME keywords:
  "today", "now", "latest", "news", "current", "2024-2026"
  → Requires current data

DYNAMIC_FACT keywords:
  "president", "minister", "stock", "election", "current"
  → May be outdated, higher fallback rate

FACT keywords:
  "who is", "what is", "define", "explain", "history"
  → Static knowledge, Ollama good

GENERAL keywords:
  Everything else (reasoning, conversation, memory use)
  → Ollama efficient for reasoning
```

### Fallback Chain
```
REALTIME:
  Try Gemini directly (has current data)
  ↓
  If Gemini unavailable → Try Ollama
  ↓ (if both fail)
  TinyLlama → offline response

DYNAMIC_FACT:
  Try Ollama first (usually knows)
  ↓
  If weak/invalid → Try Gemini
  ↓ (if both fail)
  TinyLlama → offline response

FACT:
  Try Ollama
  ↓
  If fails → Try Gemini
  ↓ (if both fail)
  TinyLlama → offline response

GENERAL:
  Try Ollama
  ↓
  If unavailable → Try Gemini
  ↓ (if both fail)
  TinyLlama → offline response
```

---

## 📱 Telegram Role

**NOT** the primary interface.

**Telegram is for:**
✔ Adding tasks/meetings  
✔ System debugging  
✔ Developer alerts  
✔ Remote control  

**Developer Alerts sent to Telegram:**
- ⚠️ Ollama weak → Gemini used
- ⚠️ Dynamic fact fallback
- ✅ Ollama recovery
- 🚨 All backends down
- 💀 Total system failure

**Sir never sees dev alerts** (only voice responses)

---

## 🎙️ Voice System (Final Design)

### TTS Failure Detection

```python
def speak(text):
    sentences = split_sentences(text)
    
    for sentence in sentences:
        # Try ElevenLabs
        audio = elevenlabs_tts(sentence)
        
        if audio and not api_limit_reached(audio):
            queue_and_play(audio)
            continue
        
        # Detect specific failures
        if "429" in error or "rate limit" in error:
            log_alert("API limit reached")
        
        if "network" in error or "timeout" in error:
            log_alert("Network error")
        
        # Try Sarvam fallback
        audio = sarvam_tts(sentence)
        
        if audio:
            queue_and_play(audio)
            continue
        
        # Try gTTS emergency
        audio = gtts_tts(sentence)
        
        if audio:
            queue_and_play(audio)
            continue
        
        # Log silent failure (should never happen)
        log_error("All TTS backends failed")
```

### TTS Priority Chain

**English:**
1. ElevenLabs (preferred, natural)
2. Sarvam (fallback)
3. gTTS (emergency)

**Hindi/Devanagari:**
1. Sarvam (native)
2. ElevenLabs (accented fallback)
3. gTTS (emergency)

---

## 🧠 Critical System Rules

### ❌ NEVER:
- Speak multiple times for same event
- Repeat alerts within 5-minute window
- Interrupt active user speech
- Send responses longer than 2 sentences
- Suggest during school hours (unless critical)
- Store irrelevant conversation data

### ✅ ALWAYS:
- One message per action
- 1–2 sentences maximum
- Professional "Sir" tone
- Respect priority order
- Fall back gracefully
- Log all routing decisions
- Alert dev only (not user) on failures

---

## 📊 Production Readiness Checklist

### ✅ Voice I/O
- [ ] Speak generates audio without hanging
- [ ] Speak falls back through chain on failure
- [ ] Listen doesn't interfere with speech
- [ ] Wake word detection works
- [ ] Stop signal interrupts playback

### ✅ AI Brain
- [ ] Ollama responds to normal queries <2s
- [ ] Gemini fallback for REALTIME queries
- [ ] Confidence filter prevents weak answers
- [ ] Dev alerts appear on fallback
- [ ] Recovery detected when Ollama comes back

### ✅ Memory & Habits
- [ ] First 3 habit detections silent
- [ ] Habit suggestions only after 8 PM / before 8 AM
- [ ] No repeated suggestions (1-hour cooldown)
- [ ] Tasks/meetings persist across restarts
- [ ] Memory clean-up runs at 3 AM

### ✅ Decision Making
- [ ] Meetings > Tasks > Reminders > Habits
- [ ] Escalation triggers for 15+ min overdue
- [ ] One alert per 5-minute window
- [ ] Planner adds helpful context
- [ ] Briefing generates on schedule (8 AM daily)

### ✅ Telegram
- [ ] /add tasks works
- [ ] /status shows current state
- [ ] Dev alerts appear
- [ ] No user-facing errors in Telegram

### ✅ System Robustness
- [ ] No crash on network loss
- [ ] Graceful degradation (Ollama down → Gemini)
- [ ] CPU usage stays <50% on Pi
- [ ] Temp files cleaned up
- [ ] Logs rotate properly

---

## 🚀 Deployment Verification

Before school deployment, verify:

1. **Voice round-trip:** Speak → Listen → Respond
2. **AI fallback:** Block internet → Ollama still works
3. **TTS fallback:** Block ElevenLabs API → gTTS works
4. **Dev alerts:** Fallback events appear in Telegram
5. **No spam:** Run 1 hour, check no repeated alerts
6. **Telegram:** Add task, verify in memory
7. **Briefing:** Check morning briefing at 8 AM (or test time jump)
8. **Behavior:** No interruptions, professional tone, correct priorities

---

## 📝 Version History

**v1.0 (April 1, 2026):** Initial production-ready architecture
- Hybrid AI (Ollama + Gemini)
- Decision engine + planner
- Confidence filters + smart fallback
- Professional school mode
- Complete memory system
- Voice I/O with TTS failure detection
- Dev monitoring
