import re
import random
import datetime
import time
from typing import Dict, Any, List, Optional
from ..services.gemini_service import GeminiService
from ..services.ollama_service import OllamaService
from ..services.memory_service import MemoryService
from ..services.browser_service import BrowserService
from ..services.vision_service import VisionService
from ..services.habit_service import HabitDetector
from ..services.habit_suggester import HabitSuggester
from ..services.briefing_engine import BriefingEngine
from ..core.security_models import PermissionMatrix

class IntentEngine:
    def __init__(self, 
                 gemini_service: GeminiService,
                 ollama_service: OllamaService,
                 memory_service: MemoryService,
                 browser_service: BrowserService,
                 vision_service: VisionService = None,
                 habit_detector: HabitDetector = None,
                 habit_suggester: HabitSuggester = None,
                 briefing_engine: BriefingEngine = None):
        self.gemini = gemini_service
        self.ollama = ollama_service
        self.memory = memory_service
        self.browser = browser_service
        self.vision = vision_service
        self.habit_detector = habit_detector
        self.habit_suggester = habit_suggester
        self.briefing_engine = briefing_engine
        
        # OMNIS_5 Fillers (professional)
        self.fillers = [
            "One moment, Sir...",
            "Checking my records...",
            "That's noted. One moment...",
            "Let me verify that...",
            "I'm on it, Sir...",
            "Processing your request...",
            "One moment, I am searching for an answer.",
            "Let me check the information...",
            "Analyzing the details..."
        ]
        
        # Personality / Mood State
        self.current_persona = "default"
        self.current_mood = "Neutral"
        
        # Regex mappings for deterministic actions
        self.commands = [
            (r'(?:add|schedule) (?:a )?meeting (.+)', self._handle_add_meeting),
            (r'time check|what time is it', self._handle_time_check),
            (r'search for (.+)', self._handle_web_search),
            (r'(?:create|add) (?:a )?task (.+)', self._handle_add_task),
            (r"what'?s my schedule|what'?s today|show.*schedule|any.*meeting|pending.*task", self._handle_schedule_query),
        ]
        
        # Preference patterns to extract and store
        self.preference_patterns = [
            (r'i (?:prefer|like|love) (.+)', 'preference'),
            (r'my favorite (.+) is (.+)', 'favorite'),
            (r'i (?:don\'t|do not) like (.+)', 'dislike'),
            (r'i hate (.+)', 'dislike'),
            (r'i\'m (.+)', 'identity'),
            (r'i am (.+)', 'identity'),
        ]

    async def process(self, user_id: str, text: str, stream_callback=None, image_b64: Optional[str] = None) -> tuple[str, str]:
        """
        Process user input and return (response, ai_mode).
        ai_mode is 'ollama', 'gemini', or 'none'
        If stream_callback is provided, it will yield fillers and then chunks.
        """
        text_lower = text.lower().strip()
        
        # Check for suggestion followup
        if self.habit_suggester:
            followup = self.habit_suggester.handle_followup(user_id, text)
            if followup:
                return followup, "system"
        
        # 0. Handle Vision Input
        vision_context = ""
        if image_b64 and self.vision and any(w in text_lower for w in ["what do you see", "what am i holding", "look at this", "vision", "tell me what you see"]):
            analysis = self.vision.analyze_image(image_b64)
            vision_context = f"\n[System Audio-Visual Input Frame: {analysis}]\n"
        
        # 1. Deterministic Command Matching
        for pattern, handler in self.commands:
            match = re.search(pattern, text_lower) # search is more flexible than match
            if match:
                # Security Check
                tool_name = handler.__name__.replace("_handle_", "")
                auth = PermissionMatrix.check_permissions(tool_name, {"query": text})
                
                if not auth["allowed"]:
                    return f"SECURITY ALERT: {auth['reason']}", "system"
                
                if auth["needs_approval"]:
                    return f"CONFIRMATION REQUIRED: This is a high-risk action ({tool_name}). Should I proceed?", "system"
                
                result = await handler(user_id, match)
                return result, "system"

        # 2. Extract and store user preferences from input
        self._extract_preferences(user_id, text)

        # 3. Memory categorization (rule + AI classifier)
        memory_category = await self._process_memory(user_id, text)
        logger.debug(f"[MEMORY] Category: {memory_category} for '{text[:40]}'")

        # 3b. Habit detection (behavior tracking)
        if self.habit_detector:
            self._maybe_observe_habit(user_id, text_lower)

        # 4. LLM Processing with Fallback and OMNIS_5 prompt logic
        async def run_llm(uid, q, stream_cb):
            fallback_needed = False
            full_resp = ""
            ai_mode = "ollama"  # Default to Ollama
            
            # --- CONTEXT BUILDING (OMNIS_5 Logic) ---
            now = datetime.datetime.now()
            time_str = now.strftime("%I:%M %p")
            day_str = now.strftime("%A, %B %d, %Y")
            
            persona_prompt = f" Current Personality/Role: {self.current_persona}. Adopt this persona's tone, vocabulary, and style." if self.current_persona != "default" else ""
            time_context = f" Current Time: {time_str}. Current Date: {day_str}. User Mood: {self.current_mood}."
            
            facts = self.memory.get_user_facts(uid)
            facts_context = "\nKnown facts about this user:\n" + "\n".join([f"- {k}: {v}" for k, v in facts.items()]) if facts else ""
            
            # Add recent conversation history for context (shortened for latency)
            history = self.memory.get_recent_history(uid, limit=3)
            history_context = ""
            if history:
                history_context = "\nRecent:\n"
                for user_msg, ai_msg in history[-2:]:  # Last 2 exchanges only
                    history_context += f"U: {user_msg[:50]}...\nA: {ai_msg[:50]}...\n"
            
            # Add recent tasks for context (limited)
            tasks = self.memory.get_recent_tasks(uid, limit=2)
            tasks_context = ""
            if tasks:
                tasks_context = "\nTasks:\n" + "\n".join(f"- {task[:30]}..." for task in tasks[:2])
            
            # Contextual awareness: Check for return after inactivity
            last_active = self.memory.get_last_activity(uid)
            current_time = time.time()
            inactivity_hours = (current_time - last_active) / 3600 if last_active else 24
            
            awareness_context = ""
            if inactivity_hours > 2:  # User returning after 2+ hours
                awareness_context = f"\n[Context: User returning after {int(inactivity_hours)} hours of inactivity. Consider a warm welcome.]"
            
            # Build System Prompt additions (concise for low latency)
            enhanced_context = f"{time_context}\n{facts_context}\n{history_context}\n{tasks_context}\n{awareness_context}\n{vision_context}"
            
            # Try Ollama (Primary)
            try:
                ollama_prompt = f"System: You are ORION, a professional AI executive assistant for Sir. {enhanced_context}\n\nINSTRUCTIONS: Be respectful, concise, and helpful. Address as 'Sir'. Focus on school administration, meetings, tasks, and study habits. Provide clear, professional responses. Keep explanations brief. ALWAYS maintain a calm, respectful, and professional tone - never casual, chatty, or playful.\n\nUser: {q}"
                for chunk in self.ollama.get_response_stream(uid, ollama_prompt):
                    if chunk.startswith("SYSTEM ERROR"):
                        fallback_needed = True
                        break
                    
                    clean_chunk = self._clean_response(chunk)
                    if clean_chunk:
                        full_resp += clean_chunk + " "
                
                # Check if Ollama has doubts or the info seems old
                doubt_phrases = ["i'm not sure", "i don't know", "knowledge cutoff", "as an ai", "i cannot verify", "i don't have real-time", "i can't browse", "up to date"]
                resp_lower = full_resp.lower()
                if any(phrase in resp_lower for phrase in doubt_phrases) or not full_resp.strip():
                    fallback_needed = True
                
                if not fallback_needed:
                    if stream_cb: stream_cb(full_resp.strip()) # Output all at once to avoid streaming doubt midway
                    return full_resp.strip(), ai_mode
            except Exception:
                fallback_needed = True
            
            # Fallback to Gemini if Ollama has doubts or fails
            if fallback_needed:
                ai_mode = "gemini"
                full_resp = "" # Reset response
                if stream_cb: stream_cb("\n[System: Checking cloud for updated info...]\n")
                
                full_q = f"You are ORION, a professional AI executive assistant for Sir. {enhanced_context}\n\nINSTRUCTIONS: Be respectful, concise, and helpful. Address as 'Sir'. Focus on school administration, meetings, tasks, and study habits. Provide clear, professional responses. Keep explanations brief. ALWAYS maintain a calm, respectful, and professional tone - never casual, chatty, or playful.\n\nUser: {q}"
                for chunk in self.gemini.get_response_stream(uid, full_q):
                    clean_chunk = self._clean_response(chunk)
                    if clean_chunk:
                        full_resp += clean_chunk + " "
                        if stream_cb: stream_cb(clean_chunk)
                return full_resp.strip(), ai_mode

        try:
            if stream_callback:
                stream_callback(random.choice(self.fillers))
                return await run_llm(user_id, text, stream_callback)
            else:
                return await run_llm(user_id, text, None)
        except Exception as e:
            # 🛡️ PHASE 2: Never stay silent - always respond with fail-safe message
            logger.error(f"Intent Engine critical error: {e}")
            return "I am currently unable to process that request, Sir. Please try again or contact support.", "safe"

    async def _handle_add_meeting(self, user_id, match):
        details = match.group(1)
        self.memory.add_task(f"Meeting: {details}")
        return f"Done. I've scheduled your meeting: {details}"

    async def _handle_add_task(self, user_id, match):
        details = match.group(1)
        self.memory.add_task(details, user_id)
        return f"Task added to your list: {details}"

    async def _handle_schedule_query(self, user_id, match):
        """Handle 'What's my schedule?' or similar queries."""
        if self.briefing_engine:
            return self.briefing_engine.get_context_briefing(user_id)
        return "I cannot retrieve your schedule at this moment."

    async def _process_memory(self, user_id: str, text: str) -> str:
        """3-layer memory process: rule, classifier, storage."""
        text_clean = text.strip().lower()

        # Layer 1: Rule engine
        rule_mapping = self._extract_rule_memory(text_clean)
        if rule_mapping:
            category, value = rule_mapping
            if self._should_store_memory(category, value) and not self.memory.is_duplicate_memory(user_id, category, value):
                self.memory.add_memory_item(user_id, category, value)
                self.memory.trim_memory(user_id, category, max_items=10)
                return category
            return "ignore"

        # Layer 2: AI classifier
        try:
            category = self.ollama.classify_memory_item(text)
        except Exception as e:
            logger.error(f"Memory classification call failed: {e}")
            category = "ignore"

        if category in {"preference", "habit", "fact"}:
            if self._should_store_memory(category, text) and not self.memory.is_duplicate_memory(user_id, category, text):
                self.memory.add_memory_item(user_id, category, text.strip())
                self.memory.trim_memory(user_id, category, max_items=10)
                return category
            return "ignore"

        return "ignore"

    def _should_store_memory(self, category: str, text: str) -> bool:
        """Confidence rules for storing memory."""
        if category == "ignore":
            return False
        if not text or len(text.strip()) < 12:
            return False
        return True

    def _maybe_observe_habit(self, user_id: str, text_lower: str):
        actions = {
            "study": "study",
            "eat": "eat",
            "sleep": "sleep",
            "drink": "drink",
            "code": "code"
        }

        for pattern, action in actions.items():
            if f" {pattern}" in text_lower or text_lower.startswith(pattern):
                self.habit_detector.observe(user_id, action)
                break

    def _extract_rule_memory(self, text: str):
        """Matches explicit patterns for fast memory extraction."""
        if "i like" in text or "i love" in text or "i prefer" in text:
            value = text.replace("i like", "").replace("i love", "").replace("i prefer", "").strip()
            return "preference", value if value else text
        if "my name is" in text:
            name = text.split("my name is", 1)[1].strip()
            return "fact", f"name:{name}" if name else "name:unknown"
        if "i always" in text or "i usually" in text or "i often" in text:
            return "habit", text
        if "i am" in text or "i'm" in text:
            if "i am" in text and len(text.split()) < 10:
                return "fact", text
        return None

    async def _handle_time_check(self, user_id, match):
        now = datetime.datetime.now()
        return f"It is currently {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d')}."

    async def _handle_web_search(self, user_id, match):
        query = match.group(1)
        
        # Security check for browser search
        auth = PermissionMatrix.check_permissions("google_search", {"query": query})
        if not auth["allowed"]:
            return f"Search Blocked: {auth['reason']}"

        results = await self.browser.perform_google_search(query)
        if not results:
            return f"I searched for '{query}' but couldn't find any relevant results."
        
        # Summarize with Gemini
        summary_prompt = f"Summarize these search results for the query '{query}':\n" + "\n".join(results)
        response = ""
        for chunk in self.gemini.get_response_stream(user_id, summary_prompt):
            response += self._clean_response(chunk)
        return response.strip()

    def _extract_preferences(self, user_id: str, text: str):
        """Extract user preferences from conversation and store as facts."""
        text_lower = text.lower()
        for pattern, pref_type in self.preference_patterns:
            match = re.search(pattern, text_lower)
            if match:
                if pref_type == 'preference':
                    value = match.group(1).strip()
                    self.memory.store_fact(user_id, f"prefers_{value.replace(' ', '_')}", "true")
                elif pref_type == 'favorite':
                    category = match.group(1).strip()
                    item = match.group(2).strip()
                    self.memory.store_fact(user_id, f"favorite_{category.replace(' ', '_')}", item)
                elif pref_type == 'dislike':
                    value = match.group(1).strip()
                    self.memory.store_fact(user_id, f"dislikes_{value.replace(' ', '_')}", "true")
                elif pref_type == 'identity':
                    identity = match.group(1).strip()
                    self.memory.store_fact(user_id, "identity", identity)

    def _clean_response(self, text: str) -> str:
        """Normalize AI response text."""
        cleaned = re.sub(r'(?i)^(AI|ORION|OMNIS|SYSTEM):\s*', '', text)
        cleaned = re.sub(r'(?i)\n(AI|ORION|OMNIS|SYSTEM):\s*', '\n', cleaned)
        return cleaned.strip()
