"""
WebSocket Handler — ORION Real-Time Bidirectional Communication
================================================================
Replaces SSE with a persistent WebSocket connection between
Pi 3 (Body) and Pi 4 (Brain).

Why WebSocket over SSE for this setup:
  • Pi 3 can PUSH events to Pi 4 (face detected, mood changed)
  • Pi 4 can PUSH proactive alerts to Pi 3 (meetings, battery)
  • Single persistent TCP connection — less overhead on Pi network
  • Pi 3 can interrupt/cancel mid-stream
  • No polling needed for notifications

Protocol (JSON messages):
─────────────────────────────────────────────────────────────
Pi 3 → Pi 4 (client sends):

  {"type": "chat",        "user_id": "Vaishnavi", "message": "What time is it?"}
  {"type": "face",        "user_id": "Vaishnavi", "action": "detected"}
  {"type": "face",        "user_id": "Unknown",   "action": "detected"}
  {"type": "mood",        "mood": "Happy"}
  {"type": "ping"}
  {"type": "interrupt"}   ← stop current AI response

Pi 4 → Pi 3 (server sends):

  {"type": "ack",         "text": "Let me check that."}
  {"type": "token",       "text": "The weather in "}
  {"type": "token",       "text": "Kochi is 32°C."}
  {"type": "done",        "full_response": "The weather..."}
  {"type": "greeting",    "text": "Good morning Vaishnavi!"}
  {"type": "alert",       "text": "Meeting in 15 minutes!"}
  {"type": "error",       "message": "..."}
  {"type": "pong"}
─────────────────────────────────────────────────────────────
"""

import asyncio
import json
import time
from typing import Dict, Optional, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.intent_router import IntentRouter
from app.services.greeting_service import GreetingService
from app.services.memory_service import MemoryService
from app.core.logging import get_logger

logger = get_logger()

router = APIRouter()


