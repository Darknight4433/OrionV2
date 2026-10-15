"""
Vision Manager — ORION V2
==========================
Vision-Language Model (VLM) reasoning layer with multi-provider fallback.
Complies with Specification Sections 5, 6, 7, 8, 12, 13, 17, 18, 20, 24, 28:
  • Primary: Hugging Face Inference API (Qwen/Qwen2.5-VL-3B-Instruct)
  • Fallback: Google Gemini Vision (gemini-1.5-flash / gemini-2.0-flash)
  • Single-request rate limit (1 capture -> 1 VLM inference -> 1 voice response)
  • Strict system prompt enforcing factual, non-hallucinated 1-2 sentence answers
  • User identification isolation (user_id logged in conversation, raw image discarded)
"""

import time
import json
import base64
import requests
import asyncio
import google.generativeai as genai
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

from app.core.config import settings
from app.core.credential_manager import CredentialManager, TokenState
from app.core.logging import get_logger
from app.services.camera_manager import CameraManager, ValidationResult

logger = get_logger()

VISION_SYSTEM_PROMPT = (
    "You are ORION's visual analysis module.\n"
    "Analyze only the provided image and the user's question.\n"
    "Describe only information supported by the image.\n"
    "Do not invent details.\n"
    "Do not guess when the image is unclear.\n"
    "If an object is partially hidden, state that.\n"
    "Answer the user's specific question.\n"
    "Keep the answer concise and suitable for voice output.\n"
    "Normally respond in 1–2 sentences.\n"
    "Address the user respectfully as Sir when appropriate."
)


@dataclass
class VisionAnalysisResult:
    success: bool
    text_response: str
    provider_used: str
    latency_seconds: float
    validation: Optional[ValidationResult] = None
    error: Optional[str] = None


