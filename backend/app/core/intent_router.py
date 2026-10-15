"""
Intent Router V2 — ORION Event-Driven Architecture
====================================================
Unified intent classification, decision routing, and vision execution.
Complies with Specification Sections 1, 2, 3, 4, 8, 14, 15, 18, 19, 23:
  • Clear separation: Rule Engine vs Vision VLM vs OCR vs Realtime vs Local Ollama
  • Complete utterance classification (never triggers camera on fragments or 'what is AI')
  • Dedicated VISION_QUERY intent -> OpenCV single frame -> HF VLM -> Gemini fallback
  • Dedicated OCR_QUERY intent -> OpenCV -> OCR extraction -> Ollama summarization -> TTS
  • Dedicated REALTIME intent -> Gemini internet-capable search & generation
  • Dedicated LOCAL_AI intent -> Ollama primary local intelligence -> Gemini fallback
  • User-level isolation with user_id on every interaction
"""

import re
import random
import datetime
import asyncio
from typing import AsyncGenerator, Optional, Dict, Callable, Tuple
from dataclasses import dataclass
from enum import Enum

from app.core.config import settings
from app.core.ai_manager import AIManager, QueryComplexity, AIProvider
from app.core.internet_detector import InternetDetector, InternetDecision
from app.core.security_models import PermissionMatrix
from app.core.logging import get_logger
from app.services.memory_service import MemoryService
from app.services.browser_service import BrowserService
from app.services.vision_manager import VisionManager
from app.services.ocr_service import OCRService

logger = get_logger()


