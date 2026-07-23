"""
AI Manager — ORION V2
======================
OMNIS-style multi-key rotation pool with full fallback chain:

  Groq (llama-3.1-8b-instant) — PRIMARY
    • Free tier: 14,400 req/day, 6000 tokens/min
    • ~500ms response, runs on Groq LPU chips
    • Rotates across multiple keys if pool provided

  Gemini (gemini-2.0-flash-lite) — SECONDARY
    • Free tier backup, rotates across key pool on 429
    • Dynamic model discovery — always picks fastest available

  Ollama (local CPU) — LAST RESORT
    • Offline fallback, no internet needed
    • Slow on CPU (~10s) but always available

Key pool sources (in priority order):
  1. GROQ_API_KEYS list in .env
  2. GROQ_API_KEY single key in .env
  3. GEMINI_API_KEYS list in .env
"""

import asyncio
import json
import re
import time
import requests
import google.generativeai as genai
from enum import Enum
from typing import AsyncGenerator, Optional, Dict, Any, List
from dataclasses import dataclass, field
from .config import settings
from .logging import get_logger

logger = get_logger()


class AIProvider(str, Enum):
    GROQ   = "groq"    # Primary — free, ~500ms
    GEMINI = "gemini"  # Secondary — free tier with key rotation
    LOCAL  = "ollama"  # Last resort — CPU offline


class QueryComplexity(str, Enum):
    SIMPLE   = "simple"
    MODERATE = "moderate"
    COMPLEX  = "complex"
    INTERNET = "internet"


@dataclass
class ProviderHealth:
    available: bool = True
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    cooldown_until: float = 0

    def mark_failure(self, error: str):
        self.consecutive_failures += 1
        self.last_error = error
        backoff = min(10 * (2 ** (self.consecutive_failures - 1)), 120)
        self.cooldown_until = time.time() + backoff
        if self.consecutive_failures >= 3:
            self.available = False

    def mark_success(self):
        self.consecutive_failures = 0
        self.available = True
        self.cooldown_until = 0

    def is_ready(self) -> bool:
        if not self.available and time.time() > self.cooldown_until:
            self.available = True
        return self.available


