import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from backend.app.services.gemini_service import GeminiService
from backend.app.services.memory_service import MemoryService

def test_gemini():
    print("=" * 45)
    print("   ORION GEMINI INTELLIGENCE TEST")
    print("=" * 45)
    
    memory = MemoryService()
    gemini = GeminiService(memory)
    
    if not gemini.api_keys:
        print("[FAIL] No Gemini API keys found in .env (GEMINI_API_KEYS is empty).")
        return False

    print(f"[OK] Active API Keys found: {len(gemini.api_keys)}")
    print("Testing response stream with prompt: 'Hello ORION, are you online?'...\n")
    
    try:
        response_chunks = []
        for chunk in gemini.get_response_stream("test_user", "Hello ORION, are you online?"):
            response_chunks.append(chunk)
            print(chunk, end="", flush=True)
            if len(response_chunks) >= 3:
                # Successfully received response stream
                break
        
        print("\n\n[SUCCESS] Gemini Service is communicating properly.")
        return True
    except Exception as e:
        print(f"\n[FAIL] Error during communication: {e}")
        return False

if __name__ == "__main__":
    success = test_gemini()
    sys.exit(0 if success else 1)
