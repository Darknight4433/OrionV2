import re
import random
import datetime
from typing import Dict, Any, List, Optional
from ..services.gemini_service import GeminiService
from ..services.ollama_service import OllamaService
from ..services.memory_service import MemoryService
from ..services.browser_service import BrowserService
from ..core.security_models import PermissionMatrix

class IntentEngine:
    def __init__(self, 
                 gemini_service: GeminiService,
                 ollama_service: OllamaService,
                 memory_service: MemoryService,
                 browser_service: BrowserService):
        self.gemini = gemini_service
        self.ollama = ollama_service
        self.memory = memory_service
        self.browser = browser_service
        
        # OMNIS_5 Fillers
        self.fillers = [
            "Umm, let me think about that...",
            "Checking my records...",
            "That's interesting. One moment...",
            "Let me search my memory banks...",
            "I'm on it. Give me a second...",
            "Processing your request...",
            "One moment, I am searching for an answer.",
            "Let me consult the stars...",
            "Analyzing trajectory..."
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
        ]

    async def process(self, user_id: str, text: str, stream_callback=None) -> str:
        """
        Process user input and return response.
        If stream_callback is provided, it will yield fillers and then chunks.
        """
        text_lower = text.lower().strip()
        
        # 1. Deterministic Command Matching
        for pattern, handler in self.commands:
            match = re.search(pattern, text_lower) # search is more flexible than match
            if match:
                # Security Check
                tool_name = handler.__name__.replace("_handle_", "")
                auth = PermissionMatrix.check_permissions(tool_name, {"query": text})
                
                if not auth["allowed"]:
                    return f"SECURITY ALERT: {auth['reason']}"
                
                if auth["needs_approval"]:
                    return f"CONFIRMATION REQUIRED: This is a high-risk action ({tool_name}). Should I proceed?"
                
                return await handler(user_id, match)

        # 3. LLM Processing with Fallback and OMNIS_5 prompt logic
        async def run_llm(uid, q, stream_cb):
            fallback_needed = False
            full_resp = ""
            
            # --- CONTEXT BUILDING (OMNIS_5 Logic) ---
            now = datetime.datetime.now()
            time_str = now.strftime("%I:%M %p")
            day_str = now.strftime("%A, %B %d, %Y")
            
            persona_prompt = f" Current Personality/Role: {self.current_persona}. Adopt this persona's tone, vocabulary, and style." if self.current_persona != "default" else ""
            time_context = f" Current Time: {time_str}. Current Date: {day_str}. User Mood: {self.current_mood}."
            
            facts = self.memory.get_user_facts(uid)
            facts_context = "\nKnown facts about this user:\n" + "\n".join([f"- {k}: {v}" for k, v in facts.items()]) if facts else ""
            
            # Build System Prompt additions
            enhanced_context = f"{persona_prompt}{time_context}\n{facts_context}\n"
            
            # Try Gemini
            try:
                # Gemini prompt with OMNIS System identity
                full_q = f"You are ORION, a friendly and lifelike AI system. {enhanced_context}\nYou are talking to {uid}. {q}"
                
                for chunk in self.gemini.get_response_stream(uid, full_q):
                    if chunk.startswith("SYSTEM") and ("CRITICAL" in chunk or "No API keys" in chunk or "exhausted" in chunk or "error" in chunk.lower()):
                        fallback_needed = True
                        break
                    
                    # Prefix cleaning
                    clean_chunk = self._clean_response(chunk)
                    if clean_chunk:
                        full_resp += clean_chunk + " "
                        if stream_cb: stream_cb(clean_chunk)
                
                if not fallback_needed and full_resp.strip():
                    return full_resp.strip()
            except Exception:
                fallback_needed = True
            
            # Fallback to Ollama
            if fallback_needed or not full_resp.strip():
                if stream_cb: stream_cb("\n[System: Primary AI exhausted. Switching to Local Ollama fallback...]\n")
                # Use the SAME enhanced prompt for Ollama to maintain personality
                ollama_prompt = f"System: You are ORION. {enhanced_context}\nUser: {q}"
                for chunk in self.ollama.get_response_stream(uid, ollama_prompt):
                    clean_chunk = self._clean_response(chunk)
                    if clean_chunk:
                        full_resp += clean_chunk + " "
                        if stream_cb: stream_cb(clean_chunk)
                return full_resp.strip()

        if stream_callback:
            stream_callback(random.choice(self.fillers))
            return await run_llm(user_id, text, stream_callback)
        else:
            return await run_llm(user_id, text, None)

    async def _handle_add_meeting(self, user_id, match):
        details = match.group(1)
        self.memory.add_task(f"Meeting: {details}")
        return f"Done. I've scheduled your meeting: {details}"

    async def _handle_add_task(self, user_id, match):
        details = match.group(1)
        self.memory.add_task(details)
        return f"Task added to your list: {details}"

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

    def _clean_response(self, text: str) -> str:
        """Forcefully remove AI/ORION/OMNIS prefixes to keep conversation natural."""
        # Clean both start of line and inline prefixes often generated by small models
        cleaned = re.sub(r'(?i)^(AI|ORION|OMNIS|SYSTEM):\s*', '', text)
        cleaned = re.sub(r'(?i)\n(AI|ORION|OMNIS|SYSTEM):\s*', '\n', cleaned)
        return cleaned.strip()
