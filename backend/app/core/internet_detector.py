"""
Internet Detection Service — ORION
====================================
Determines whether a user query requires internet search
BEFORE sending it to the AI for reasoning.

Decision Flow:
  1. Rule-based keyword matching (fast, no AI needed)
  2. Temporal detection (asks about "latest", "current", "today's news")
  3. Knowledge boundary detection (asks about specific people, events, prices)
  
If internet is needed:
  → Search → Collect Results → Inject into AI context

Design Principles:
  • This runs BEFORE the AI call, not during.
  • Must be fast (<10ms for rule-based detection).
  • False negatives are acceptable (AI can still answer from training).
  • False positives are expensive (unnecessary search latency).
"""

import re
from typing import Tuple, Optional, List
from dataclasses import dataclass
from .logging import get_logger

logger = get_logger()


@dataclass
class InternetDecision:
    """Result of internet detection analysis."""
    needs_internet: bool
    confidence: float  # 0.0 to 1.0
    reason: str
    search_query: Optional[str] = None  # Optimized query for search engine


class InternetDetector:
    """
    Fast rule-based detector for queries that need external knowledge.
    
    Categories that trigger internet search:
      • Current events / news
      • Prices, stocks, weather
      • Latest versions, releases
      • Specific factual lookups (who, what year, how much)
      • Explicit search requests
    
    Categories that DON'T need internet:
      • Personal questions (how are you, what's your name)
      • Task management (add meeting, remind me)
      • Conversational (tell me a joke, explain X)
      • Time/date queries (handled by rule engine)
      • Memory queries (what did I say yesterday)
    """

    # Patterns that STRONGLY indicate internet is needed
    INTERNET_TRIGGERS = [
        # Explicit search intent
        (r"\b(search|google|look up|find out|what is the latest)\b", 0.95),
        # Current/live information
        (r"\b(current|latest|today'?s?|right now|live|real.?time)\b.*(news|price|score|weather|update|version|status)", 0.90),
        # Temporal markers for recent events
        (r"\b(who won|who is winning|what happened|breaking news)\b", 0.85),
        # Price/stock queries
        (r"\b(price of|cost of|how much is|stock|bitcoin|crypto|market)\b", 0.90),
        # Weather
        (r"\b(weather|temperature|forecast|rain|humidity)\b.*(today|tomorrow|this week|in \w+)", 0.90),
        # Version/release queries
        (r"\b(latest version|newest|just released|update.*available)\b", 0.85),
        # Specific factual (who/what/when about external entities)
        (r"\b(who is|who are|what company|what country|capital of|population of)\b", 0.70),
        # How-to with specific tools/tech (might need docs)
        (r"\b(how to|how do i|tutorial|documentation for)\b.*(install|setup|configure|use)\b", 0.60),
    ]

    # Patterns that indicate NO internet needed (override triggers)
    LOCAL_INDICATORS = [
        # Personal/system queries
        r"\b(your name|who are you|how are you|what can you do)\b",
        # Task management
        r"\b(add|create|schedule|remind|set|cancel).*(meeting|task|reminder|alarm|timer)\b",
        # Memory/personal
        r"\b(remember|recall|what did i|my favorite|my name)\b",
        # Conversational
        r"\b(tell me a joke|sing|story|poem|hello|hi|good morning|thank)\b",
        # Time (handled by rule engine)
        r"\b(what time|what day|what date|current time)\b",
        # System commands
        r"\b(battery|status|shutdown|restart|volume|brightness)\b",
    ]

    def analyze(self, text: str) -> InternetDecision:
        """
        Analyze user query and decide if internet search is needed.
        Returns InternetDecision with confidence score.
        """
        text_lower = text.lower().strip()

        # Step 1: Check local indicators first (fast exit)
        for pattern in self.LOCAL_INDICATORS:
            if re.search(pattern, text_lower):
                return InternetDecision(
                    needs_internet=False,
                    confidence=0.90,
                    reason="Matches local/personal pattern"
                )

        # Step 2: Check internet triggers
        best_match = None
        best_confidence = 0.0

        for pattern, confidence in self.INTERNET_TRIGGERS:
            if re.search(pattern, text_lower):
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = pattern

        if best_match and best_confidence >= 0.70:
            # Generate optimized search query
            search_query = self._extract_search_query(text_lower)
            return InternetDecision(
                needs_internet=True,
                confidence=best_confidence,
                reason=f"Matched internet pattern (confidence: {best_confidence:.0%})",
                search_query=search_query
            )

        # Step 3: Heuristic — questions with "?" that are factual
        if "?" in text and self._is_factual_question(text_lower):
            return InternetDecision(
                needs_internet=True,
                confidence=0.55,
                reason="Factual question detected (low confidence)",
                search_query=self._extract_search_query(text_lower)
            )

        # Default: No internet needed
        return InternetDecision(
            needs_internet=False,
            confidence=0.70,
            reason="No internet triggers matched"
        )

    def _is_factual_question(self, text: str) -> bool:
        """Heuristic: Does this look like a factual/knowledge question?"""
        factual_starters = [
            "what is", "what are", "who is", "who are",
            "where is", "when did", "when was", "how many",
            "how much", "which", "why did", "why is"
        ]
        return any(text.startswith(s) or f" {s} " in text for s in factual_starters)

    def _extract_search_query(self, text: str) -> str:
        """
        Convert user's natural language into an optimized search query.
        Removes conversational fluff, keeps the core question.
        """
        # Remove common prefixes
        removals = [
            r"^(hey |hi |hello |orion |please |can you |could you |would you )",
            r"^(search for |look up |google |find out |tell me )",
            r"^(what is the |what are the |who is the |where is the )",
        ]
        query = text
        for pattern in removals:
            query = re.sub(pattern, "", query, flags=re.IGNORECASE)

        # Remove trailing punctuation and filler
        query = re.sub(r"[?.!]+$", "", query).strip()
        query = re.sub(r"\b(please|thanks|thank you|sir|madam)\b", "", query).strip()

        # Collapse whitespace
        query = re.sub(r"\s+", " ", query).strip()

        # Fallback: if too short after cleaning, use original
        if len(query) < 5:
            query = text.rstrip("?.! ")

        return query[:100]  # Cap at 100 chars for search engines
