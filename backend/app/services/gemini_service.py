import os
import re
import datetime
import google.generativeai as genai
from typing import List, Generator, Optional
from ..core.config import settings
from ..core.logging import get_logger
from ..services.memory_service import MemoryService

logger = get_logger()

class GeminiService:
    def __init__(self, memory_service: MemoryService):
        self.memory = memory_service
        self.api_keys = settings.GEMINI_API_KEYS
        self.current_key_index = 0
        self.cached_model = None
        self._configure_initial()

    def _configure_initial(self):
        if self.api_keys:
            self._configure_next_key()
        else:
            print("WARNING: No Gemini API Keys configured.")

    def _configure_next_key(self) -> bool:
        if not self.api_keys: return False
        
        attempts = 0
        while attempts < len(self.api_keys):
            key = self.api_keys[self.current_key_index]
            try:
                genai.configure(api_key=key)
                return True
            except Exception as e:
                print(f"Key #{self.current_key_index} failed: {e}")
            
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            attempts += 1
        return False

    def _rotate_key(self):
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self._configure_next_key()

    def _discover_model(self):
        """Finds the best available model dynamically."""
        if self.cached_model: return self.cached_model
        
        try:
            candidates = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            
            # Priority: 1.5-flash -> 1.5-pro -> 1.0-pro
            found = next((m for m in candidates if 'gemini-1.5-flash' in m), None)
            if not found: found = next((m for m in candidates if 'gemini-1.5-pro' in m), None)
            if not found: found = next((m for m in candidates if 'gemini-pro' in m), None)
            if not found and candidates: found = candidates[0]
            
            self.cached_model = found
            return found
        except Exception as e:
            print(f"Model discovery failed: {e}")
            return 'gemini-1.5-flash'

    def get_response_stream(self, user_id: str, prompt: str) -> Generator[str, None, None]:
        if not self.api_keys:
            yield "SYSTEM: No API keys found. Please add GEMINI_API_KEYS to your .env file."
            return

        # System Prompt logic handled by IntentEngine for better personalization
        system_prompt = prompt


        model_name = self._discover_model()
        max_retries = len(self.api_keys)
        retries = 0
        
        full_response = ""

        while retries < max_retries:
            try:
                # Log rotation attempt
                if retries > 0:
                    yield f"SYSTEM: Key #{self.current_key_index-1} exhausted. Trying rotation Key #{self.current_key_index}..."
                
                logger.info(f"Attempting with Key #{self.current_key_index}")
                genai.configure(api_key=self.api_keys[self.current_key_index])
                
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(system_prompt, stream=True)
                
                output_buffer = ""
                for chunk in response:
                    try:
                        if chunk.text:
                            text = chunk.text
                            full_response += text
                            output_buffer += text
                    except Exception as e:
                        # Safety block or other issue with this chunk
                        logger.warning(f"Chunk error: {e}")
                        continue
                        
                    # Yield sentences for low-latency
                    parts = re.split(r'(?<=[.!?\n]) ', output_buffer)
                    if len(parts) > 1:
                        for p in parts[:-1]:
                            clean_p = p.strip()
                            if clean_p: yield clean_p
                        output_buffer = parts[-1]
                
                if output_buffer.strip():
                    yield output_buffer.strip()
                
                # Save to memory
                self._save_memory(user_id, prompt, full_response)
                return

            except Exception as e:
                err = str(e).lower()
                if any(kw in err for kw in ["quota", "429", "resource", "limit"]):
                    logger.warning(f"Key #{self.current_key_index} exhausted (Quota/Rate).")
                    self._rotate_key()
                    retries += 1
                else:
                    logger.error(f"Gemini Error (Key #{self.current_key_index}): {e}")
                    yield f"SYSTEM: Key #{self.current_key_index} encountered an error: {str(e)[:50]}"
                    self._rotate_key() # Even on other errors, let's try next key
                    retries += 1
        
        yield f"SYSTEM CRITICAL: All {max_retries} Gemini API keys are exhausted. Please add more keys to your .env file or wait for the quota to reset (usually 1 minute for free tier)."

    def _save_memory(self, user_id: str, prompt: str, response: str):
        # 1. Check for explicit permanent memory triggers
        payload_lower = prompt.lower()
        permanent = False
        memory_triggers = ["remember this", "keep in mind", "remember forever", "don't forget this"]
        if any(t in payload_lower for t in memory_triggers):
            permanent = True
            logger.info("🧠 Permanent memory triggered.")

        # 2. Extract Facts (Heuristics)
        if "my favorite" in payload_lower and "is" in payload_lower:
            try:
                parts = payload_lower.split("my favorite")[1].split("is")
                f_key = parts[0].strip()
                f_val = parts[1].strip().rstrip(".!?")
                self.memory.store_fact(user_id, f_key, f_val)
                logger.info(f"Learned Fact: {f_key} = {f_val}")
            except: 
                pass

        self.memory.add_conversation(user_id, prompt, response, permanent=permanent)