class AIManager:

    def __init__(self):
        self.health: Dict[AIProvider, ProviderHealth] = {
            AIProvider.GROQ:   ProviderHealth(),
            AIProvider.GEMINI: ProviderHealth(),
            AIProvider.LOCAL:  ProviderHealth(),
        }

        # ── Groq key pool ──
        # Supports multiple keys: GROQ_API_KEYS=["key1","key2"] or single GROQ_API_KEY
        self.groq_keys: List[str] = list(getattr(settings, "GROQ_API_KEYS", []))
        single = getattr(settings, "GROQ_API_KEY", "")
        if single and single not in self.groq_keys:
            self.groq_keys.insert(0, single)
        self.groq_key_index = 0
        self.groq_model = getattr(settings, "GROQ_MODEL", "llama-3.1-8b-instant")

        # ── Gemini key pool ──
        self.gemini_keys: List[str] = list(getattr(settings, "GEMINI_API_KEYS", []))
        self.gemini_key_index = 0
        self.gemini_model_cache: Optional[str] = None

        # ── Ollama ──
        self.ollama_url   = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = getattr(settings, "OLLAMA_MODEL", "phi3:latest")

        logger.info(
            f"AI Manager ready — "
            f"Groq: {len(self.groq_keys)} key(s) | "
            f"Gemini: {len(self.gemini_keys)} key(s) | "
            f"Ollama: {self.ollama_model} (CPU fallback)"
        )

    # ──────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────

    async def generate(
        self,
        user_id: str,
        prompt: str,
        complexity: QueryComplexity = QueryComplexity.MODERATE,
        system_context: str = "",
        force_provider: Optional[AIProvider] = None
    ) -> AsyncGenerator[str, None]:

        chain = [force_provider] if force_provider else self._get_provider_chain()

        for provider in chain:
            if not self.health[provider].is_ready():
                logger.debug(f"Skipping {provider.value} (cooldown)")
                continue
            try:
                got = False
                async for chunk in self._call_provider(provider, prompt, system_context):
                    got = True
                    yield chunk
                if got:
                    self.health[provider].mark_success()
                    return
            except Exception as e:
                self.health[provider].mark_failure(str(e))
                logger.warning(f"{provider.value} failed: {str(e)[:80]} → trying next")
                continue

        yield "I'm having trouble connecting right now. Please try again."

    def get_health_status(self) -> Dict[str, Any]:
        return {
            p.value: {
                "available": h.is_ready(),
                "failures": h.consecutive_failures,
                "last_error": h.last_error,
            }
            for p, h in self.health.items()
        }

    # ──────────────────────────────────────────
    # ROUTING
    # ──────────────────────────────────────────

    def _get_provider_chain(self) -> list:
        """Groq → Gemini → Ollama. Always this order."""
        return [AIProvider.GROQ, AIProvider.GEMINI, AIProvider.LOCAL]

    # ──────────────────────────────────────────
    # DISPATCH
    # ──────────────────────────────────────────

    async def _call_provider(
        self, provider: AIProvider, prompt: str, system_context: str = ""
    ) -> AsyncGenerator[str, None]:
        if provider == AIProvider.GROQ:
            async for chunk in self._stream_groq(prompt, system_context):
                yield chunk
        elif provider == AIProvider.GEMINI:
            async for chunk in self._stream_gemini(prompt, system_context):
                yield chunk
        elif provider == AIProvider.LOCAL:
            async for chunk in self._stream_ollama(prompt, system_context):
                yield chunk

    # ──────────────────────────────────────────
    # GROQ — Primary (~500ms, free)
    # ──────────────────────────────────────────

    async def _stream_groq(self, prompt: str, system_context: str = "") -> AsyncGenerator[str, None]:
        if not self.groq_keys:
            raise RuntimeError("No Groq API keys configured. Get a free key at https://console.groq.com")

        from groq import Groq

        max_retries = len(self.groq_keys)
        retries = 0

        while retries < max_retries:
            key = self.groq_keys[self.groq_key_index]
            messages = []
            if system_context:
                messages.append({"role": "system", "content": system_context})
            messages.append({"role": "user", "content": prompt})

            try:
                loop = asyncio.get_event_loop()

                def _call():
                    client = Groq(api_key=key)
                    return client.chat.completions.create(
                        model=self.groq_model,
                        messages=messages,
                        stream=True,
                        max_tokens=300,
                        temperature=0.4,
                    )

                stream = await loop.run_in_executor(None, _call)
                got = False
                for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        got = True
                        yield delta.content
                if got:
                    return

            except Exception as e:
                err = str(e).lower()
                if any(x in err for x in ["quota", "429", "rate", "limit", "exceeded"]):
                    logger.warning(f"Groq key #{self.groq_key_index} quota hit. Rotating...")
                    self._rotate_groq()
                    retries += 1
                else:
                    raise

        raise RuntimeError(f"All {len(self.groq_keys)} Groq key(s) exhausted")

    def _rotate_groq(self):
        self.groq_key_index = (self.groq_key_index + 1) % len(self.groq_keys)
        logger.info(f"Groq → key #{self.groq_key_index}")

    # ──────────────────────────────────────────
    # GEMINI — Secondary (free tier, key rotation)
    # ──────────────────────────────────────────

    async def _stream_gemini(self, prompt: str, system_context: str = "") -> AsyncGenerator[str, None]:
        if not self.gemini_keys:
            raise RuntimeError("No Gemini API keys configured")

        max_retries = len(self.gemini_keys)
        retries = 0

        while retries < max_retries:
            key = self.gemini_keys[self.gemini_key_index]
            genai.configure(api_key=key)
            model_name = self._discover_gemini_model()

            try:
                model = genai.GenerativeModel(
                    model_name,
                    system_instruction=system_context if system_context else None
                )
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: model.generate_content(prompt, stream=True)
                )
                buf = ""
                for chunk in response:
                    try:
                        if chunk.text:
                            buf += chunk.text
                            parts = re.split(r'(?<=[.!?\n]) ', buf)
                            if len(parts) > 1:
                                for p in parts[:-1]:
                                    if p.strip():
                                        yield p.strip() + " "
                                buf = parts[-1]
                    except (ValueError, AttributeError):
                        continue
                if buf.strip():
                    yield buf.strip()
                return

            except Exception as e:
                err = str(e).lower()
                if any(x in err for x in ["quota", "429", "exhausted", "resource", "limit"]):
                    logger.warning(f"Gemini key #{self.gemini_key_index} quota hit. Rotating...")
                    self._rotate_gemini()
                    retries += 1
                else:
                    raise

        raise RuntimeError(f"All {len(self.gemini_keys)} Gemini key(s) exhausted")

    def _rotate_gemini(self):
        self.gemini_key_index = (self.gemini_key_index + 1) % len(self.gemini_keys)
        self.gemini_model_cache = None  # reset so model is rediscovered on next key
        logger.info(f"Gemini → key #{self.gemini_key_index}")

    def _discover_gemini_model(self) -> str:
        if self.gemini_model_cache:
            return self.gemini_model_cache
        try:
            candidates = [
                m.name for m in genai.list_models()
                if "generateContent" in m.supported_generation_methods
                and not any(x in m.name for x in ["research", "thinking", "exp", "tts", "image"])
            ]
            for preferred in ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-flash-lite-latest", "gemini-2.5-flash"]:
                match = next((m for m in candidates if preferred in m), None)
                if match:
                    self.gemini_model_cache = match
                    logger.info(f"Gemini model selected: {match}")
                    return match
            if candidates:
                self.gemini_model_cache = candidates[0]
                return candidates[0]
        except Exception:
            pass
        return "models/gemini-2.0-flash-lite"

    # ──────────────────────────────────────────
    # OLLAMA — Last resort (local CPU)
    # ──────────────────────────────────────────

    async def _stream_ollama(self, prompt: str, system_context: str = "") -> AsyncGenerator[str, None]:
        url = f"{self.ollama_url}/api/chat"
        messages = []
        if system_context:
            messages.append({"role": "system", "content": system_context})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": True,
            "options": {
                "num_ctx": 1024,
                "temperature": 0.3,
                "stop": ["User:", "Human:", "\nUser", "\nHuman", "Speaker:"]
            }
        }
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(url, json=payload, stream=True, timeout=60)
        )
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line.decode("utf-8"))
                if "message" in chunk and "content" in chunk["message"]:
                    content = chunk["message"]["content"]
                    if content:
                        yield content
                if chunk.get("done"):
                    break