class IntentType(str, Enum):
    RULE_ENGINE     = "rule_engine"
    VISION_QUERY    = "vision_query"
    OCR_QUERY       = "ocr_query"
    REALTIME        = "realtime"
    LOCAL_AI        = "local_ai"


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
      │  User Input │
      └──────┬──────┘
             │
      ┌──────▼──────────────┐
      │ Intent Classifier   │
      └──────┬──────────────┘
             │
             ├── RULE ENGINE  ──→ Time, date, tasks, meetings, system status
             ├── VISION QUERY ──→ Single-frame OpenCV → HF VLM (Qwen) → Gemini fallback
             ├── OCR QUERY    ──→ Single-frame OpenCV → OCR extraction → Ollama
             ├── REALTIME     ──→ Internet-capable provider (Gemini)
             └── LOCAL AI     ──→ Primary Ollama → Gemini fallback
    """

    def __init__(
        self,
        ai_manager: AIManager,
        memory_service: MemoryService,
        browser_service: BrowserService,
        vision_manager: Optional[VisionManager] = None,
        ocr_service: Optional[OCRService] = None
    ):
        self.ai = ai_manager
        self.memory = memory_service
        self.browser = browser_service
        self.vision_manager = vision_manager or VisionManager()
        self.ocr_service = ocr_service or OCRService()
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
        self.rules = [
            # Time & Date (expanded for natural phrasing)
            (r"\b(what time|tell me the time|time check|current time|the time)\b", self._rule_time, "get_time", QueryComplexity.SIMPLE),
            (r"\b(what day|what date|today'?s? date|what is today)\b", self._rule_date, "get_time", QueryComplexity.SIMPLE),
            
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
    # INTENT CLASSIFICATION (Specification Sections 3, 4, 14)
    # ──────────────────────────────────────────

    def classify_intent(self, text_stripped: str) -> IntentType:
        """
        Classifies the COMPLETE utterance into an authoritative intent.
        Strictly prevents camera activation on queries like 'what is AI?'.
        """
        text_lower = text_stripped.lower().strip()

        # 1. Deterministic Rule Engine match
        if self._match_rule(text_lower, text_stripped) is not None:
            return IntentType.RULE_ENGINE

        # 2. OCR Query (Section 14: separate subsystem)
        ocr_patterns = [
            r"\bread this\b",
            r"\bwhat does this say\b",
            r"\bread what is written\b",
            r"\bread the text\b",
            r"\bread this document\b",
            r"\bread this page\b"
        ]
        if any(re.search(p, text_lower) for p in ocr_patterns):
            return IntentType.OCR_QUERY

        # 3. Vision Query (Section 4: Dedicated intent, strict complete-utterance matching)
        # MUST NOT match "what is AI?" or general questions containing "this"
        vision_explicit_patterns = [
            r"\bwhat (?:is|are) (?:this|that|these|those)(?:\s+(?:object|item|thing))?\b",
            r"\bwhat am i holding\b",
            r"\bidentify (?:this|that|the object|the item)\b",
            r"\bwhat (?:object|item) is this\b",
            r"\bwhat is in my hand\b",
            r"\bhow many objects (?:are there|do you see)\b",
            r"\bwhat do you see\b",
            r"\blook at (?:this|that)\b",
            r"\btell me what (?:this|that) is\b",
            r"\bdescribe what you see\b",
        ]
        if any(re.search(p, text_lower) for p in vision_explicit_patterns):
            return IntentType.VISION_QUERY

        # 4. Realtime / Dynamic Query (Section 3: Internet-capable service / Gemini)
        realtime_patterns = [
            r"\b(who is the current|latest news|what happened today|today's news|breaking news)\b",
            r"\b(current weather|weather today|weather tomorrow|current temperature)\b",
            r"\b(stock price|market today|election results|who won|who is winning)\b",
            r"\b(search for|google for|look up on the internet)\b"
        ]
        if any(re.search(p, text_lower) for p in realtime_patterns):
            return IntentType.REALTIME

        # General definitions, concepts, and reasoning are explicitly local (Section 2)
        if re.search(r"\b(what is (?:ai|a |an |the |quantum|python|machine learning|gravity|dna|photosynthesis))\b", text_lower) or text_lower.startswith("explain "):
            return IntentType.LOCAL_AI

        dec = self.internet_detector.analyze(text_stripped)
        if dec.needs_internet and dec.confidence >= 0.85:
            return IntentType.REALTIME

        # 5. Default General Knowledge / Reasoning -> Local Ollama (Section 2)
        return IntentType.LOCAL_AI

    # ──────────────────────────────────────────
    # MAIN PROCESSING PIPELINE
    # ──────────────────────────────────────────

    async def process_stream(
        self,
        user_id: str,
        text: str,
        direct_frame = None,
        image_bytes: Optional[bytes] = None
    ) -> AsyncGenerator[str, None]:
        """
        Process user input and stream response chunks.
        """
        text_stripped = text.strip()
        text_lower = text_stripped.lower()

        intent = self.classify_intent(text_stripped)
        logger.info(f"[ROUTER] User '{user_id}' query: '{text_stripped}' -> Intent: {intent.value}")

        # ── 1. RULE ENGINE ──
        if intent == IntentType.RULE_ENGINE:
            rule_result = self._match_rule(text_lower, text_stripped)
            if rule_result:
                pattern, handler, cmd_name, complexity = rule_result
                auth = PermissionMatrix.check_permissions(cmd_name, {"query": text})
                if not auth["allowed"]:
                    yield f"Security blocked: {auth['reason']}"
                    return
                if auth["needs_approval"]:
                    yield f"This requires your approval. Should I proceed with: {cmd_name}?"
                    return

                match = re.search(pattern, text_lower) or re.search(pattern, text_stripped, re.IGNORECASE)
                result = await handler(user_id, match, text_stripped)
                yield result
                return

        # ── 2. VISION QUERY (Specification Section 8) ──
        if intent == IntentType.VISION_QUERY:
            # Immediate voice prompt instructing user
            yield "Sir, please hold the object clearly in front of the camera and keep it steady."
            yield "\n"
            await asyncio.sleep(getattr(settings, "VISION_CAPTURE_DELAY", 1.5))

            # Run visual reasoning
            result = await self.vision_manager.process_visual_query(
                user_id=user_id,
                question=text_stripped,
                image_bytes=image_bytes,
                direct_frame=direct_frame
            )

            yield result.text_response

            # Save interaction text to memory (no raw image stored)
            self.memory.add_conversation(
                user_id,
                text_stripped,
                result.text_response,
                permanent=False
            )
            return

        # ── 3. OCR QUERY (Specification Section 14) ──
        if intent == IntentType.OCR_QUERY:
            yield "Sir, please hold the text steady in front of the camera."
            yield "\n"
            await asyncio.sleep(1.0)

            # Capture frame if not provided
            frame = direct_frame
            if frame is None and image_bytes is None:
                loop = asyncio.get_event_loop()
                frame, val = await loop.run_in_executor(None, self.vision_manager.camera.capture_frame)

            if frame is not None:
                success, extracted_text = await self.ocr_service.extract_text(frame)
                if success and extracted_text:
                    # Summarize/interpret via Ollama if long
                    if len(extracted_text) > 120:
                        prompt = f"The following text was read from an image. Summarize it concisely in 1-2 spoken sentences: '{extracted_text}'"
                        system_context = self._build_system_context(user_id)
                        async for chunk in self.ai.generate(user_id, prompt, complexity=QueryComplexity.SIMPLE, system_context=system_context):
                            yield chunk
                    else:
                        yield f"Sir, it reads: '{extracted_text}'"
                else:
                    yield "Sir, I couldn't detect legible text from the camera. Please ensure good lighting and hold it steady."
            else:
                yield "Sir, camera capture was unavailable for reading."
            return

        # ── 4. REALTIME / DYNAMIC QUERY (Specification Section 3) ──
        if intent == IntentType.REALTIME:
            yield self._get_ack("searching")
            yield "\n"

            internet_decision = self.internet_detector.analyze(text_stripped)
            search_query = internet_decision.search_query or text_stripped
            search_context = await self._perform_search(search_query)

            system_context = self._build_system_context(user_id, internet_context=search_context)
            prompt = (
                f"Based on current real-time data, answer concisely in 1-2 sentences.\n"
                f"Search Context: {search_context}\n"
                f"User Question: {text_stripped}"
            )

            # Uses internet-capable provider (Gemini primary)
            full_response = ""
            async for chunk in self.ai.generate(
                user_id, prompt,
                complexity=QueryComplexity.INTERNET,
                system_context=system_context
            ):
                clean = self._clean_response(chunk)
                if clean:
                    full_response += clean
                    yield clean

            if full_response:
                self.memory.add_conversation(user_id, text_stripped, full_response[:500], permanent=False)
            return

        # ── 5. LOCAL AI / GENERAL TEXT QUERY (Specification Section 2) ──
        complexity = self._assess_complexity(text_stripped)
        if complexity in (QueryComplexity.COMPLEX, QueryComplexity.MODERATE):
            yield self._get_ack("thinking")
            yield "\n"

        system_context = self._build_system_context(user_id)
        prompt = self._build_user_prompt(user_id, text_stripped)

        # Uses Ollama primary local intelligence, with Gemini fallback
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

        if full_response:
            self.memory.add_conversation(user_id, text_stripped, full_response[:500], permanent=False)

    # ──────────────────────────────────────────
    # RULE ENGINE HANDLERS
    # ──────────────────────────────────────────

    async def _rule_time(self, user_id: str, match, original: str) -> str:
        now = datetime.datetime.now()
        return f"Sir, it is currently {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d')}."

    async def _rule_date(self, user_id: str, match, original: str) -> str:
        now = datetime.datetime.now()
        return f"Sir, today is {now.strftime('%A, %B %d, %Y')}."

    async def _rule_add_meeting(self, user_id: str, match, original: str) -> str:
        details = match.group(1) if match else original
        self.memory.add_task(f"Meeting: {details}", user_id=user_id)
        return f"Sir, your meeting is scheduled: {details}"

    async def _rule_add_task(self, user_id: str, match, original: str) -> str:
        details = match.group(1) if match else original
        self.memory.add_task(details, user_id=user_id)
        return f"Sir, task added: {details}"

    async def _rule_add_reminder(self, user_id: str, match, original: str) -> str:
        details = match.group(1) if match else original
        self.memory.add_task(f"Reminder: {details}", user_id=user_id)
        return f"Sir, I will remind you: {details}"

    async def _rule_battery(self, user_id: str, match, original: str) -> str:
        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery:
                pct = battery.percent
                plugged = "charging" if battery.power_plugged else "on battery"
                return f"Sir, battery is at {pct}%, {plugged}."
        except Exception:
            pass
        return "Sir, battery status is unavailable on this hardware."

    async def _rule_system_status(self, user_id: str, match, original: str) -> str:
        import psutil
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        return f"Sir, system status is operational. CPU usage is {cpu}%, and memory usage is {ram}%."

    async def _rule_search(self, user_id: str, match, original: str) -> str:
        query = match.group(1) if match else original
        auth = PermissionMatrix.check_permissions("google_search", {"query": query})
        if not auth["allowed"]:
            return f"Search blocked: {auth['reason']}"

        results = await self.browser.perform_google_search(query)
        if not results:
            return f"Sir, I searched for '{query}' but couldn't find relevant results."
        return "Sir, here is what I found:\n" + "\n".join(f"• {r}" for r in results[:4])

    # ──────────────────────────────────────────
    # CONTEXT BUILDING
    # ──────────────────────────────────────────

    def _build_system_context(self, user_id: str, internet_context: str = "") -> str:
        now = datetime.datetime.now()
        parts = [
            f"You are ORION, a professional voice executive assistant. Time: {now.strftime('%I:%M %p, %A %B %d %Y')}. User: {user_id}.",
            "Rules: Answer in 1-2 concise sentences. Be calm, polite, and address the user as Sir when appropriate. Never simulate back-and-forth dialogue or write roleplay markers.",
        ]
        facts = self.memory.get_user_facts(user_id)
        if facts:
            parts.append("User facts: " + ", ".join(f"{k}:{v}" for k, v in list(facts.items())[:3]))
        if internet_context:
            parts.append(f"Context: {internet_context[:400]}")
        return " ".join(parts)

    def _build_user_prompt(self, user_id: str, text: str) -> str:
        return text

    # ──────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────

    def _match_rule(self, text_lower: str, text_original: str) -> Optional[Tuple]:
        for pattern, handler, cmd_name, complexity in self.rules:
            if re.search(pattern, text_lower):
                return (pattern, handler, cmd_name, complexity)
        return None

    def _assess_complexity(self, text: str) -> QueryComplexity:
        text_lower = text.lower()
        word_count = len(text.split())
        if word_count <= 4:
            return QueryComplexity.SIMPLE

        complex_patterns = [
            r"\b(explain|analyze|compare|summarize|write|compose|create a|design)\b",
            r"\b(why|how does|what if|pros and cons|difference between)\b",
            r"\b(code|program|algorithm|function|implement)\b",
        ]
        for pattern in complex_patterns:
            if re.search(pattern, text_lower):
                return QueryComplexity.COMPLEX

        return QueryComplexity.MODERATE

    async def _perform_search(self, query: str) -> str:
        try:
            results = await self.browser.perform_google_search(query)
            if results:
                return "\n".join(results[:4])
            return "No search results found."
        except Exception as e:
            logger.error(f"[SEARCH ERR] {e}")
            return "Search unavailable."

    def _get_ack(self, context: str = "general") -> str:
        if context == "searching":
            options = [
                "Let me look into that.",
                "Checking current records...",
                "One moment please.",
            ]
        elif context == "thinking":
            options = self.ack_phrases
        else:
            options = self.ack_phrases
        return random.choice(options)

    def _clean_response(self, text: str) -> str:
        if not text:
            return ""
        cleaned = re.sub(r'(?i)^(AI|ORION|OMNIS|SYSTEM|Assistant):\s*', '', text)
        cleaned = re.sub(r'(?i)\n(AI|ORION|OMNIS|SYSTEM|Assistant):\s*', '\n', cleaned)
        return cleaned
