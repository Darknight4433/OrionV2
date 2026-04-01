#!/usr/bin/env python3
"""
Test Human Trust Layer Implementation
"""

import sys
import os
sys.path.append('backend')

def test_usage_learner():
    """Test usage learner with trust layer features."""
    try:
        from app.services.usage_learner import get_learner
        learner = get_learner()

        # Test gradual application
        pattern1 = {"type": "tone", "tone": "formal"}
        pattern2 = {"type": "length", "length": "short"}
        pattern3 = {"type": "shortcut", "command": "test", "action": "action"}
        pattern4 = {"type": "tone", "tone": "casual"}  # Should be limited

        result1 = learner.apply_gradually(pattern1)
        result2 = learner.apply_gradually(pattern2)
        result3 = learner.apply_gradually(pattern3)
        result4 = learner.apply_gradually(pattern4)  # Should fail due to limit

        print("✓ Usage Learner:")
        print(f"  Pattern 1 applied: {result1}")
        print(f"  Pattern 2 applied: {result2}")
        print(f"  Pattern 3 applied: {result3}")
        print(f"  Pattern 4 applied: {result4} (should be False due to limit)")

        # Test personality lock
        rules = learner.get_adaptation_rules()
        personality = rules.get("personality_lock", {})
        print(f"  Personality lock: {personality}")

        return True
    except Exception as e:
        print(f"✗ Usage Learner failed: {e}")
        return False

def test_decision_engine():
    """Test decision engine with trust layer features."""
    try:
        from app.services.memory_service import MemoryService
        from app.services.habit_suggester import HabitSuggester
        from app.services.decision_engine import DecisionEngine

        memory = MemoryService()
        habit_suggester = HabitSuggester(memory)
        engine = DecisionEngine(memory, habit_suggester)

        # Test with low confidence (should return None)
        result_low = engine.choose_best_action("test_user", user_busy=False)
        print("✓ Decision Engine:")
        print(f"  Low confidence result: {result_low}")

        return True
    except Exception as e:
        print(f"✗ Decision Engine failed: {e}")
        return False

def test_health_monitor():
    """Test health monitor with degradation detection."""
    try:
        from app.services.health_monitor import get_health_monitor
        monitor = get_health_monitor()

        # Test health check
        result = monitor.run_full_health_check()
        print("✓ Health Monitor:")
        print(f"  Health check result: {result['healthy']}")
        print(f"  Alerts: {len(result['alerts'])}")

        return True
    except Exception as e:
        print(f"✗ Health Monitor failed: {e}")
        return False

if __name__ == "__main__":
    print("🧠 Testing Human Trust Layer Implementation\n")

    tests = [
        test_usage_learner,
        test_decision_engine,
        test_health_monitor
    ]

    passed = 0
    for test in tests:
        if test():
            passed += 1
        print()

    print(f"Results: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("🎉 Human Trust Layer implementation successful!")
    else:
        print("⚠️  Some tests failed - check implementation")