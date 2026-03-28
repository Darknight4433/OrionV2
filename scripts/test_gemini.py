import sys
import os
import asyncio

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.services.gemini_service import GeminiService
from backend.app.services.memory_service import MemoryService

async def test_gemini():
    print("Initializing ORION Intelligence Test...")
    memory = MemoryService()
    gemini = GeminiService(memory)
    
    if not gemini.api_keys:
        print("FAIL: No API keys found in .env (or list is empty).")
        return

    print(f"Active API Keys found: {len(gemini.api_keys)}")
    print("Testing response stream...")
    
    response_found = False
    async for chunk in gemini.get_response_stream("test_user", "Hello ORION, are you online?"):
        print(f"ORION: {chunk}")
        response_found = True
        break # Just test connectivity
    
    if response_found:
        print("\nSUCCESS: Gemini Service is communicating.")
    else:
        print("\nFAIL: No response received from Gemini.")

if __name__ == "__main__":
    # GeminiService.get_response_stream is synchronous generator in current implementation
    # but the intent engine treats it as one. 
    # Let's check the service definition again.
    # Ah, it's a sync generator: def get_response_stream(...) -> Generator[str, None, None]
    
    print("Initializing ORION Intelligence Test...")
    memory = MemoryService()
    gemini = GeminiService(memory)
    
    if not gemini.api_keys:
        print("FAIL: No API keys found in .env (or list is empty).")
        sys.exit(1)

    print(f"Active API Keys found: {len(gemini.api_keys)}")
    print("Testing response stream...")
    
    try:
        for chunk in gemini.get_response_stream("test_user", "Hello ORION, are you online?"):
            print(f"ORION: {chunk}")
            break
        print("\nSUCCESS: Gemini Service is communicating.")
    except Exception as e:
        print(f"\nFAIL: Error during communication: {e}")
