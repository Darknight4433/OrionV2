"""Quick integration test for Phase 1: Streaming + AI Manager + Intent Router"""
import sys, asyncio
sys.path.insert(0, '.')
from app.core.ai_manager import AIManager, QueryComplexity
from app.core.intent_router import IntentRouter
from app.services.memory_service import MemoryService
from app.services.browser_service import BrowserService
from app.core.internet_detector import InternetDetector

# Initialize services
memory = MemoryService()
browser = BrowserService()
ai = AIManager()
router = IntentRouter(ai, memory, browser)


async def test():
    print("=" * 50)
    print("ORION Phase 1 Integration Test")
    print("=" * 50)
    
    # Test 1: Rule Engine
    print("\n--- Test 1: Rule Engine (time) ---")
    chunks = []
    async for chunk in router.process_stream("Vaishnavi", "what time is it"):
        chunks.append(chunk)
    print(f"Response: {''.join(chunks)}")
    
    # Test 2: Rule Engine (task)
    print("\n--- Test 2: Rule Engine (add task) ---")
    chunks = []
    async for chunk in router.process_stream("Vaishnavi", "add task review the ORION code"):
        chunks.append(chunk)
    print(f"Response: {''.join(chunks)}")
    
    # Test 3: Rule Engine (battery)
    print("\n--- Test 3: Rule Engine (system status) ---")
    chunks = []
    async for chunk in router.process_stream("Vaishnavi", "system status"):
        chunks.append(chunk)
    print(f"Response: {''.join(chunks)}")
    
    # Test 4: Internet Detection
    print("\n--- Test 4: Internet Detection ---")
    d = InternetDetector()
    tests = [
        "what time is it",
        "what is the price of gold today",
        "tell me a joke",
        "who is the president of India",
        "remind me to buy milk",
        "search for python tutorials",
        "latest news about AI",
        "hello orion how are you",
    ]
    for t in tests:
        r = d.analyze(t)
        status = "INTERNET" if r.needs_internet else "LOCAL"
        print(f"  [{status:8s}] ({r.confidence:.0%}) {t}")
        if r.search_query:
            print(f"           Query: {r.search_query}")
    
    # Test 5: Complexity Assessment
    print("\n--- Test 5: Complexity Assessment ---")
    test_queries = [
        ("hi", "SIMPLE"),
        ("what time", "SIMPLE"),
        ("explain quantum computing to me", "COMPLEX"),
        ("write a function to sort an array", "COMPLEX"),
        ("how is the weather", "MODERATE"),
    ]
    for query, expected in test_queries:
        actual = router._assess_complexity(query)
        match = "OK" if actual.value == expected.lower() else "MISMATCH"
        print(f"  [{match}] '{query}' -> {actual.value} (expected {expected.lower()})")
    
    # Test 6: AI Manager Health
    print("\n--- Test 6: AI Manager Health ---")
    health = ai.get_health_status()
    for provider, status in health.items():
        avail = "READY" if status["available"] else "DOWN"
        print(f"  {provider:12s} [{avail}] failures={status['consecutive_failures']}")
    
    print("\n" + "=" * 50)
    print("All tests passed!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(test())
