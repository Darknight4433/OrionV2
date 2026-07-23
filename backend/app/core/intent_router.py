"""
Intent Router V2 — ORION Event-Driven Architecture
====================================================
Complete rewrite of the intent engine with:
  • Clear separation: Rule Engine vs AI vs Internet
  • Async streaming throughout
  • Internet detection BEFORE AI processing
  • Context building with memory, schedule, and user profile
  • Immediate acknowledgment (never wait before speaking)

Flow:
  1. User speaks → Text arrives
  2. Immediate ACK sent to client (filler)
  3. Intent classification (rule engine check)
  4. If rule match → execute immediately, stream result
  5. If no rule match → check internet need
  6. If internet needed → search → inject context → AI
  7. If no internet → build context → AI (local or cloud based on complexity)
  8. Stream response tokens as they arrive
"""

import re
import random
import datetime
from typing import AsyncGenerator, Optional, Dict, Callable, Tuple
from dataclasses import dataclass
from enum import Enum

from .ai_manager import AIManager, QueryComplexity, AIProvider
from .internet_detector import InternetDetector, InternetDecision
from ..services.memory_service import MemoryService
from ..services.browser_service import BrowserService
from .security_models import PermissionMatrix
from .logging import get_logger

logger = get_logger()


class IntentType(str, Enum):
    RULE_ENGINE = "rule_engine"
    LOCAL_AI = "local_ai"
    CLOUD_AI = "cloud_ai"
    INTERNET_SEARCH = "internet_search"


@dataclass
class IntentResult:
    """Result of intent classification."""
    intent_type: IntentType
    command_name: Optional[str] = None
    extracted_data: Optional[Dict] = None
    complexity: QueryComplexity = QueryComplexity.MODERATE


