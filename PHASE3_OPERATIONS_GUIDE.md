# 🚀 ORION Phase 3: Real-World Hardening Operations Guide

## Status: LIVE OPERATIONS MODE

**Phase 3 transforms ORION from a working system to a reliable, self-healing production assistant.**

---

## 🏥 What's New: Phase 3 Components

### 1. Health Monitoring System (`health_monitor.py`)

**Runs:** Daily at 6 AM + Every 30 minutes (continuous check)

**Monitors:**
- Response time (alerts if avg > 3s)
- Error rate (alerts if > 15%)
- Memory usage (alerts if >100 MB/hour growth)
- Service health (Voice, Memory, Ollama, Gemini)

**Output:** `data/health_status.json`

**Key Point:** Only alerts DEV, never bothers Sir

---

### 2. Auto-Recovery System (`auto_recovery.py`)

**Triggers:** When health check detects issues

**Auto-heals:**
- Slow responses → Switch to performance mode (more Gemini)
- High error rate → Cleanup error-prone resources
- Memory leak → Run aggressive cleanup
- Voice issues → Restart voice service
- Ollama timeout → Reset connection

**Cooldown:** 5 minutes between recovery attempts (prevents thrashing)

**Key Point:** System self-heals without human intervention

---

### 3. Usage Learning System (`usage_learner.py`)

**Runs:** Every 6 hours + Continuous logging

**Learns:**
- Command shortcuts (if "schedule" repeated 3+ times, create shortcut)
- Response length preference (is Sir ignoring long answers?)
- Tone preference (formal vs casual)
- Ignored suggestions (stop suggesting what he ignores)
- Repeated commands (opportunity for optimization)

**Output:** `data/usage_patterns.json`

**Example Learning:**
```
Day 1: Sir says "What's my schedule?" 5 times
Day 2: System offers direct shortcut
        "Schedule already loading, Sir..."
Result: Faster, feels custom-built
```

**Key Point:** System becomes more intelligent every day

---

### 4. Weekly Maintenance (`weekly_maintenance.py`)

**Runs:** Every Sunday at 2 AM (auto-detected if overdue)

**Tasks:**
- Archive logs older than 7 days (compress with gzip)
- Trim stats (keep last 500 queries only)
- Clean old tasks (delete completed tasks > 30 days old)
- Optimize database (VACUUM + PRAGMA optimize)

**Result:** Prevents long-term slowdown

**Key Point:** System maintenance happens automatically

---

## 📊 Monitoring Dashboards

### Daily Health Dashboard
```bash
# Check current health
python -c "
import json
with open('data/health_status.json') as f:
    health = json.load(f)
    print('🏥 ORION Health Status')
    print(f'  Response time: {health[\"response_time_avg\"]:.2f}s')
    print(f'  Error rate: {health[\"error_rate\"]:.1%}')
    print(f'  Memory usage: {health[\"memory_usage_mb\"]:.1f} MB')
    print(f'  Services: {health[\"service_status\"]}')
    if health['alerts']:
        print(f'  ⚠️  Alerts: {health[\"alerts\"]}')
"
```

### Usage Learning Dashboard
```bash
# What ORION has learned
python -c "
import json
with open('data/usage_patterns.json') as f:
    patterns = json.load(f)
    print('📚 What ORION Learned')
    print(f'  Preferred response length: {patterns[\"preferred_length\"]}')
    print(f'  Preferred tone: {patterns[\"preferred_tone\"]}')
    print(f'  Top repeated command: {max(patterns[\"repeat_commands\"].items(), key=lambda x:x[1])[0]}')
"
```

### Scheduler Status
```bash
# See all scheduled jobs
python -c "
from backend.app.main import scheduler
for job in scheduler.get_jobs():
    print(f'{job.name}: {job.trigger}')
"
```

---

## 🧠 How Phase 3 Works (Real Example)

### Day 1: Initial Deployment
```
🚀 ORION starts
📊 Health check: All green
```

### Day 2-3: Learning Phase
```
🎤 Sir: "What's my schedule?"
📊 System logs usage
🧠 System learns: "schedule" = important query

🎤 Sir: "What's my schedule?" (again)
📌 System notes repetition

🎤 Sir: "What's my schedule?" (again)
📌 System notes repetition

🎤 Sir: "What's my schedule?" (again)
💡 ALERT: Pattern identified!
🔧 System creates shortcut
```

### Day 3-5: Adaptive Phase
```
⏰ 6 AM: Health check runs
  ✅ Response time: 0.7s (good)
  ✅ Error rate: 0.2% (excellent)
  ✅ All services healthy

📚 6 AM: Usage learning update
  ✅ Shortcut for "schedule" active
  ✅ Sir prefers short answers (< 50 words)
  ✅ No ignored suggestions yet

🧠 System adapts:
  - Shorter responses
  - Schedule queries routed to briefing
  - Response time further optimized
```

### Day 7: Maintenance
```
2 AM Sunday: Weekly maintenance runs
  🧹 Archived 3 log files
  📊 Trimmed stats (kept last 500 queries)
  🗑️  Deleted 12 old tasks
  🗄️  Database optimized
  
Result: Database back to ~50 MB (was growing)
```

---

## ⚙️ Configuration & Tuning

### Health Check Thresholds
```python
# In health_monitor.py - adjust if needed:

ALERT_THRESHOLD_RESPONSE_TIME = 3.0  # seconds
ALERT_THRESHOLD_ERROR_RATE = 0.15  # 15%
ALERT_THRESHOLD_MEMORY_GROWTH = 100  # MB per hour
```

