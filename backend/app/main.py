from fastapi import FastAPI, UploadFile, File, Form, Depends
from pydantic import BaseModel
from typing import Optional, List
import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .core.intent_engine import IntentEngine
from .services.memory_service import MemoryService
from .services.gemini_service import GeminiService
from .services.ollama_service import OllamaService
from .services.browser_service import BrowserService
from .services.greeting_service import GreetingService
from .services.vision_service import VisionService
from .services.habit_service import HabitDetector
from .services.habit_suggester import HabitSuggester
from .services.decision_engine import DecisionEngine
from .services.planner_engine import PlannerEngine
from .services.briefing_engine import BriefingEngine
from .core.config import settings
from .core.logging import get_logger
from .api import monitoring

from .core.logging import get_logger
from .api import monitoring
from .core.lifecycle import LifecycleManager
from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = get_logger()

# send one alert text per interval to avoid user spam
last_action_sent = {}  # {text: timestamp}


def should_send_notification(text: str, cooldown_sec: int = 300) -> bool:
    now = time.time()
    if text in last_action_sent and now - last_action_sent[text] < cooldown_sec:
        return False
    last_action_sent[text] = now
    return True


app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

# Middleware: Safe Mode Gatekeeper
@app.middleware("http")
async def safe_mode_middleware(request: Request, call_next):
    # Check cached state (Fast)
    is_danger = LifecycleManager.is_safe_mode()
    
    if is_danger and request.method not in ["GET", "HEAD"]:
        return JSONResponse(
            status_code=503, 
            content={"error": "System in SAFE MODE. Writes disabled."}
        )
        
    response = await call_next(request)
    return response

# Initialize Lifecycle Monitor on Startup
@app.on_event("startup")
async def start_lifecycle_monitor():
    LifecycleManager() # Starts daemon thread

# Include Monitoring Router
app.include_router(monitoring.router)

# ─────────────────────────────────────────────
#  HEALTH & SAFE MODE ENDPOINTS (PRODUCTION)
# ─────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Watchdog health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.get("/safe")
async def safe_mode_fallback():
    """Safe mode fallback when everything fails"""
    return {
        "response": "System is running in safe mode. Basic functions only.",
        "ai_mode": "safe"
    }

# Dependency Injection
memory_service = MemoryService()
gemini_service = GeminiService(memory_service)
ollama_service = OllamaService(memory_service)
browser_service = BrowserService()
vision_service = VisionService()
habit_detector = HabitDetector(memory_service)
habit_suggester = HabitSuggester(memory_service)
greeting_service = GreetingService(memory_service)
decision_engine = DecisionEngine(memory_service, habit_suggester)
planner_engine = PlannerEngine()
briefing_engine = BriefingEngine(memory_service)
intent_engine = IntentEngine(
    gemini_service,
    ollama_service,
    memory_service,
    browser_service,
    vision_service,
    habit_detector,
    habit_suggester,
    briefing_engine
)

# Proactive Scheduler
scheduler = AsyncIOScheduler()

# --- Proactive Task ---
async def check_upcoming_meetings():
    """Ran every minute to check for meetings starting soon."""
    logger.info("Checking for upcoming tasks...")
    # Logic: Get meetings from DB that start within 15 mins
    # If found, add to a 'notification queue' for the client to poll
    # In v1, we just write to a log or a specific 'notifications' table
    # Notifications are pulled by client via /notifications
    pass

async def check_habit_suggestions():
    """Check for habit suggestions every 5 minutes."""
    user_id = "default_user"
    last = memory_service.get_last_activity(user_id)
    if last and time.time() - last < 30:
        return  # User engaged in conversation
    
    suggestion = habit_suggester.check_and_suggest(user_id, last_input_time=last, last_output_time=None)
    if suggestion:
        # Add as notification for client to speak
        memory_service.add_system_alert(user_id, suggestion, "habit_suggestion")
        logger.info(f"Habit suggestion: {suggestion}")


async def check_best_action():
    """Decision engine poll: choose top candidate, expand with planner, and notify."""
    user_id = "default_user"
    last_active = memory_service.get_last_activity(user_id)
    if last_active and time.time() - last_active < 30:
        return

    action = decision_engine.choose_best_action(user_id, last_input_time=last_active, last_output_time=None)
    if action:
        # Expand action with planner context
        planned_action = planner_engine.build_plan(action, memory_service)
        
        if should_send_notification(planned_action["text"]):
            # Send expanded plan instead of raw action
            memory_service.add_system_alert(user_id, planned_action["text"], "decision")
            logger.info(f"Decision action sent (planned): {planned_action['type']} - {planned_action['text']}")
        else:
            logger.info(f"Decision action skipped as duplicate/recent: {planned_action['text']}")


