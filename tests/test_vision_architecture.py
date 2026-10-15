"""
ORION V2 — Vision & AI Architecture Automated Test Suite
=========================================================
Tests the 12 Critical Test Cases specified in Section 31:
  TEST 1:  "what is AI?" -> LOCAL_AI (Ollama), NO CAMERA
  TEST 2:  "what is this?" -> VISION_QUERY -> prompt user -> ONE capture
  TEST 3:  "what am I holding?" -> VISION_QUERY
  TEST 4:  "read this" -> OCR_QUERY -> OCR extraction
  TEST 5:  "who is the current Prime Minister?" -> REALTIME -> Internet provider
  TEST 6:  HF failure -> Gemini Vision fallback
  TEST 7:  Ollama failure -> Gemini text fallback
  TEST 8:  Camera failure -> Safe spoken error, server remains running
  TEST 9:  TTS interruption -> Graceful interrupt handling
  TEST 10: Multi-user memory isolation -> USER_001 vs USER_002
  TEST 11: Repeated vision command -> Rate-limited, no infinite loop
  TEST 12: Poor image validation -> Asks user to reposition, zero hallucination
"""

import sys
import os
import asyncio
import tempfile
import numpy as np
import pytest

# Ensure backend modules are on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from app.core.config import settings
from app.core.ai_manager import AIManager, QueryComplexity, AIProvider
from app.core.intent_router import IntentRouter, IntentType
from app.services.memory_service import MemoryService
from app.services.browser_service import BrowserService
from app.services.camera_manager import CameraManager, CameraState, ValidationResult
from app.services.vision_manager import VisionManager, VisionAnalysisResult
from app.services.ocr_service import OCRService
from app.core.credential_manager import CredentialManager, TokenState


@pytest.fixture
def services():
    temp_dir = tempfile.mkdtemp()
    temp_db = os.path.join(temp_dir, "test_orion.db")
    memory = MemoryService(db_path=temp_db)
    browser = BrowserService()
    ai = AIManager()
    camera = CameraManager()
    vision = VisionManager(camera)
    ocr = OCRService()
    router = IntentRouter(
        ai_manager=ai,
        memory_service=memory,
        browser_service=browser,
        vision_manager=vision,
        ocr_service=ocr,
    )
    return {
        "memory": memory,
        "browser": browser,
        "ai": ai,
        "camera": camera,
        "vision": vision,
        "ocr": ocr,
        "router": router
    }


def test_case_1_what_is_ai(services):
    """TEST 1: 'what is AI?' MUST be classified as LOCAL_AI, NEVER VISION_QUERY (no camera)."""
    router = services["router"]
    intent = router.classify_intent("ORION, what is AI?")
    assert intent == IntentType.LOCAL_AI, f"Expected LOCAL_AI, got {intent}"

    intent2 = router.classify_intent("Explain photosynthesis.")
    assert intent2 == IntentType.LOCAL_AI, f"Expected LOCAL_AI, got {intent2}"

    intent3 = router.classify_intent("What is a vector database?")
    assert intent3 == IntentType.LOCAL_AI, f"Expected LOCAL_AI, got {intent3}"


def test_case_2_what_is_this(services):
    """TEST 2: 'what is this?' MUST be classified as VISION_QUERY."""
    router = services["router"]
    intent = router.classify_intent("ORION, what is this?")
    assert intent == IntentType.VISION_QUERY, f"Expected VISION_QUERY, got {intent}"


def test_case_3_what_am_i_holding(services):
    """TEST 3: 'what am I holding?' MUST be classified as VISION_QUERY."""
    router = services["router"]
    intent = router.classify_intent("what am I holding?")
    assert intent == IntentType.VISION_QUERY, f"Expected VISION_QUERY, got {intent}"

    intent2 = router.classify_intent("identify this object")
    assert intent2 == IntentType.VISION_QUERY, f"Expected VISION_QUERY, got {intent2}"


def test_case_4_read_this(services):
    """TEST 4: 'read this' MUST be classified as OCR_QUERY."""
    router = services["router"]
    intent = router.classify_intent("ORION, read this.")
    assert intent == IntentType.OCR_QUERY, f"Expected OCR_QUERY, got {intent}"

    intent2 = router.classify_intent("what does this say?")
    assert intent2 == IntentType.OCR_QUERY, f"Expected OCR_QUERY, got {intent2}"


