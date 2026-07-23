"""
ORION Brain — Main Application Server (V2)
============================================
Event-driven FastAPI server with:
  • WebSocket for real-time bidirectional Pi 3 ↔ Pi 4 communication
  • AI Manager with multi-provider routing (Ollama/TinyLlama → Gemini → OpenRouter)
  • Intent Router with rule engine + internet detection
  • Proactive scheduler — pushes alerts directly to Pi 3 via WebSocket
  • Backward-compatible /chat endpoint (blocking, for testing/fallback)
  • Safe Mode middleware for disk pressure protection
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

# Core
from app.core.config import settings
from app.core.logging import get_logger
from app.core.lifecycle import LifecycleManager
from app.core.ai_manager import AIManager
from app.core.intent_router import IntentRouter

# Services
from app.services.memory_service import MemoryService
from app.services.browser_service import BrowserService
from app.services.greeting_service import GreetingService

# API Routers
from app.api import monitoring
from app.api.websocket_handler import create_ws_endpoint, manager as ws_manager

logger = get_logger()

# ──────────────────────────────────────────
# APP INITIALIZATION
# ──────────────────────────────────────────

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="ORION AI Assistant — WebSocket + Event-Driven Architecture"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────
# MIDDLEWARE
# ──────────────────────────────────────────

@app.middleware("http")
async def safe_mode_middleware(request: Request, call_next):
    """Block writes when system is in disk pressure SAFE MODE."""
    if LifecycleManager.is_safe_mode() and request.method not in ["GET", "HEAD"]:
        return JSONResponse(
            status_code=503,
            content={"error": "System in SAFE MODE. Writes disabled."}
        )
    return await call_next(request)


# ──────────────────────────────────────────
# SERVICE INITIALIZATION
# ──────────────────────────────────────────

memory_service  = MemoryService()
browser_service = BrowserService()
greeting_service = GreetingService(memory_service)
ai_manager      = AIManager()
intent_router   = IntentRouter(
    ai_manager=ai_manager,
    memory_service=memory_service,
    browser_service=browser_service,
)

scheduler = AsyncIOScheduler()

# ──────────────────────────────────────────
# ROUTERS
# ──────────────────────────────────────────

app.include_router(monitoring.router)

# WebSocket endpoint — primary Pi 3 ↔ Pi 4 channel
ws_router = create_ws_endpoint(intent_router, greeting_service, memory_service)
app.include_router(ws_router)

# ──────────────────────────────────────────
# LIFECYCLE
# ──────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    logger.info("=" * 55)
    logger.info("  ORION Brain V2 — WebSocket Architecture")
    logger.info(f"  AI: Ollama/gemma3 (primary) → Gemini (fallback)")
    logger.info("=" * 55)

    LifecycleManager()

    missed = memory_service.check_missed_meetings()
    if missed:
        logger.warning(f"Recovered {len(missed)} missed alerts on startup.")

    scheduler.add_job(
        _check_upcoming_meetings,
        IntervalTrigger(minutes=1),
        id="meeting_checker"
    )
    scheduler.add_job(
        memory_service.run_maintenance,
        CronTrigger(hour=3, minute=0),
        id="daily_janitor"
    )
    scheduler.start()
    logger.info("Scheduler started.")


@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    await browser_service.close()
    logger.info("ORION Brain shutdown.")


# ──────────────────────────────────────────
# PROACTIVE SCHEDULER
# ──────────────────────────────────────────

async def _check_upcoming_meetings():
    """
    Runs every 60 seconds.
    Finds alerts due within 15 minutes and pushes them directly
    to connected Pi 3 clients via WebSocket — no polling needed.
    """
    import time
    now = time.time()
    window = now + (15 * 60)  # 15 minutes ahead

    try:
        import sqlite3
        from app.core.config import PROJECT_ROOT
        import os
        db_path = os.path.join(PROJECT_ROOT, "data", "orion.db")
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT user_id, content FROM system_alerts
                   WHERE scheduled_time BETWEEN ? AND ?
                   AND read_status = 0
                   AND alert_type IN ('task', 'meeting', 'reminder')""",
                (now, window)
            )
            alerts = cursor.fetchall()

        for user_id, content in alerts:
            msg = {"type": "alert", "text": f"Reminder: {content}"}
            if ws_manager.is_connected(user_id):
                await ws_manager.push(user_id, msg)
                logger.info(f"[ALERT] Pushed to {user_id}: {content[:60]}")
            else:
                logger.debug(f"[ALERT] {user_id} not connected — alert queued in DB.")

    except Exception as e:
        logger.error(f"Meeting checker error: {e}")


# ──────────────────────────────────────────
# HTTP ENDPOINTS (fallback / testing)
# ──────────────────────────────────────────

class ChatRequest(BaseModel):
    user_id: str = "default_user"
    message: str

class ChatResponse(BaseModel):
    response: str

class NotificationResponse(BaseModel):
    notifications: List[str]


@app.get("/")
def root():
    return {
        "status": "ORION is online",
        "version": settings.VERSION,
        "protocol": "WebSocket",
        "ws_endpoint": "ws://<host>:8000/ws/<user_id>",
        "providers": ai_manager.get_health_status(),
        "active_ws_connections": len(ws_manager.active),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Blocking HTTP fallback for testing or simple clients.
    Use WebSocket /ws/<user_id> for real-time streaming.
    """
    logger.info(f"[HTTP/chat] {request.user_id}: {request.message}")
    full_response = ""
    async for chunk in intent_router.process_stream(request.user_id, request.message):
        if chunk.strip() not in intent_router.ack_phrases:
            full_response += chunk
    return ChatResponse(response=full_response.strip())


@app.get("/notifications", response_model=NotificationResponse)
async def get_notifications(user_id: str = "default_user"):
    """HTTP fallback for clients that can't use WebSocket."""
    alerts = memory_service.get_pending_notifications(user_id)
    return NotificationResponse(notifications=alerts)


@app.post("/personality")
async def set_personality(persona: str):
    intent_router.current_persona = persona
    return {"status": f"Persona set to: {persona}"}


@app.post("/mood")
async def update_mood(mood: str):
    intent_router.current_mood = mood
    return {"status": f"Mood updated: {mood}"}


@app.get("/ai/status")
async def ai_status():
    return {
        "providers": ai_manager.get_health_status(),
        "persona": intent_router.current_persona,
        "mood": intent_router.current_mood,
        "ws_connections": len(ws_manager.active),
    }
