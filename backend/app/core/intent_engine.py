import re
import random
import datetime
from typing import Dict, Any, List, Optional
from ..services.gemini_service import GeminiService
from ..services.ollama_service import OllamaService
from ..services.memory_service import MemoryService
from ..services.browser_service import BrowserService
from ..services.vision_service import VisionService
from ..core.security_models import PermissionMatrix

class IntentEngine:
    def __init__(self, 
                 gemini_service: GeminiService,
                 ollama_service: OllamaService,
                 memory_service: MemoryService,
                 browser_service: BrowserService,
                 vision_service: VisionService = None):
        self.gemini = gemini_service
        self.ollama = ollama_service
        self.memory = memory_service
        self.browser = browser_service
        self.vision = vision_service
        
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

    async def process(self, user_id: str, text: str, stream_callback=None, image_b64: Optional[str] = None) -> str:
        """
        Process user input and return response.
        If stream_callback is provided, it will yield fillers and then chunks.
        """
        text_lower = text.lower().strip()
        
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
            enhanced_context = f"{persona_prompt}{time_context}\n{facts_context}\n{vision_context}"
            
            # Try Ollama (Primary)
            try:
                ollama_prompt = f"System: You are ORION. {enhanced_context}\nUser: {q}"
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
                    return full_resp.strip()
            except Exception:
                fallback_needed = True
            
            # Fallback to Gemini if Ollama has doubts or fails
            if fallback_needed:
                full_resp = "" # Reset response
                if stream_cb: stream_cb("\n[System: Checking cloud for updated info...]\n")
                
                full_q = f"You are ORION, a friendly and lifelike AI system. {enhanced_context}\nYou are talking to {uid}. {q}"
                for chunk in self.gemini.get_response_stream(uid, full_q):
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
