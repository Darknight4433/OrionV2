from fastapi import FastAPI, UploadFile, File, Form, Depends
from pydantic import BaseModel
from typing import Optional, List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.intent_engine import IntentEngine
from app.services.memory_service import MemoryService
from app.services.gemini_service import GeminiService
from app.services.ollama_service import OllamaService
from app.services.browser_service import BrowserService
from app.services.greeting_service import GreetingService
from app.services.vision_service import VisionService
from app.core.config import settings
from app.core.logging import get_logger
from app.api import monitoring

from app.core.logging import get_logger
from app.api import monitoring
from app.core.lifecycle import LifecycleManager
from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = get_logger()

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

# Dependency Injection
memory_service = MemoryService()
gemini_service = GeminiService(memory_service)
ollama_service = OllamaService(memory_service)
browser_service = BrowserService()
vision_service = VisionService()
intent_engine = IntentEngine(gemini_service, ollama_service, memory_service, browser_service, vision_service)
greeting_service = GreetingService(memory_service)

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

@app.on_event("startup")
async def startup_event():
    logger.info("Starting ORION Brain...")
    
    # Recovery: Check for missed meetings
    missed = memory_service.check_missed_meetings()
    if missed:
        logger.warning(f"Recovered {len(missed)} missed meetings during downtime.")
        # In a real system, we'd push these to a 'missed alerts' queue immediately
        
    scheduler.add_job(check_upcoming_meetings, IntervalTrigger(minutes=1))
    
    # Daily Maintenance (The Janitor) - Runs at 3 AM
    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(memory_service.run_maintenance, CronTrigger(hour=3, minute=0))
    
    scheduler.start()
    logger.info("Scheduler started (Poller + Janitor).")

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

class NotificationResponse(BaseModel):
    notifications: List[str]

# --- Endpoints ---

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    logger.info(f"User {request.user_id}: {request.message}")
    response_text = await intent_engine.process(request.user_id, request.message, image_b64=request.image)
    return ChatResponse(response=response_text)

@app.get("/notifications", response_model=NotificationResponse)
async def get_notifications(user_id: str = "default_user"):
    """Client polls this endpoint for proactive alerts."""
    alerts = memory_service.get_pending_notifications()
    if alerts:
        logger.info(f"Serving {len(alerts)} alerts to {user_id}")
    return NotificationResponse(notifications=alerts)

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

