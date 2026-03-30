import requests
import json
import datetime
from typing import Generator
from ..core.config import settings
from ..core.logging import get_logger
from ..services.memory_service import MemoryService

logger = get_logger()

class OllamaService:
    def __init__(self, memory_service: MemoryService):
        self.memory = memory_service
        self.base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = getattr(settings, "OLLAMA_MODEL", "llama3")

    def get_response_stream(self, user_id: str, prompt: str) -> Generator[str, None, None]:
        # Prompt structure is handled by IntentEngine for better personalization
        system_prompt = prompt


        try:
            url = f"{self.base_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "stream": True
            }
            
            logger.info(f"Attempting local fallback with Ollama model: {self.model}")
            
            response = requests.post(url, json=payload, stream=True, timeout=10)
            response.raise_for_status()
            
            full_response = ""
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    if 'message' in chunk and 'content' in chunk['message']:
                        content = chunk['message']['content']
                        full_response += content
                        yield content
                    if chunk.get('done'):
                        break
            
            # Save to memory
            self._save_memory(user_id, prompt, full_response)
            
        except Exception as e:
            logger.error(f"Ollama local fallback failed: {e}")
            yield f"SYSTEM ERROR: Both Gemini and Ollama fallback failed. Error: {str(e)[:50]}"

    def _save_memory(self, user_id: str, prompt: str, response: str):
        # We can reuse the logic from GeminiService or put it in a base class/helper
        # For simplicity now, I'll just save the conversation
        self.memory.add_conversation(user_id, prompt, response, permanent=False)

    def classify_memory_item(self, user_input: str) -> str:
        """Classify a user statement for memory storage."""
        try:
            prompt = f"""
You are a classification assistant. A user statement is provided, and you must classify it as one of exactly: preference, habit, fact, ignore.
Return exactly one word and nothing else.

Text: \"{user_input.strip()}\"
"""
            url = f"{self.base_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "Classify user memory statements for ORION."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False
            }
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                if "choices" in data and len(data["choices"]) > 0:
                    text = data["choices"][0].get("message", {}).get("content", "").strip().lower()
                    candidate = text.split()[0] if text else ""
                    if candidate in {"preference", "habit", "fact", "ignore"}:
                        return candidate
            return "ignore"
        except Exception as e:
            logger.warn(f"Memory classification failed: {e}")
            return "ignore"