async def morning_briefing():
    """Send morning briefing at 8:00 AM daily."""
    user_id = "default_user"
    briefing = briefing_engine.get_morning_briefing(user_id)
    memory_service.add_system_alert(user_id, briefing, "briefing")
    logger.info(f"Morning briefing sent: {briefing}")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting ORION Brain...")
    
    # Recovery: Check for missed meetings
    missed = memory_service.check_missed_meetings()
    if missed:
        logger.warning(f"Recovered {len(missed)} missed meetings during downtime.")
        # In a real system, we'd push these to a 'missed alerts' queue immediately
        
    scheduler.add_job(check_upcoming_meetings, IntervalTrigger(minutes=1))
    scheduler.add_job(check_best_action, IntervalTrigger(minutes=3))
    
    # Daily Maintenance (The Janitor) - Runs at 3 AM
    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(memory_service.run_maintenance, CronTrigger(hour=3, minute=0))
    
    # Morning Briefing - Runs at 8:00 AM daily
    scheduler.add_job(morning_briefing, CronTrigger(hour=8, minute=0))
    
    # ================== PHASE 3: REAL-WORLD HARDENING ==================
    # Daily Health Check at 6 AM
    async def daily_health_check_job():
        from .services.health_monitor import get_health_monitor
        from .services.usage_monitor import get_monitor
        from .services.auto_recovery import auto_recovery_check
        
        monitor = get_health_monitor()
        usage_stats = get_monitor().stats
        health_status = monitor.run_full_health_check(usage_stats)
        
        # If issues found, trigger recovery
        if not health_status["healthy"]:
            logger.warning(f"🚨 Health check found issues: {health_status['alerts']}")
            recovery_result = auto_recovery_check(health_status)
            if recovery_result["recovered"]:
                logger.info(f"✅ Auto-recovery executed: {recovery_result['actions_taken']}")
    
    # Auto-recovery check every 30 minutes
    async def periodic_auto_recovery():
        from .services.health_monitor import get_health_monitor
        from .services.usage_monitor import get_monitor
        from .services.auto_recovery import auto_recovery_check
        
        monitor = get_health_monitor()
        usage_stats = get_monitor().stats
        health_status = monitor.run_full_health_check(usage_stats)
        
        if not health_status["healthy"]:
            auto_recovery_check(health_status)
    
    # Weekly maintenance on Sunday at 2 AM
    async def weekly_maintenance_job():
        from .services.weekly_maintenance import weekly_maintenance_check
        result = weekly_maintenance_check()
        if result["executed"]:
            logger.info("✅ Weekly maintenance executed")
    
    # Usage learning summary every 6 hours
    async def usage_learning_job():
        from .services.usage_learner import get_learner
        learner = get_learner()
        summary = learner.get_learning_summary()
        logger.info(f"📚 Usage patterns updated: {summary}")
    
    scheduler.add_job(daily_health_check_job, CronTrigger(hour=6, minute=0))
    scheduler.add_job(periodic_auto_recovery, IntervalTrigger(minutes=30))
    scheduler.add_job(weekly_maintenance_job, CronTrigger(day_of_week=6, hour=2, minute=0))  # Sunday 2 AM
    scheduler.add_job(usage_learning_job, IntervalTrigger(hours=6))
    
    logger.info("✅ Phase 3 Real-World Hardening scheduled")
    # ===================================================================
    
    scheduler.start()
    logger.info("Scheduler started (Poller + Janitor + Daily Briefing + Phase 3 Hardening).")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    await browser_service.close()
    logger.info("ORION Brain Shutdown.")

# --- API Models ---
class ChatRequest(BaseModel):
    user_id: str = "default_user"
    message: str
    image: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    ai_mode: str

class NotificationResponse(BaseModel):
    notifications: List[str]

# --- Endpoints ---

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    logger.info(f"User {request.user_id}: {request.message}")
    response_text, ai_mode = await intent_engine.process(request.user_id, request.message, image_b64=request.image)
    return ChatResponse(response=response_text, ai_mode=ai_mode)

@app.get("/notifications", response_model=NotificationResponse)
async def get_notifications(user_id: str = "default_user"):
    """Client polls this endpoint for proactive alerts."""
    alerts = memory_service.get_pending_notifications()
    if alerts:
        logger.info(f"Serving {len(alerts)} alerts to {user_id}")
    return NotificationResponse(notifications=alerts)

@app.get("/schedule")
async def get_schedule(user_id: str = "default_user"):
    """Get current day's schedule and pending tasks (Sir asks: What's my schedule?)."""
    briefing = briefing_engine.get_context_briefing(user_id)
    return {"schedule": briefing}

@app.post("/voice")
async def voice_endpoint(file: UploadFile = File(...), user_id: str = Form(...)):
    # Placeholder for Whisper
    return {"error": "Voice transcription not yet implemented on backend. Send text."}

@app.get("/")
def health_check():
    return {"status": "ORION is online", "version": settings.VERSION}

# --- OMNIS Sync Endpoints ---

@app.get("/greet")
async def greet_user(user_id: str = "Unknown"):
    """Triggered by GUI when a face is detected."""
    greeting = greeting_service.get_greeting(user_id)
    if greeting:
        return {"greeting": greeting}
    return {"greeting": None}

@app.post("/personality")
async def set_personality(persona: str):
    """Change ORION's persona (e.g., 'William Shakespeare', 'NASA Scientist')."""
    intent_engine.current_persona = persona
    return {"status": f"Persona set to {persona}"}

@app.post("/mood")
async def update_mood(mood: str):
    """Update user mood detected via computer vision."""
    intent_engine.current_mood = mood
    return {"status": f"Mood updated: {mood}"}