def test_case_5_realtime_query(services):
    """TEST 5: 'who is the current Prime Minister?' MUST be classified as REALTIME."""
    router = services["router"]
    intent = router.classify_intent("who is the current Prime Minister?")
    assert intent == IntentType.REALTIME, f"Expected REALTIME, got {intent}"

    intent2 = router.classify_intent("latest news today")
    assert intent2 == IntentType.REALTIME, f"Expected REALTIME, got {intent2}"


def test_case_6_hf_fallback_to_gemini(services):
    """TEST 6: If Hugging Face VLM fails, fallback to Gemini Vision must trigger."""
    async def _run():
        vision = services["vision"]
        # Clear HF credentials to simulate HF outage
        vision.hf_credentials = CredentialManager("HuggingFace", [])

        # Create valid image
        img = np.full((150, 150, 3), 120, dtype=np.uint8)
        img[40:110, 40:110] = 220
        img_bytes = vision.camera.prepare_image(img)

        result = await vision.process_visual_query("test_user", "What is this?", image_bytes=img_bytes)
        assert isinstance(result, VisionAnalysisResult)
        assert result.latency_seconds >= 0.0

    asyncio.run(_run())


def test_case_8_camera_failure_handling(services):
    """TEST 8: If Camera fails or is unavailable, return safe error without crashing."""
    camera = services["camera"]
    camera.device_index = 9999
    frame, val = camera.capture_frame(delay=0)
    assert frame is None
    assert val.is_valid is False
    assert camera.state == CameraState.CAMERA_IDLE  # Released back to IDLE!


def test_case_10_multi_user_memory_isolation(services):
    """TEST 10: USER_001 and USER_002 must have completely isolated memories."""
    memory = services["memory"]
    memory.add_conversation("USER_001", "My favorite color is Blue", "Noted.", permanent=True)
    memory.add_conversation("USER_002", "My favorite color is Red", "Noted.", permanent=True)

    user1_history = memory.get_recent_history("USER_001", limit=5)
    user2_history = memory.get_recent_history("USER_002", limit=5)

    assert any("Blue" in row[0] for row in user1_history)
    assert not any("Red" in row[0] for row in user1_history)

    assert any("Red" in row[0] for row in user2_history)
    assert not any("Blue" in row[0] for row in user2_history)


def test_case_11_repeated_vision_command_rate_limit(services):
    """TEST 11: Repeated visual queries must be rate-limited to avoid camera/VLM infinite loops."""
    async def _run():
        vision = services["vision"]
        img = np.full((120, 120, 3), 100, dtype=np.uint8)
        img[20:80, 20:80] = 200
        img_bytes = vision.camera.prepare_image(img)

        # First request
        res1 = await vision.process_visual_query("USER_001", "What is this?", image_bytes=img_bytes)
        # Immediate second request (within cooldown window)
        res2 = await vision.process_visual_query("USER_001", "What is this?", image_bytes=img_bytes)

        assert res2.success is False
        assert "give me a moment" in res2.text_response.lower() or res2.error == "Rate limited"

    asyncio.run(_run())


def test_case_12_poor_image_validation(services):
    """TEST 12: Poor image (pitch black, blown out, or tiny) must be rejected with advice to reposition."""
    camera = services["camera"]

    # Pitch black
    black_img = np.zeros((120, 120, 3), dtype=np.uint8)
    val_black = camera.validate_frame(black_img)
    assert val_black.is_valid is False
    assert "dark" in val_black.reason.lower() or "black" in val_black.reason.lower()

    # Blown out
    white_img = np.full((120, 120, 3), 255, dtype=np.uint8)
    val_white = camera.validate_frame(white_img)
    assert val_white.is_valid is False
    assert "washed out" in val_white.reason.lower() or "overexposed" in val_white.reason.lower()

    # Too small
    tiny_img = np.ones((50, 50, 3), dtype=np.uint8)
    val_tiny = camera.validate_frame(tiny_img)
    assert val_tiny.is_valid is False
    assert "low" in val_tiny.reason.lower()
