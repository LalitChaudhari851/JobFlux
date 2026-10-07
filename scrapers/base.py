"""
base.py
Shared base class for all portal scrapers: handles browser setup,
randomized delays, per-domain request caps, robots.txt checks, and logging.

Provides both synchronous (BaseScraper) and asynchronous (AsyncBaseScraper)
base classes. Portal scrapers use the sync version; company site crawling
uses the async version for concurrent email discovery.
"""

import random
import time
import asyncio
import logging
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright

from utils.robots_checker import is_allowed


class BaseScraper:
    """Synchronous base scraper — used by portal scrapers (Indeed, Internshala, etc.)."""

    def __init__(self, settings: dict, logger: logging.Logger):
        self.settings = settings
        self.logger = logger
        self._request_counts = {}

    def _domain_of(self, url: str) -> str:
        return urlparse(url).netloc

    def _can_request(self, url: str) -> bool:
        domain = self._domain_of(url)
        count = self._request_counts.get(domain, 0)
        max_allowed = self.settings.get("max_requests_per_domain", 40)
        if count >= max_allowed:
            self.logger.warning(f"Request cap reached for {domain}, skipping {url}")
            return False
        if not self.settings.get("ignore_robots_txt", False) and not is_allowed(url, user_agent="*"):
            self.logger.warning(f"robots.txt disallows scraping {url}, skipping")
            return False
        return True

    def _record_request(self, url: str):
        domain = self._domain_of(url)
        self._request_counts[domain] = self._request_counts.get(domain, 0) + 1

    def _delay(self):
        low = self.settings.get("min_delay_seconds", 2)
        high = self.settings.get("max_delay_seconds", 5)
        time.sleep(random.uniform(low, high))

    def fetch_page_html(self, page, url: str) -> str:
        """Fetch rendered HTML for a URL using an existing Playwright page object."""
        if not self._can_request(url):
            return None
        try:
            page.goto(url, timeout=self.settings.get("page_timeout_ms", 30000))
            page.wait_for_load_state("networkidle", timeout=self.settings.get("page_timeout_ms", 30000))
            html = page.content()
            self._record_request(url)
            self.logger.info(f"Fetched: {url}")
            self._delay()
            return html
        except Exception as e:
            self.logger.error(f"Failed to fetch {url}: {e}")
            self._record_request(url)
            return None

    def new_browser_context(self, playwright):
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=self.settings.get("user_agent"))
        return browser, context

    def scrape(self, keywords: list, locations: list) -> list:
        """Override in subclasses. Must return a list of dicts, one per listing."""
        raise NotImplementedError


class AsyncBaseScraper:
    """
    Asynchronous base scraper — used by the company site crawler for
    concurrent email discovery across multiple companies.
    
    Features over BaseScraper:
    - async/await throughout
    - Retry with exponential backoff (configurable)
    - Shared request counting across concurrent tasks
    """

    def __init__(self, settings: dict, logger: logging.Logger):
        self.settings = settings
        self.logger = logger
        self._request_counts = {}
        self._lock = asyncio.Lock()
        self._max_retries = settings.get("max_retries", 3)

    def _domain_of(self, url: str) -> str:
        return urlparse(url).netloc

    async def _can_request(self, url: str) -> bool:
        domain = self._domain_of(url)
        async with self._lock:
            count = self._request_counts.get(domain, 0)
        max_allowed = self.settings.get("max_requests_per_domain", 40)
        if count >= max_allowed:
            self.logger.warning(f"Request cap reached for {domain}, skipping {url}")
            return False
        # robots.txt check is synchronous — it caches aggressively so it's fine
        if not self.settings.get("ignore_robots_txt", False) and not is_allowed(url, user_agent="*"):
            self.logger.warning(f"robots.txt disallows scraping {url}, skipping")
            return False
        return True

    async def _record_request(self, url: str):
        domain = self._domain_of(url)
        async with self._lock:
            self._request_counts[domain] = self._request_counts.get(domain, 0) + 1

    async def _delay(self):
        low = self.settings.get("min_delay_seconds", 1)
        high = self.settings.get("max_delay_seconds", 3)
        await asyncio.sleep(random.uniform(low, high))

    async def fetch_page_html(self, page, url: str) -> str:
        """
        Fetch rendered HTML with retry + exponential backoff.
        Returns HTML string or None on failure.
        """
        if not await self._can_request(url):
            return None

        timeout = self.settings.get("page_timeout_ms", 30000)

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await page.goto(url, timeout=timeout)
                # Wait for page to be mostly loaded
                try:
                    await page.wait_for_load_state("networkidle", timeout=min(timeout, 10000))
                except Exception:
                    # networkidle can be flaky — proceed with domcontentloaded
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except Exception:
                        pass

                html = await page.content()
                await self._record_request(url)
                self.logger.info(f"Fetched: {url} (attempt {attempt})")
                await self._delay()
                return html

            except Exception as e:
                await self._record_request(url)
                if attempt < self._max_retries:
                    backoff = (2 ** attempt) + random.uniform(0, 1)
                    self.logger.warning(
                        f"Attempt {attempt}/{self._max_retries} failed for {url}: {e}. "
                        f"Retrying in {backoff:.1f}s..."
                    )
                    await asyncio.sleep(backoff)
                else:
                    self.logger.error(
                        f"All {self._max_retries} attempts failed for {url}: {e}"
                    )
                    return None

    async def new_browser_context(self, playwright):
        """Launch a browser and create a context for async Playwright."""
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=self.settings.get("user_agent")
        )
        return browser, context
