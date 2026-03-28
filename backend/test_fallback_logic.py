import asyncio
import os
import sys

# Change directory to backend to import modules correctly
sys.path.append(os.getcwd())

from app.services.memory_service import MemoryService
from app.services.gemini_service import GeminiService
from app.services.ollama_service import OllamaService
from app.services.browser_service import BrowserService
from app.core.intent_engine import IntentEngine

async def test_fallback():
    # 1. Setup services
    memory = MemoryService()
    
    # Create a "Broken" Gemini Service (no keys)
    from unittest.mock import MagicMock
    gemini = GeminiService(memory)
    gemini.api_keys = [] # Force failure
    
    ollama = OllamaService(memory)
    browser = BrowserService()
    
    # 2. Init Engine
    engine = IntentEngine(gemini, ollama, memory, browser)
    
    # 3. Process test message
    print("Testing Fallback: 'What time is it in Tokyo?'")
    user_id = "test_user"
    message = "Tell me a joke."
    
    # We expect this to hit Gemini, find no keys (or a system critical msg), 
    # and then use Ollama.
    
    # Because Gemini yields a "SYSTEM CRITICAL" msg when keys are empty,
    # the IntentEngine should detect it and switch.
    
    print("--- RESPONSE FROM ORION ---")
    response = await engine.process(user_id, message)
    print(response)
    print("--- END RESPONSE ---")

if __name__ == "__main__":
    asyncio.run(test_fallback())
