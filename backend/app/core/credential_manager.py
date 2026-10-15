"""
Credential Manager — ORION V2
==============================
Secure multi-token rotation, failure cooldown, and health tracking.
Complies with Specification Section 7 & Section 30:
  • Never logs actual tokens (uses masked labels like 'HF-Key#1')
  • Exponential backoff and cooldown tracking on provider failures
  • Avoids repeatedly hammering failed credentials
  • Clean fallback trigger when all credentials exhausted
"""

import time
import re
from typing import List, Optional, Dict
from dataclasses import dataclass, field
from app.core.logging import get_logger

logger = get_logger()


@dataclass
class TokenState:
    label: str
    token: str
    is_available: bool = True
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    last_used: float = 0.0
    last_error: Optional[str] = None

    def mark_failure(self, error: str):
        self.consecutive_failures += 1
        self.last_error = error
        # Exponential backoff: 10s, 20s, 40s, capped at 120s
        backoff = min(10 * (2 ** (self.consecutive_failures - 1)), 120)
        self.cooldown_until = time.time() + backoff
        if self.consecutive_failures >= 3:
            self.is_available = False
        logger.warning(
            f"[CREDENTIAL] {self.label} failed ({error[:60]}). "
            f"Cooldown: {backoff}s. Failures: {self.consecutive_failures}."
        )

    def mark_success(self):
        self.consecutive_failures = 0
        self.is_available = True
        self.cooldown_until = 0.0
        self.last_used = time.time()

    def is_ready(self) -> bool:
        if not self.is_available and time.time() > self.cooldown_until:
            self.is_available = True
        return self.is_available and (time.time() >= self.cooldown_until)


class CredentialManager:
    """
    Manages rotation and failover between authorized credentials
    for a specific service (Hugging Face, Gemini, etc.).
    """

    def __init__(self, service_name: str, tokens: List[str]):
        self.service_name = service_name
        self.token_states: List[TokenState] = []
        self._current_index = 0

        # Deduplicate and register non-empty tokens
        seen = set()
        for idx, tok in enumerate(tokens, 1):
            if not tok or not tok.strip():
                continue
            cleaned = tok.strip()
            # Ignore placeholder templates
            if cleaned.lower().startswith("your_") or cleaned.lower().startswith("hf_your_"):
                continue
            if cleaned not in seen:
                seen.add(cleaned)
                label = f"{service_name}-Key#{len(self.token_states) + 1}"
                self.token_states.append(TokenState(label=label, token=cleaned))

        logger.info(
            f"[CREDENTIAL] {service_name} CredentialManager initialized with {len(self.token_states)} authorized key(s)."
        )

    @property
    def total_keys(self) -> int:
        return len(self.token_states)

    def get_token(self) -> Optional[TokenState]:
        """
        Retrieves the next available, healthy credential using round-robin.
        Returns None if all credentials are on cooldown or exhausted.
        """
        if not self.token_states:
            return None

        now = time.time()
        n = len(self.token_states)

        for attempt in range(n):
            idx = (self._current_index + attempt) % n
            state = self.token_states[idx]
            if state.is_ready():
                self._current_index = (idx + 1) % n
                return state

        logger.warning(
            f"[CREDENTIAL] All {n} {self.service_name} credentials are on cooldown or exhausted."
        )
        return None

    def get_status(self) -> Dict[str, dict]:
        """Returns non-sensitive metadata for telemetry and monitoring."""
        return {
            s.label: {
                "available": s.is_ready(),
                "failures": s.consecutive_failures,
                "cooldown_remaining": max(0.0, s.cooldown_until - time.time()),
                "last_used": s.last_used,
            }
            for s in self.token_states
        }
