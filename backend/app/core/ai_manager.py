"""
AI Manager — The Unified AI Gateway for ORION
==============================================
Provider Logic:
  1. Ollama (gemma3) — PRIMARY. Local, free, always tried first.
                        Handles 100% of queries when running.
  2. Gemini API      — FALLBACK only. Used when Ollama is down or unreachable.

OpenRouter has been removed — not needed with this setup.
"""

import asyncio
import json
import re
import time
import requests
import google.generativeai as genai
from enum import Enum
from typing import AsyncGenerator, Optional, Dict, Any
from dataclasses import dataclass, field
from .config import settings
from .logging import get_logger

logger = get_logger()


class AIProvider(str, Enum):
    LOCAL = "ollama"    # Primary — gemma3 via Ollama, always tried first
    GEMINI = "gemini"   # Fallback — cloud, only when Ollama is down


class QueryComplexity(str, Enum):
    SIMPLE = "simple"        # Time, greetings, basic facts -> Local
    MODERATE = "moderate"    # Conversation, explanation -> Local first, Gemini fallback
    COMPLEX = "complex"      # Reasoning, summarization, research -> Gemini/OpenRouter
    INTERNET = "internet"    # Needs web search before AI processing


@dataclass
class AIResponse:
    """Structured response from any AI provider."""
    provider: AIProvider
    text: str
    tokens_used: int = 0
    latency_ms: float = 0
    success: bool = True
    error: Optional[str] = None


@dataclass
class ProviderHealth:
    """Tracks provider availability."""
    available: bool = True
    last_error: Optional[str] = None
    last_error_time: float = 0
    consecutive_failures: int = 0
    cooldown_until: float = 0  # Unix timestamp

    def mark_failure(self, error: str):
        self.consecutive_failures += 1
        self.last_error = error
        self.last_error_time = time.time()
        # Exponential backoff: 10s, 30s, 60s, 120s max
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
            # Allow retry after cooldown
            self.available = True
        return self.available


