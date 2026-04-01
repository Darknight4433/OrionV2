#!/usr/bin/env python3
"""
🎬 ORION DEMO SCRIPT v1.0

Demonstrates full system capabilities for school presentation.
Run this to showcase all features in sequence:

1. Voice command → AI response
2. Task add via Telegram
3. Meeting reminder
4. Habit suggestion
5. Daily briefing
6. Smart question answering
"""

import sys
import time
import asyncio

sys.path.insert(0, '.')
sys.path.insert(0, './backend')

from backend.app.core.intent_engine import IntentEngine
from backend.app.services.memory_service import MemoryService
from backend.app.services.gemini_service import GeminiService
from backend.app.services.ollama_service import OllamaService
from backend.app.services.browser_service import BrowserService
from backend.app.services.greeting_service import GreetingService
from backend.app.services.vision_service import VisionService
from backend.app.services.habit_service import HabitDetector
from backend.app.services.habit_suggester import HabitSuggester
from backend.app.services.decision_engine import DecisionEngine
from backend.app.services.planner_engine import PlannerEngine
from backend.app.services.briefing_engine import BriefingEngine
from backend.app.core.logging import get_logger

logger = get_logger()

DEMO_USER = "principal_demo"

class ORIONDemo:
    """Interactive demo showcasing ORION capabilities."""
    
    def __init__(self):
        logger.info("🎬 ORION DEMO INITIALIZATION")
        
        # Initialize services
        self.memory = MemoryService()
        self.gemini = GeminiService(self.memory)
        self.ollama = OllamaService(self.memory)
        self.browser = BrowserService()
        self.greeting = GreetingService(self.memory)
        self.vision = VisionService()
        self.habit_detector = HabitDetector(self.memory)
        self.habit_suggester = HabitSuggester(self.memory)
        self.decision_engine = DecisionEngine(self.memory, self.habit_suggester)
        self.planner_engine = PlannerEngine()
        self.briefing_engine = BriefingEngine(self.memory)
        
        self.intent_engine = IntentEngine(
            self.gemini, self.ollama, self.memory,
            self.browser, self.vision,
            self.habit_detector, self.habit_suggester,
            self.briefing_engine
        )
        
        logger.info("✅ All services initialized")
    
    def print_section(self, title: str):
        """Print a formatted section header."""
        print(f"\n{'='*60}")
        print(f"🎯 {title}")
        print(f"{'='*60}\n")
    
    async def demo_voice_command(self):
        """Demo 1: Voice command → AI response."""
        self.print_section("DEMO 1: VOICE COMMAND")
        
        queries = [
            "What is photosynthesis?",
            "Add a reminder for 3 PM",
            "What's tomorrow's weather?"
        ]
        
        for query in queries:
            print(f"🎤 USER: {query}")
            start = time.time()
            response, ai_mode = await self.intent_engine.process_input(
                DEMO_USER, query, stream_callback=None
            )
            duration = time.time() - start
            print(f"🤖 ORION ({ai_mode}): {response}")
            print(f"⏱️  Response time: {duration:.2f}s\n")
            time.sleep(0.5)
    
    async def demo_task_management(self):
        """Demo 2: Task management."""
        self.print_section("DEMO 2: TASK MANAGEMENT")
        
        # Add tasks
        tasks = [
            "Meeting with department heads at 10 AM",
            "Review student progress reports",
            "Approve budget for sports event"
        ]
        
        print("📋 Adding tasks to system...\n")
        for task in tasks:
            self.memory.add_task(task, DEMO_USER)
            print(f"✅ Added: {task}")
            time.sleep(0.3)
        
        # Retrieve and display
        print("\n📋 Current tasks:")
        recent_tasks = self.memory.get_recent_tasks(DEMO_USER, limit=10)
        for i, task in enumerate(recent_tasks, 1):
            print(f"  {i}. {task}")
    
    async def demo_reminders(self):
        """Demo 3: Smart reminders with context."""
        self.print_section("DEMO 3: SMART REMINDERS")
        
        # Create a meeting reminder
        action = {
            "type": "MEETING",
            "text": "Your meeting with the Board is in 10 minutes.",
            "priority": 5
        }
        
        print("⏰ Original reminder:")
        print(f"  {action['text']}\n")
        
        # Expand with context via planner
        planned = self.planner_engine.build_plan(action, self.memory)
        print("📌 Expanded with context:")
        print(f"  {planned.get('text', 'No expansion')}\n")
    
    async def demo_habits(self):
        """Demo 4: Habit suggestions."""
        self.print_section("DEMO 4: HABIT SUGGESTIONS")
        
        # Log some activities
        activities = ["Checked grades", "Reviewed files", "Lunch break"]
        print("📊 Recording activities...\n")
        for activity in activities:
            self.habit_detector.log_action(DEMO_USER, activity)
            print(f"  logged: {activity}")
            time.sleep(0.2)
        
        # Get suggestions
        print("\n💡 Habit suggestions:")
        suggestions = self.habit_suggester.suggest(DEMO_USER)
        for i, suggestion in enumerate(suggestions[:3], 1):
            print(f"  {i}. {suggestion}")
    
    async def demo_briefing(self):
        """Demo 5: Daily briefing."""
        self.print_section("DEMO 5: MORNING BRIEFING")
        
        briefing = self.briefing_engine.get_morning_briefing(DEMO_USER)
        print(f"📢 {briefing}\n")
    
    async def demo_smart_qa(self):
        """Demo 6: Smart Q&A with routing."""
        self.print_section("DEMO 6: SMART Q&A")
        
        from orion.core.router import classify_query, get_ai_response
        
        questions = [
            ("What's the latest news?", "REALTIME query"),
            ("Define machine learning", "FACT query"),
            ("Who is the current president?", "DYNAMIC_FACT query"),
            ("How should I organize meetings?", "GENERAL query"),
        ]
        
        for question, label in questions:
            print(f"📚 {label}")
            print(f"❓ {question}")
            try:
                query_type = classify_query(question)
                response, ai_mode = get_ai_response(question, query_type)
                print(f"🔍 Classification: {query_type}")
                print(f"💭 Response: {response[:100]}...\n")
            except Exception as e:
                print(f"⚠️  Error: {e}\n")
            time.sleep(0.5)
    
    async def run_full_demo(self):
        """Run complete demo sequence."""
        print("\n" + "="*60)
        print("🏆 ORION — AI Executive Assistant Demo")
        print("="*60)
        print("\nShowing all capabilities in sequence...\n")
        
        try:
            await self.demo_voice_command()
            await self.demo_task_management()
            await self.demo_reminders()
            await self.demo_habits()
            await self.demo_briefing()
            await self.demo_smart_qa()
            
            self.print_section("DEMO COMPLETE ✅")
            print("All systems operational and ready for production.\n")
            
        except Exception as e:
            logger.error(f"Demo error: {e}")
            print(f"\n❌ Demo failed: {e}\n")


async def main():
    """Run the demo."""
    demo = ORIONDemo()
    await demo.run_full_demo()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Demo interrupted by user.")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