class ConnectionManager:
    """
    Manages all active WebSocket connections.
    Allows Pi 4 to push proactive alerts to connected Pi 3 clients.
    """

    def __init__(self):
        # user_id → WebSocket
        self.active: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active[user_id] = ws
        logger.info(f"[WS] Client connected: {user_id} "
                    f"(total connections: {len(self.active)})")

    def disconnect(self, user_id: str):
        self.active.pop(user_id, None)
        logger.info(f"[WS] Client disconnected: {user_id}")

    async def push(self, user_id: str, message: dict):
        """Push a message to a specific connected client."""
        ws = self.active.get(user_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning(f"[WS] Push to {user_id} failed: {e}")
                self.disconnect(user_id)

    async def broadcast(self, message: dict):
        """Push a message to all connected clients."""
        disconnected = []
        for user_id, ws in self.active.items():
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(user_id)
        for uid in disconnected:
            self.disconnect(uid)

    def is_connected(self, user_id: str) -> bool:
        return user_id in self.active


# Singleton — shared across the app so proactive alerts can push to clients
manager = ConnectionManager()


class SessionHandler:
    """
    Handles all messages for a single WebSocket session.
    One instance per connected Pi 3 client.
    """

    def __init__(
        self,
        ws: WebSocket,
        user_id: str,
        intent_router: IntentRouter,
        greeting_service: GreetingService,
        memory_service: MemoryService,
        movement_service: Optional[Any] = None,
    ):
        self.ws = ws
        self.user_id = user_id
        self.intent_router = intent_router
        self.greeting_service = greeting_service
        self.memory = memory_service
        self.movement_service = movement_service

        self._interrupt = asyncio.Event()
        self._stream_task: Optional[asyncio.Task] = None

        # OMNIS-style: track last interaction time for 5s global cooldown
        self._last_interaction_time: float = 0
        # OMNIS-style: after greeting, conversation is active (no wake word needed)
        self.conversation_active: bool = False

    async def send(self, message: dict):
        """Send JSON to this client."""
        await self.ws.send_json(message)

    async def handle(self):
        """Main message loop for this session."""
        async for raw in self._receive_loop():
            if raw is None:
                break
            await self._dispatch(raw)

    async def _receive_loop(self):
        """Yield parsed messages, handle disconnect gracefully."""
        try:
            while True:
                data = await self.ws.receive_text()
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    logger.warning(f"[WS] Invalid JSON from {self.user_id}: {data[:100]}")
        except WebSocketDisconnect:
            logger.info(f"[WS] {self.user_id} disconnected cleanly.")
            yield None
        except Exception as e:
            logger.error(f"[WS] Receive error for {self.user_id}: {e}")
            yield None

    async def _dispatch(self, msg: dict):
        """Route incoming message to the correct handler."""
        msg_type = msg.get("type", "")

        if msg_type == "chat":
            await self._handle_chat(msg)

        elif msg_type in ("vision", "vision_query"):
            await self._handle_vision(msg)

        elif msg_type == "face":
            await self._handle_face(msg)

        elif msg_type == "mood":
            mood = msg.get("mood", "Neutral")
            self.intent_router.current_mood = mood
            logger.debug(f"[WS] Mood updated: {mood}")

        elif msg_type == "interrupt":
            await self._handle_interrupt()

        elif msg_type == "ping":
            await self.send({"type": "pong"})

        else:
            logger.warning(f"[WS] Unknown message type: {msg_type}")

    # ──────────────────────────────────────────
    # CHAT & VISION — Streaming handlers
    # ──────────────────────────────────────────

    async def _handle_chat(self, msg: dict):
        """Process a chat message with debounce."""
        message = msg.get("message", "").strip()
        user_id = msg.get("user_id", self.user_id)

        if not message:
            return

        now = time.time()
        if (now - self._last_interaction_time) < 0.5 and self._last_interaction_time > 0:
            logger.debug(f"[WS] Interaction debounce active, ignoring: {message[:30]}")
            return
        self._last_interaction_time = now

        logger.info(f"[WS] {user_id}: {message}")

        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            await asyncio.sleep(0)

        self._interrupt.clear()

        # Check if client sent image along with chat
        image_b64 = msg.get("image", None)
        image_bytes = None
        if image_b64:
            import base64
            try:
                if "," in image_b64:
                    image_b64 = image_b64.split(",", 1)[1]
                image_bytes = base64.b64decode(image_b64)
            except Exception as e:
                logger.error(f"[WS] Failed to decode image payload: {e}")

        self._stream_task = asyncio.create_task(
            self._stream_response(user_id, message, image_bytes=image_bytes)
        )
        try:
            await self._stream_task
        except asyncio.CancelledError:
            await self.send({"type": "interrupted"})

    async def _handle_vision(self, msg: dict):
        """Process visual query with optional client-captured image."""
        user_id = msg.get("user_id", self.user_id)
        question = msg.get("question", msg.get("message", "What is this object?")).strip()
        image_b64 = msg.get("image", None)
        image_bytes = None
        if image_b64:
            import base64
            try:
                if "," in image_b64:
                    image_b64 = image_b64.split(",", 1)[1]
                image_bytes = base64.b64decode(image_b64)
            except Exception as e:
                logger.error(f"[WS] Failed to decode image payload: {e}")

        logger.info(f"[WS] Vision query from {user_id}: '{question}' (image provided: {image_bytes is not None})")

        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            await asyncio.sleep(0)

        self._interrupt.clear()
        self._stream_task = asyncio.create_task(
            self._stream_response(user_id, question, image_bytes=image_bytes)
        )
        try:
            await self._stream_task
        except asyncio.CancelledError:
            await self.send({"type": "interrupted"})

    async def _stream_response(self, user_id: str, message: str, image_bytes: Optional[bytes] = None):
        """Stream AI response tokens to the client."""
        full_response = ""
        ack_sent = False

        try:
            async for chunk in self.intent_router.process_stream(user_id, message, image_bytes=image_bytes):
                # Check for interrupt
                if self._interrupt.is_set():
                    await self.send({"type": "interrupted"})
                    return

                if not chunk:
                    continue

                # First chunk that is an ACK phrase — send as ack only, don't echo as token
                if not ack_sent and chunk.strip() in self.intent_router.ack_phrases:
                    await self.send({"type": "ack", "text": chunk})
                    ack_sent = True
                    continue  # skip adding to full_response and skip token send

                # All other chunks are real response tokens
                full_response += chunk
                await self.send({"type": "token", "text": chunk})

                # Yield to event loop so other messages can be processed
                await asyncio.sleep(0)

        except asyncio.CancelledError:
            raise  # Let the task handler deal with it
        except Exception as e:
            logger.error(f"[WS] Stream error for {user_id}: {e}")
            await self.send({"type": "error", "message": str(e)[:200]})
            return

        # Stream complete
        await self.send({
            "type": "done",
            "full_response": full_response.strip(),
            "user_id": user_id
        })

    # ──────────────────────────────────────────
    # FACE — Pi 3 pushes face detection events
    # ──────────────────────────────────────────

    async def _handle_face(self, msg: dict):
        """Pi 3 detected a face. Pi 4 generates greeting, triggers movement."""
        detected_user = msg.get("user_id", "Unknown")
        action = msg.get("action", "detected")
        distance = msg.get("distance", None)  # optional distance in meters

        if action != "detected":
            return

        logger.info(f"[WS] Face detected: {detected_user}")
        self.user_id = detected_user

        # ── Movement decision via TinyLlama ──
        if self.movement_service:
            dist_str = f"at {distance}m" if distance else "at unknown distance"
            situation = f"Person '{detected_user}' detected {dist_str}, greeting mode"
            mv = self.movement_service
            try:
                loop = asyncio.get_running_loop()
                loop.run_in_executor(
                    None,
                    lambda: mv.decide_and_move(situation)
                )
            except RuntimeError:
                pass

        # ── Greeting ──
        greeting = self.greeting_service.get_greeting(detected_user)
        if greeting:
            self._last_interaction_time = time.time()
            await self.send({
                "type": "greeting",
                "text": greeting,
                "user_id": detected_user
            })
            self.conversation_active = True
            await self.send({"type": "conversation_active", "value": True})
            logger.info(f"[WS] Greeting + conversation handoff → {detected_user}")

    # ──────────────────────────────────────────
    # INTERRUPT
    # ──────────────────────────────────────────

    async def _handle_interrupt(self):
        """Pi 3 wants to stop current AI response (user spoke again)."""
        logger.info(f"[WS] Interrupt received from {self.user_id}")
        self._interrupt.set()
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()


# ──────────────────────────────────────────
# WEBSOCKET ENDPOINT
# ──────────────────────────────────────────

def create_ws_endpoint(
    intent_router: IntentRouter,
    greeting_service: GreetingService,
    memory_service: MemoryService,
    movement_service: Optional[Any] = None,
):
    """
    Factory to create the WebSocket endpoint with injected services.
    Called from main.py.
    """

    # ── Register GET /ws/status BEFORE /ws/{user_id} ──
    # FastAPI matches routes in registration order. If /ws/{user_id} is first,
    # it would match /ws/status as user_id="status". Status must come first.
    @router.get("/ws/status")
    async def ws_status():
        """Shows active WebSocket connections."""
        return {
            "protocol": "WebSocket",
            "active_connections": len(manager.active),
            "connected_users": list(manager.active.keys()),
        }

    @router.websocket("/ws/{user_id}")
    async def websocket_endpoint(websocket: WebSocket, user_id: str):
        """
        Persistent WebSocket connection for a Pi 3 client.

        Connect:  ws://<PI4_IP>:8000/ws/Vaishnavi
        Messages: See protocol docs at top of file.
        """
        await manager.connect(user_id, websocket)
        handler = SessionHandler(
            ws=websocket,
            user_id=user_id,
            intent_router=intent_router,
            greeting_service=greeting_service,
            memory_service=memory_service,
            movement_service=movement_service,
        )
        try:
            await handler.handle()
        finally:
            manager.disconnect(user_id)

    return router
