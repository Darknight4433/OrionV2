import asyncio
import sys
import os

# Adjust path to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.services.browser_service import BrowserService
from backend.app.services.memory_service import MemoryService

async def ingest(url: str):
    print(f"Starting ingestion for: {url}")
    
    browser = BrowserService()
    memory = MemoryService() # Defaults to backend/data/orion.db if running from root, might need adjustment
    
    try:
        content = await browser.scrape_page(url)
        print(f"Extracted {len(content)} characters.")
        
        # Store in memory as a 'fact' or 'conversation' for now
        # Ideally we'd chunk this and vector store it, but for Phase 1:
        memory.add_conversation("SYSTEM", f"Learn from {url}", f"Content: {content[:2000]}...", permanent=True)
        print("Stored in memory.")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await browser.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingest_knowledge.py <url>")
        sys.exit(1)
    
    url = sys.argv[1]
    asyncio.run(ingest(url))