class VisionManager:
    """
    Orchestrates the entire vision pipeline:
      Camera capture -> Validation -> HF VLM inference -> Gemini Vision fallback.
    """

    def __init__(self, camera_manager: Optional[CameraManager] = None):
        self.camera = camera_manager or CameraManager()

        # Collect HF tokens from environment and settings
        hf_tokens = list(getattr(settings, "HF_TOKENS", []))
        for key in ["HF_TOKEN_1", "HF_TOKEN_2", "HF_TOKEN_3"]:
            val = getattr(settings, key, "")
            if val and val not in hf_tokens:
                hf_tokens.append(val)

        self.hf_credentials = CredentialManager("HuggingFace", hf_tokens)
        self.hf_model = getattr(settings, "HF_VISION_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")

        # Gemini fallback keys
        self.gemini_keys = list(getattr(settings, "GEMINI_API_KEYS", []))
        for key in [
            "GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3",
            "GEMINI_API_KEY_4", "GEMINI_API_KEY_5", "GEMINI_API_KEYS_1", "GEMINI_API_KEYS_2",
            "GEMINI_API_KEYS_3", "GEMINI_API_KEYS_4"
        ]:
            val = getattr(settings, key, "")
            if val and val not in self.gemini_keys:
                self.gemini_keys.append(val)

        self.gemini_credentials = CredentialManager("Gemini", self.gemini_keys)

        # Rate limiting / Cooldown
        self._last_request_time: float = 0.0
        self._cooldown_seconds: float = 2.0

        logger.info(
            f"[VISION] VisionManager active: HF Model={self.hf_model}, "
            f"HF Keys={self.hf_credentials.total_keys}, Gemini Keys={self.gemini_credentials.total_keys}"
        )

    async def process_visual_query(
        self,
        user_id: str,
        question: str,
        image_bytes: Optional[bytes] = None,
        direct_frame = None
    ) -> VisionAnalysisResult:
        """
        Executes a complete single-frame visual analysis workflow:
          1. Rate-limit guard
          2. Acquisition of ONE frame if image_bytes not provided
          3. Image validation check
          4. HF VLM query with authorized credential
          5. Gemini Vision fallback if HF fails
          6. Respectful, non-hallucinated response
        """
        start_time = time.time()
        now = time.time()

        # 1. Rate-limiting guard
        if (now - self._last_request_time) < self._cooldown_seconds and self._last_request_time > 0:
            return VisionAnalysisResult(
                success=False,
                text_response="Sir, please give me a moment before showing another object.",
                provider_used="none",
                latency_seconds=time.time() - start_time,
                error="Rate limited"
            )
        self._last_request_time = now

        # 2. Acquire & Validate Frame
        val_result = None
        if image_bytes is None:
            if direct_frame is not None:
                val_result = self.camera.validate_frame(direct_frame)
                if val_result.is_valid:
                    image_bytes = self.camera.prepare_image(direct_frame)
            else:
                loop = asyncio.get_event_loop()
                frame, val_result = await loop.run_in_executor(None, self.camera.capture_frame)
                if val_result.is_valid and frame is not None:
                    image_bytes = self.camera.prepare_image(frame)

        if not image_bytes:
            reason = val_result.reason if val_result else "Could not capture image"
            logger.warning(f"[VISION] Frame invalid: {reason}")
            return VisionAnalysisResult(
                success=False,
                text_response="Sir, I couldn't get a clear view. Please hold the object closer to the camera and keep it steady.",
                provider_used="camera",
                latency_seconds=time.time() - start_time,
                validation=val_result,
                error=reason
            )

        # 3. Primary: Hugging Face VLM
        hf_token_state = self.hf_credentials.get_token()
        if hf_token_state is not None:
            try:
                hf_resp = await self._call_hf_vlm(hf_token_state, image_bytes, question)
                if hf_resp:
                    hf_token_state.mark_success()
                    logger.info(f"[VISION] HF VLM success via {hf_token_state.label}")
                    return VisionAnalysisResult(
                        success=True,
                        text_response=hf_resp,
                        provider_used=f"HuggingFace ({self.hf_model})",
                        latency_seconds=time.time() - start_time,
                        validation=val_result
                    )
            except Exception as e:
                logger.warning(f"[VISION] HF VLM failed: {e}. Initiating Gemini fallback...")
                hf_token_state.mark_failure(str(e))
        else:
            logger.info("[VISION] No available HF credentials. Proceeding directly to Gemini fallback.")

        # 4. Fallback: Gemini Vision
        gemini_token_state = self.gemini_credentials.get_token()
        if gemini_token_state is not None:
            try:
                gemini_resp = await self._call_gemini_vision(gemini_token_state, image_bytes, question)
                if gemini_resp:
                    gemini_token_state.mark_success()
                    logger.info(f"[VISION] Gemini Vision fallback success via {gemini_token_state.label}")
                    return VisionAnalysisResult(
                        success=True,
                        text_response=gemini_resp,
                        provider_used="Gemini-Vision",
                        latency_seconds=time.time() - start_time,
                        validation=val_result
                    )
            except Exception as e:
                logger.error(f"[VISION] Gemini Vision fallback failed: {e}")
                gemini_token_state.mark_failure(str(e))

        # 5. All providers failed
        return VisionAnalysisResult(
            success=False,
            text_response="Sir, I'm having trouble analyzing the visual feed right now. Please try again in a moment.",
            provider_used="none",
            latency_seconds=time.time() - start_time,
            error="All vision providers failed"
        )

    async def _call_hf_vlm(self, token_state: TokenState, image_bytes: bytes, question: str) -> str:
        """
        Calls Hugging Face router / inference API for Qwen2.5-VL / VLM models.
        """
        loop = asyncio.get_event_loop()
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{b64_image}"

        # Standard OpenAI-compatible format supported by HF Inference Providers
        payload = {
            "model": self.hf_model,
            "messages": [
                {
                    "role": "system",
                    "content": VISION_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question or "What is this object?"},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]
                }
            ],
            "max_tokens": 150,
            "temperature": 0.2
        }

        # Try Hugging Face Router endpoint
        endpoint = "https://router.huggingface.co/hf-inference/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {token_state.token}",
            "Content-Type": "application/json"
        }

        def _sync_req():
            res = requests.post(endpoint, json=payload, headers=headers, timeout=15)
            # If router 404 or unsupported, try standard api-inference endpoint
            if res.status_code == 404:
                legacy_url = f"https://api-inference.huggingface.co/models/{self.hf_model}/v1/chat/completions"
                res = requests.post(legacy_url, json=payload, headers=headers, timeout=15)
            res.raise_for_status()
            data = res.json()
            return data["choices"][0]["message"]["content"]

        answer = await loop.run_in_executor(None, _sync_req)
        return self._format_voice_response(answer)

    async def _call_gemini_vision(self, token_state: TokenState, image_bytes: bytes, question: str) -> str:
        """
        Calls Google Gemini Vision API as a reliable high-capability fallback.
        """
        loop = asyncio.get_event_loop()

        def _sync_gemini():
            genai.configure(api_key=token_state.token)
            # Find available vision-capable Gemini model
            model_name = "gemini-1.5-flash"
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=VISION_SYSTEM_PROMPT
            )
            image_part = {
                "mime_type": "image/jpeg",
                "data": image_bytes
            }
            prompt = question or "What is this object?"
            response = model.generate_content([prompt, image_part])
            return response.text

        answer = await loop.run_in_executor(None, _sync_gemini)
        return self._format_voice_response(answer)

    def _format_voice_response(self, text: str) -> str:
        """Cleans and standardizes response for natural 1-2 sentence voice delivery."""
        if not text:
            return "Sir, I can't identify that clearly from the image."

        cleaned = text.strip()
        # Remove common markdown symbols or role prefixes
        cleaned = cleaned.replace("```", "").replace("**", "").replace("*", "")
        if cleaned.startswith("ORION:"):
            cleaned = cleaned[6:].strip()

        # Ensure respectful address if not already present
        if not cleaned.lower().startswith("sir") and not cleaned.lower().startswith("it appears") and not cleaned.lower().startswith("that appears"):
            cleaned = f"Sir, {cleaned[0].lower() + cleaned[1:]}"

        return cleaned
