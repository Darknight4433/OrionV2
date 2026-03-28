import asyncio
from playwright.async_api import async_playwright, TimeoutError
from typing import Optional
import re
from ..core.logging import get_logger

logger = get_logger()

class BrowserService:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.semaphore = asyncio.Semaphore(2)
        self.max_content_length = 5000 # Safety limit

    async def _ensure_browser(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()
        if not self.browser:
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )

    def _sanitize_content(self, text: str) -> str:
        """Cleans and truncates text to prevent malicious payload storage."""
        if not text: return ""
        # Remove weird characters but keep punctuation
        clean = re.sub(r'[^\w\s.,!?-]', '', text)
        # Collapse whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        # Initial truncation
        if len(clean) > self.max_content_length:
            logger.warning(f"Truncating scraped content from {len(clean)} to {self.max_content_length} chars")
            clean = clean[:self.max_content_length] + "...[truncated]"
        return clean

    async def scrape_page(self, url: str) -> str:
        if not url.startswith('http'): 
            return "Invalid URL"

        async with self.semaphore:
            await self._ensure_browser()
            page = await self.browser.new_page()
            try:
                # 15s Timeout - Aggressive for production
                await page.goto(url, wait_until='domcontentloaded', timeout=15000)
                
                # Extract text
                content = await page.inner_text('body')
                
                # Sanitize
                safe_content = self._sanitize_content(content)
                return safe_content
                
            except TimeoutError:
                logger.warning(f"Timeout scraping {url}")
                return "Error: Page took too long to load."
            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")
                return f"Error scraping page: {str(e)[:100]}"
            finally:
                await page.close()

    async def perform_google_search(self, query: str) -> list[str]:
        # Input validation
        if len(query) > 100: query = query[:100]
        
        async with self.semaphore:
            await self._ensure_browser()
            page = await self.browser.new_page()
            results = []
            try:
                await page.goto(f"https://www.google.com/search?q={query}", timeout=10000)
                try:
                    await page.wait_for_selector('div.g', timeout=5000)
                except:
                    return ["No results found."]

                elements = await page.query_selector_all('div.g')
                for el in elements[:5]:
                    try:
                        title_el = await el.query_selector("h3")
                        link_el = await el.query_selector("a")
                        if title_el and link_el:
                            title = await title_el.inner_text()
                            link = await link_el.get_attribute("href")
                            if link and link.startswith('http'):
                                safe_title = self._sanitize_content(title)[:200]
                                results.append(f"{safe_title}: {link}")
                    except: continue
            except Exception as e:
                 logger.error(f"Search failed: {e}")
                 results.append("Search failed.")
            finally:
                await page.close()
            return results

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