### Auto-Recovery Cooldown
```python
# In auto_recovery.py - prevent recovery thrashing:

RECOVERY_COOLDOWN = 300  # 5 minutes
```

---

## 🚨 Understanding Alerts

### Red Flag: Response Time Spike
```
Alert: "Slow responses: 3.2s"

Causes:
  ❌ Ollama server slow
  ❌ Network latency
  ❌ High CPU load

Auto-Recovery:
  ✅ Switch to performance mode (more Gemini)
  ✅ Temporarily reduce context size
  ✅ Next check: Monitor recovery

Action: Check Ollama server health
```

### Red Flag: High Error Rate
```
Alert: "High error rate: 18%"

Causes:
  ❌ TTS API failures
  ❌ Corrupted memory data
  ❌ Network issues

Auto-Recovery:
  ✅ Run memory cleanup
  ✅ Clear error-prone cache
  ✅ Restart voice service if needed

Action: Check API quotas
```

### Red Flag: Memory Leak
```
Alert: "Memory growing at 150 MB/hour"

Causes:
  ❌ Conversation history bloat
  ❌ Unclosed file handles
  ❌ Memory leak in service

Auto-Recovery:
  ✅ Aggressive cleanup (keep 10 conversations)
  ✅ Force garbage collection
  ✅ Next check: Monitor trend

Action: Investigate service logs
```

---

## 🧪 Testing Phase 3

### Test Auto-Recovery
```bash
# Simulate Ollama down
pkill -f ollama

# Wait 30 min (auto-recovery trigger)
# Check logs for recovery attempt

# Start Ollama again
# System should resume normal operation
```

### Test Weekly Cleanup
```bash
# Force weekly maintenance (for testing)
python -c "
from backend.app.services.weekly_maintenance import WeeklyMaintenance
result = WeeklyMaintenance.run_weekly_maintenance()
print(result)
"
```

### Test Usage Learning
```bash
# Log some commands
from backend.app.services.usage_learner import get_learner
learner = get_learner()
learner.log_command("schedule")
learner.log_command("schedule")
learner.log_command("schedule")
learner.log_command("schedule")  # Threshold: 3 repeats

# Check if shortcut created
shortcuts = learner.identify_command_shortcut()
print(shortcuts)  # Should show "schedule" shortcut
```

---

## 📈 What to Watch Over Next 2 Weeks

### Optimal Health Metrics
```
Response Time:  0.5–1.5s ✅
Error Rate:     < 1% ✅
Memory Usage:   < 150 MB ✅
Service Status: All green ✅
```

### Learning Indicators
```
Command shortcuts: Increasing ✅
Ignored suggestions: Decreasing ✅
Response accuracy: Improving ✅
User satisfaction: Rising 👍
```

---

## 🔧 Common Operations

### Check System Status
```bash
python -c "
from backend.app.services.health_monitor import get_health_monitor
from backend.app.services.usage_learner import get_learner
from backend.app.services.usage_monitor import get_monitor

health = get_health_monitor().get_health_summary()
learning = get_learner().get_learning_summary()
usage = get_monitor().get_stats_summary()

print('═' * 60)
print('ORION OPERATIONS STATUS')
print('═' * 60)
print(f'Health: {health}')
print(f'Learning: {learning}')
print(f'Usage: {usage}')
"
```

### Force Memory Cleanup
```bash
python -c "
from backend.app.services.memory_service import MemoryService
mem = MemoryService()
mem.cleanup_conversations('default_user', keep_count=15)
mem.run_maintenance()
print('✅ Cleanup complete')
"
```

### Reset Learning (if needed)
```bash
rm data/usage_patterns.json
# System will restart learning from scratch
```

---

## 🚀 What Happens Automatically

| Task | When | What | Result |
|------|------|------|--------|
| Health Check | 6 AM daily | Monitor response time, errors, memory | Alerts if issues |
| Auto-Recovery | Every 30 min | Heal if degraded | System self-fixes |
| Weekly Cleanup | Sunday 2 AM | Archive logs, trim stats, optimize DB | Long-term stability |
| Usage Learning | Every 6 hours | Analyze patterns, identify shortcuts | System customizes |
| Memory Cleanup | 3 AM daily | Remove old history, trim memory | Database stays lean |
| Morning Briefing | 8 AM daily | Provide schedule summary | Sir stays informed |

---

## 🏁 Phase 3 Status Checklist

- [x] Health monitoring (daily + continuous)
- [x] Auto-recovery (triggers on degradation)
- [x] Usage learning (learns shortcuts + preferences)
- [x] Weekly maintenance (prevents long-term issues)
- [x] Scheduler integration (all tasks scheduled)
- [x] Alerting system (DEV alerts, never bothers Sir)
- [x] Self-healing (no human intervention needed)

---

## 📞 When to Intervene

**You need to intervene if:**
- Same alert appears 3+ days in a row
- Auto-recovery not working (alerts still present)
- Memory keeps growing despite cleanup
- Service health shows "error" for > 6 hours

**You DO NOT need to intervene if:**
- Occasional spike (one-time alert)
- Auto-recovery succeeds (alert cleared)
- Health issue during low-traffic time
- System recovers within 1 hour

---

## 🎯 Final Setup (One-Time)

1. ✅ All Phase 3 modules imported
2. ✅ Scheduler jobs added to main.py
3. ✅ Health/Learning/Recovery systems active
4. ✅ Weekly cleanup scheduled
5. ✅ Data collection active

**System is now self-maintaining and self-healing.**

---

**Next:** Monitor for 1-2 weeks, collect real usage data, then optimize further.

**ORION is now production-grade with enterprise-level reliability.**