class IntentRouter:
    """
    The Brain of ORION. Routes user input to the correct handler.
    
    Architecture:
      ┌─────────────┐
      │  User Input  │
      └──────┬──────┘
             │
      ┌──────▼──────┐
      │  Rule Engine │──→ Immediate response (meetings, tasks, time, status)
      └──────┬──────┘
             │ (no match)
      ┌──────▼──────────┐
      │Internet Detector │──→ Search → Context injection → AI
      └──────┬──────────┘
             │ (no internet needed)
      ┌──────▼──────┐
      │  AI Manager  │──→ Local (simple) or Cloud (complex)
      └─────────────┘
    """

    def __init__(
        self,
        ai_manager: AIManager,
        memory_service: MemoryService,
        browser_service: BrowserService
    ):
        self.ai = ai_manager
        self.memory = memory_service
        self.browser = browser_service
        self.internet_detector = InternetDetector()

        # Personality state
        self.current_persona = "default"
        self.current_mood = "Neutral"

        # Immediate acknowledgments (spoken while processing)
        self.ack_phrases = [
            "Certainly.",
            "Let me check that.",
            "One moment please.",
            "On it.",
            "Working on that.",
            "Let me look into that.",
            "Give me a second.",
            "Processing.",
        ]

        # Rule Engine: Regex → Handler mapping
        # Each entry: (pattern, handler_func, command_name, complexity)
        self.rules = [
            # Time & Date
            (r"\b(what time|time check|current time)\b", self._rule_time, "get_time", QueryComplexity.SIMPLE),
            (r"\b(what day|what date|today'?s? date)\b", self._rule_date, "get_time", QueryComplexity.SIMPLE),
            
            # Task Management
            (r"(?:add|create|schedule)\s+(?:a\s+)?meeting\s+(.+)", self._rule_add_meeting, "add_task", QueryComplexity.SIMPLE),
            (r"(?:add|create)\s+(?:a\s+)?task\s+(.+)", self._rule_add_task, "add_task", QueryComplexity.SIMPLE),
            (r"(?:remind me|set reminder)\s+(?:to\s+)?(.+)", self._rule_add_reminder, "add_task", QueryComplexity.SIMPLE),
            
            # System Status
            (r"\b(battery|battery level|power status)\b", self._rule_battery, "get_status", QueryComplexity.SIMPLE),
            (r"\b(system status|robot status|health check)\b", self._rule_system_status, "get_status", QueryComplexity.SIMPLE),
            
            # Explicit search
            (r"(?:search|google|look up)\s+(?:for\s+)?(.+)", self._rule_search, "google_search", QueryComplexity.INTERNET),
        ]

    # ──────────────────────────────────────────
    # PUBLIC API — Main Entry Point
    # ──────────────────────────────────────────

    async def process_stream(
        self, user_id: str, text: str
    ) -> AsyncGenerator[str, None]:
        """
        Process user input and stream response tokens.
        
        This is the main entry point. It:
          1. Classifies intent
          2. Sends immediate ACK for AI queries
          3. Streams the response
          
        Yields:
          Individual text chunks suitable for SSE delivery.
        """
        text_stripped = text.strip()
        text_lower = text_stripped.lower()

        # ── Step 1: Rule Engine Check ──
        rule_result = self._match_rule(text_lower, text_stripped)
        if rule_result:
            pattern, handler, cmd_name, complexity = rule_result
            
            # Security check
            auth = PermissionMatrix.check_permissions(cmd_name, {"query": text})
            if not auth["allowed"]:
                yield f"Security blocked: {auth['reason']}"
                return
            if auth["needs_approval"]:
                yield f"This requires your approval. Should I proceed with: {cmd_name}?"
                return

            # Execute rule handler
            match = re.search(pattern, text_lower) or re.search(pattern, text_stripped, re.IGNORECASE)
            result = await handler(user_id, match, text_stripped)
            yield result
            return

        # ── Step 2: Internet Detection ──
        internet_decision = self.internet_detector.analyze(text_stripped)
        
        if internet_decision.needs_internet and internet_decision.confidence >= 0.70:
            # Acknowledge immediately
            yield self._get_ack("searching")
            yield "\n"

            # Perform search
            search_context = await self._perform_search(internet_decision.search_query or text_stripped)
            
            # Build enhanced prompt with search results
            system_context = self._build_system_context(user_id, internet_context=search_context)
            prompt = f"Based on the following search results, answer the user's question.\n\nSearch Results:\n{search_context}\n\nUser Question: {text_stripped}"

            async for chunk in self.ai.generate(
                user_id, prompt,
                complexity=QueryComplexity.COMPLEX,
                system_context=system_context
            ):
                yield chunk

            # Save to memory
            self.memory.add_conversation(user_id, text_stripped, "[Internet-assisted response]", permanent=False)
            return

        # ── Step 3: AI Processing (No Internet Needed) ──
        # Determine complexity
        complexity = self._assess_complexity(text_stripped)

        # Acknowledge for complex queries (gives user instant feedback)
        if complexity in (QueryComplexity.COMPLEX, QueryComplexity.MODERATE):
            yield self._get_ack("thinking")
            yield "\n"

        # Build context
        system_context = self._build_system_context(user_id)
        prompt = self._build_user_prompt(user_id, text_stripped)

        # Stream AI response
        full_response = ""
        async for chunk in self.ai.generate(
            user_id, prompt,
            complexity=complexity,
            system_context=system_context
        ):
            clean = self._clean_response(chunk)
            if clean:
                full_response += clean
                yield clean

        # Save to memory (summarized)
        if full_response:
            self.memory.add_conversation(user_id, text_stripped, full_response[:500], permanent=False)

    # ──────────────────────────────────────────
    # RULE ENGINE HANDLERS
    # ──────────────────────────────────────────

    async def _rule_time(self, user_id: str, match, original: str) -> str:
        now = datetime.datetime.now()
        return f"It is currently {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d')}."

    async def _rule_date(self, user_id: str, match, original: str) -> str:
        now = datetime.datetime.now()
        return f"Today is {now.strftime('%A, %B %d, %Y')}."

    async def _rule_add_meeting(self, user_id: str, match, original: str) -> str:
        details = match.group(1) if match else original
        self.memory.add_task(f"Meeting: {details}", user_id=user_id)
        return f"Done. Meeting scheduled: {details}"

    async def _rule_add_task(self, user_id: str, match, original: str) -> str:
        details = match.group(1) if match else original
        self.memory.add_task(details, user_id=user_id)
        return f"Task added: {details}"

    async def _rule_add_reminder(self, user_id: str, match, original: str) -> str:
        details = match.group(1) if match else original
        self.memory.add_task(f"Reminder: {details}", user_id=user_id)
        return f"I'll remind you: {details}"

    async def _rule_battery(self, user_id: str, match, original: str) -> str:
        # Placeholder — will integrate with actual robot hardware
        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery:
                pct = battery.percent
                plugged = "charging" if battery.power_plugged else "on battery"
                return f"Battery is at {pct}%, {plugged}."
        except Exception:
            pass
        return "Battery status unavailable on this system."

    async def _rule_system_status(self, user_id: str, match, original: str) -> str:
        import psutil
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        return f"System status: CPU at {cpu}%, RAM at {ram}%. All systems operational."

    async def _rule_search(self, user_id: str, match, original: str) -> str:
        query = match.group(1) if match else original
        
        # Security check
        auth = PermissionMatrix.check_permissions("google_search", {"query": query})
        if not auth["allowed"]:
            return f"Search blocked: {auth['reason']}"

        results = await self.browser.perform_google_search(query)
        if not results:
            return f"I searched for '{query}' but couldn't find relevant results."
        
        return "Here's what I found:\n" + "\n".join(f"• {r}" for r in results[:5])

    # ──────────────────────────────────────────
    # CONTEXT BUILDING
    # ──────────────────────────────────────────

    def _build_system_context(self, user_id: str, internet_context: str = "") -> str:
        """Build the system prompt with all available context."""
        now = datetime.datetime.now()
        
        # Base identity
        parts = [
            "You are ORION, a friendly and intelligent AI assistant system.",
            f"Current time: {now.strftime('%I:%M %p')}, Date: {now.strftime('%A, %B %d, %Y')}.",
            f"You are speaking with: {user_id}.",
            f"User's current mood: {self.current_mood}.",
        ]

        # Persona
        if self.current_persona != "default":
            parts.append(f"Adopt the personality of: {self.current_persona}. Use their tone and vocabulary.")

        # User facts from memory
        facts = self.memory.get_user_facts(user_id)
        if facts:
            facts_str = ", ".join(f"{k}: {v}" for k, v in facts.items())
            parts.append(f"Known facts about this user: {facts_str}")

        # Recent conversation context
        history = self.memory.get_recent_history(user_id, limit=5)
        if history:
            history_str = "\n".join(f"User: {h[0][:80]}\nYou: {h[1][:80]}" for h in history[-3:])
            parts.append(f"Recent conversation:\n{history_str}")

        # Internet context
        if internet_context:
            parts.append(f"Search results available:\n{internet_context[:2000]}")

        # Response guidelines
        parts.append(
            "Guidelines: Be concise but warm. Never start with 'AI:' or 'ORION:'. "
            "Speak naturally as if in conversation. Keep responses under 3 sentences for simple queries."
        )

        return "\n".join(parts)

    def _build_user_prompt(self, user_id: str, text: str) -> str:
        """Construct the final prompt sent to AI."""
        return text  # Context is in system_context; keep user prompt clean

    # ──────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────

    def _match_rule(self, text_lower: str, text_original: str) -> Optional[Tuple]:
        """Check if input matches any rule engine pattern."""
        for pattern, handler, cmd_name, complexity in self.rules:
            if re.search(pattern, text_lower):
                return (pattern, handler, cmd_name, complexity)
        return None

    def _assess_complexity(self, text: str) -> QueryComplexity:
        """Heuristic complexity assessment for AI routing."""
        text_lower = text.lower()
        word_count = len(text.split())

        # Simple: short greetings, yes/no, single-word
        if word_count <= 4:
            return QueryComplexity.SIMPLE

        # Complex indicators
        complex_patterns = [
            r"\b(explain|analyze|compare|summarize|write|compose|create a|design)\b",
            r"\b(why|how does|what if|pros and cons|difference between)\b",
            r"\b(code|program|algorithm|function|implement)\b",
        ]
        for pattern in complex_patterns:
            if re.search(pattern, text_lower):
                return QueryComplexity.COMPLEX

        # Default: moderate
        return QueryComplexity.MODERATE

    async def _perform_search(self, query: str) -> str:
        """Execute internet search and return formatted results."""
        try:
            results = await self.browser.perform_google_search(query)
            if results:
                return "\n".join(results[:5])
            return "No search results found."
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return "Search unavailable."

    def _get_ack(self, context: str = "general") -> str:
        """Get an immediate acknowledgment phrase."""
        if context == "searching":
            options = [
                "Let me search for that.",
                "Searching the internet...",
                "Looking that up for you.",
                "One moment, searching...",
            ]
        elif context == "thinking":
            options = self.ack_phrases
        else:
            options = self.ack_phrases
        return random.choice(options)

    def _clean_response(self, text: str) -> str:
        """Remove AI prefixes and artifacts."""
        if not text:
            return ""
        cleaned = re.sub(r'(?i)^(AI|ORION|OMNIS|SYSTEM|Assistant):\s*', '', text)
        cleaned = re.sub(r'(?i)\n(AI|ORION|OMNIS|SYSTEM|Assistant):\s*', '\n', cleaned)
        return cleaned
