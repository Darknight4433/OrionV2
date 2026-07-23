"""
SSE Streaming API — ORION Real-Time Response Delivery
======================================================
Server-Sent Events endpoint that streams AI tokens to the client
in real-time. This is what makes ORION feel instant.

Protocol:
  Client sends POST /stream with {user_id, message}
  Server responds with text/event-stream:
    event: ack
    data: {"text": "Let me check that."}
    
    event: token  
    data: {"text": "The weather"}
    
    event: token
    data: {"text": " in Kerala is"}
    
    event: done
    data: {"full_response": "The weather in Kerala is..."}

Benefits over /chat:
  • First token arrives in <500ms (vs waiting 3-10s for full response)
  • Client can start TTS immediately on first sentence
  • User sees ORION is "thinking" in real-time
  • Supports interruption (client can close connection)
"""

import json
import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from ..core.intent_router import IntentRouter
from ..core.logging import get_logger

logger = get_logger()

router = APIRouter()


class StreamRequest(BaseModel):
    user_id: str = "default_user"
    message: str


def format_sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event message."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_response(intent_router: IntentRouter, user_id: str, message: str):
    """
    Async generator that yields SSE-formatted events.
    
    Events:
      - ack: First response (acknowledgment/filler)
      - token: Each chunk of the AI response
      - done: Final event with complete response
      - error: If something goes wrong
    """
    full_response = ""
    first_chunk = True
    
    try:
        async for chunk in intent_router.process_stream(user_id, message):
            if not chunk:
                continue
                
            # First chunk is typically the ACK
            if first_chunk:
                yield format_sse("ack", {"text": chunk})
                first_chunk = False
                # Don't add ACK to full_response if it's a filler
                if chunk.strip() in intent_router.ack_phrases or chunk.strip().endswith("..."):
                    continue
            
            # Subsequent chunks are response tokens
            full_response += chunk
            yield format_sse("token", {"text": chunk})
            
            # Small yield to allow other coroutines to run
            await asyncio.sleep(0)

    except asyncio.CancelledError:
        logger.info(f"Stream cancelled by client for user {user_id}")
        yield format_sse("cancelled", {"reason": "Client disconnected"})
        return
    except Exception as e:
        logger.error(f"Stream error for {user_id}: {e}")
        yield format_sse("error", {"message": str(e)[:200]})
        return

    # Final event
    yield format_sse("done", {
        "full_response": full_response.strip(),
        "user_id": user_id
    })


def create_stream_endpoint(intent_router: IntentRouter):
    """
    Factory function to create the streaming endpoint with the router dependency.
    Called from main.py after services are initialized.
    """

    @router.post("/stream")
    async def stream_chat(request: StreamRequest):
        """
        SSE Streaming endpoint.
        
        POST /stream
        Body: {"user_id": "Vaishnavi", "message": "What's the weather like?"}
        
        Response: text/event-stream with token-by-token delivery
        """
        logger.info(f"[STREAM] {request.user_id}: {request.message}")

        return StreamingResponse(
            stream_response(intent_router, request.user_id, request.message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            }
        )

    @router.get("/stream/health")
    async def stream_health():
        """Check if streaming endpoint is operational."""
        return {"status": "ok", "protocol": "SSE", "version": "2.0"}

    return router
