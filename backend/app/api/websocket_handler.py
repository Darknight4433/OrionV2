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
from typing import Dict, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.intent_router import IntentRouter
from ..services.greeting_service import GreetingService
from ..services.memory_service import MemoryService
from ..core.logging import get_logger

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
    ):
        self.ws = ws
        self.user_id = user_id
        self.intent_router = intent_router
        self.greeting_service = greeting_service
        self.memory = memory_service

        # Interrupt flag — set to True when Pi 3 sends {"type": "interrupt"}
        self._interrupt = asyncio.Event()
        # Current streaming task — cancelled on interrupt
        self._stream_task: Optional[asyncio.Task] = None

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
    # CHAT — Main streaming handler
    # ──────────────────────────────────────────

    async def _handle_chat(self, msg: dict):
        """
        Process a chat message and stream response tokens back.
        Runs in a task so it can be cancelled by an interrupt.
        """
        message = msg.get("message", "").strip()
        user_id = msg.get("user_id", self.user_id)

        if not message:
            return

        logger.info(f"[WS] {user_id}: {message}")

        # Cancel any in-progress stream
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            await asyncio.sleep(0)

        self._interrupt.clear()

        # Create new stream task
        self._stream_task = asyncio.create_task(
            self._stream_response(user_id, message)
        )
        try:
            await self._stream_task
        except asyncio.CancelledError:
            await self.send({"type": "interrupted"})

    async def _stream_response(self, user_id: str, message: str):
        """Stream AI response tokens to the client."""
        full_response = ""
        first_chunk = True

        try:
            async for chunk in self.intent_router.process_stream(user_id, message):
                # Check for interrupt
                if self._interrupt.is_set():
                    await self.send({"type": "interrupted"})
                    return

                if not chunk:
                    continue

                if first_chunk:
                    # First chunk — send as ACK (spoken immediately)
                    await self.send({"type": "ack", "text": chunk})
                    first_chunk = False
                    # Don't include filler in full_response
                    if chunk.strip() in self.intent_router.ack_phrases:
                        continue

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
        """
        Pi 3 detected a face. Pi 4 generates a greeting and pushes it back.
        This replaces the old polling GET /greet endpoint.
        """
        detected_user = msg.get("user_id", "Unknown")
        action = msg.get("action", "detected")

        if action != "detected":
            return

        logger.info(f"[WS] Face detected: {detected_user}")

        # Update current user in router
        self.user_id = detected_user

        # Generate greeting
        greeting = self.greeting_service.get_greeting(detected_user)
        if greeting:
            await self.send({
                "type": "greeting",
                "text": greeting,
                "user_id": detected_user
            })
            logger.info(f"[WS] Greeting sent: {greeting[:60]}")

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
):
    """
    Factory to create the WebSocket endpoint with injected services.
    Called from main.py.
    """

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
        )
        try:
            await handler.handle()
        finally:
            manager.disconnect(user_id)

    @router.get("/ws/status")
    async def ws_status():
        """Shows active WebSocket connections."""
        return {
            "protocol": "WebSocket",
            "active_connections": len(manager.active),
            "connected_users": list(manager.active.keys()),
        }

    return router