class AIManager:
    """
    Unified AI Gateway.
    
    Usage:
        manager = AIManager()
        async for chunk in manager.generate(user_id, prompt, complexity):
            # stream chunk to client
    """

    def __init__(self):
        # Provider health tracking — Ollama primary, Gemini fallback only
        self.health: Dict[AIProvider, ProviderHealth] = {
            AIProvider.LOCAL: ProviderHealth(),
            AIProvider.GEMINI: ProviderHealth(),
        }

        # Gemini state (fallback only — used when Ollama is down)
        self.gemini_keys = settings.GEMINI_API_KEYS
        self.gemini_key_index = 0
        self.gemini_model_cache: Optional[str] = None

        # Ollama state (primary brain — always tried first)
        self.ollama_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = getattr(settings, "OLLAMA_MODEL", "gemma3")
        self.is_tinyllama = "tinyllama" in self.ollama_model.lower()

        logger.info(f"AI Manager initialized. Primary: Ollama/{self.ollama_model}, "
                    f"Fallback: Gemini ({'configured' if self.gemini_keys else 'no keys — Ollama only'})")

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
        """
        Stream AI response tokens. Automatically routes to the best provider.
        
        Yields individual text chunks as they arrive.
        """
        # Determine provider chain based on complexity
        if force_provider:
            chain = [force_provider]
        else:
            chain = self._get_provider_chain(complexity)

        full_prompt = f"{system_context}\n{prompt}" if system_context else prompt

        for provider in chain:
            if not self.health[provider].is_ready():
                logger.debug(f"Skipping {provider.value} (cooldown)")
                continue

            try:
                start_time = time.time()
                token_count = 0
                got_response = False

                async for chunk in self._call_provider(provider, user_id, full_prompt):
                    got_response = True
                    token_count += 1
                    yield chunk

                if got_response:
                    latency = (time.time() - start_time) * 1000
                    self.health[provider].mark_success()
                    logger.info(f"AI response complete. Provider: {provider.value}, "
                               f"Tokens: ~{token_count}, Latency: {latency:.0f}ms")
                    return  # Success — don't try next provider

            except Exception as e:
                error_msg = str(e)
                self.health[provider].mark_failure(error_msg)
                logger.warning(f"{provider.value} failed: {error_msg}. Trying next provider...")
                # Yield a system notification about failover
                yield f"\n[Switching to backup AI...]\n"
                continue

        # All providers failed
        yield "I'm having trouble connecting to my AI systems right now. Please try again in a moment."

    def get_health_status(self) -> Dict[str, Any]:
        """Returns health status of all providers for monitoring."""
        return {
            provider.value: {
                "available": health.is_ready(),
                "consecutive_failures": health.consecutive_failures,
                "last_error": health.last_error,
            }
            for provider, health in self.health.items()
        }

    # ──────────────────────────────────────────
    # ROUTING LOGIC
    # ──────────────────────────────────────────

    def _get_provider_chain(self, complexity: QueryComplexity) -> list:
        """
        Provider chain:
          ALL queries → Ollama (gemma3) first — free, local, always on
          If Ollama fails → Gemini API fallback
          OpenRouter is intentionally removed.
        """
        return [AIProvider.LOCAL, AIProvider.GEMINI]

    # ──────────────────────────────────────────
    # PROVIDER IMPLEMENTATIONS
    # ──────────────────────────────────────────

    async def _call_provider(
        self, provider: AIProvider, user_id: str, prompt: str
    ) -> AsyncGenerator[str, None]:
        """Dispatch to the correct provider's streaming implementation."""
        if provider == AIProvider.LOCAL:
            async for chunk in self._stream_ollama(prompt):
                yield chunk
        elif provider == AIProvider.GEMINI:
            async for chunk in self._stream_gemini(prompt):
                yield chunk

    # ── Ollama (Local) ──

    async def _stream_ollama(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        Stream from local Ollama instance.
        TinyLlama uses chatml format:
          <|system|>...</s><|user|>...</s><|assistant|>
        We split the prompt into system + user parts automatically.
        """
        url = f"{self.ollama_url}/api/chat"

        # The generate() method prepends system_context with a "\n" separator:
        #   full_prompt = f"{system_context}\n{prompt}"
        # We split on the LAST newline to separate system context from the user query.
        # This correctly handles multi-line system context (which contains many \n).
        sep = "\n"
        split_idx = prompt.rfind(sep)
        if split_idx != -1:
            system_part = prompt[:split_idx].strip()
            user_part = prompt[split_idx + 1:].strip()
        else:
            system_part = ""
            user_part = prompt.strip()

        if system_part:
            messages = [
                {"role": "system", "content": system_part},
                {"role": "user",   "content": user_part}
            ]
        else:
            messages = [{"role": "user", "content": user_part}]

        # Context window: Gemma3 supports up to 8192, but cap to 4096 for Windows RAM.
        # On Pi 4 with 4GB RAM keep at 2048 or lower.
        num_ctx = 4096 if not self.is_tinyllama else 1024

        payload = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": True,
            "options": {
                "num_ctx": num_ctx,
                "temperature": 0.7,
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

    # ── Gemini (Cloud Primary) ──

    async def _stream_gemini(self, prompt: str) -> AsyncGenerator[str, None]:
        """Stream from Google Gemini with key rotation."""
        if not self.gemini_keys:
            raise RuntimeError("No Gemini API keys configured")

        max_retries = len(self.gemini_keys)
        retries = 0

        while retries < max_retries:
            try:
                key = self.gemini_keys[self.gemini_key_index]
                genai.configure(api_key=key)

                model_name = self._discover_gemini_model()
                model = genai.GenerativeModel(model_name)

                # Run blocking Gemini call in thread pool
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: model.generate_content(prompt, stream=True)
                )

                output_buffer = ""
                for chunk in response:
                    try:
                        if chunk.text:
                            output_buffer += chunk.text
                            # Yield sentence-by-sentence for low-latency TTS
                            parts = re.split(r'(?<=[.!?\n]) ', output_buffer)
                            if len(parts) > 1:
                                for p in parts[:-1]:
                                    if p.strip():
                                        yield p.strip() + " "
                                output_buffer = parts[-1]
                    except (ValueError, AttributeError):
                        continue

                # Flush remaining buffer
                if output_buffer.strip():
                    yield output_buffer.strip()
                return  # Success

            except Exception as e:
                err = str(e).lower()
                if any(kw in err for kw in ["quota", "429", "resource", "limit", "exhausted"]):
                    logger.warning(f"Gemini key #{self.gemini_key_index} exhausted. Rotating...")
                    self._rotate_gemini_key()
                    retries += 1
                else:
                    raise  # Non-quota errors should bubble up

        raise RuntimeError(f"All {max_retries} Gemini keys exhausted")

    def _rotate_gemini_key(self):
        self.gemini_key_index = (self.gemini_key_index + 1) % len(self.gemini_keys)

    def _discover_gemini_model(self) -> str:
        """Find the best available Gemini model."""
        if self.gemini_model_cache:
            return self.gemini_model_cache

        try:
            candidates = [
                m.name for m in genai.list_models()
                if "generateContent" in m.supported_generation_methods
            ]
            # Priority order
            for preferred in ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]:
                match = next((m for m in candidates if preferred in m), None)
                if match:
                    self.gemini_model_cache = match
                    return match
            if candidates:
                self.gemini_model_cache = candidates[0]
                return candidates[0]
        except Exception:
            pass

        return "gemini-1.5-flash"

    # ── OpenRouter removed — Ollama is primary, Gemini is the only fallback ──
