"""
naukri.py
Scrapes AI/ML internship/job listings from Naukri.com's public search results.
NOTE: Naukri uses aggressive anti-bot measures and renders listings via JS.
This scraper uses Playwright with realistic browser behavior to avoid detection.
If selectors stop matching, inspect a listing card in a real browser and
update the CSS selectors below.
"""

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from scrapers.base import BaseScraper


class NaukriScraper(BaseScraper):
    # Naukri URL format for search
    BASE_SEARCH_URL = "https://www.naukri.com/{keyword}-jobs"
    # Alternative search URL that sometimes works better
    ALT_SEARCH_URL = "https://www.naukri.com/jobapi/v3/search?noOfResults=20&urlType=search_by_keyword&searchType=adv&keyword={keyword}&pageNo=1"

    def scrape(self, keywords: list, locations: list) -> list:
        results = []
        seen_keys = set()

        with sync_playwright() as p:
            # Use non-headless mode with more realistic settings to avoid detection
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                ]
            )
            context = browser.new_context(
                user_agent=self.settings.get("user_agent"),
                viewport={"width": 1366, "height": 768},
                locale="en-IN",
                timezone_id="Asia/Kolkata",
            )

            # Set extra headers to appear more like a real browser
            context.set_extra_http_headers({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            })

            page = context.new_page()

            # Remove automation detection markers
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
            """)

            # First visit the homepage to establish a session
            try:
                page.goto("https://www.naukri.com/", timeout=15000)
                page.wait_for_timeout(3000)
            except Exception as e:
                self.logger.warning(f"Failed to load Naukri homepage: {e}")

            for keyword in keywords:
                slug = keyword.strip().lower().replace(" ", "-")
                url = self.BASE_SEARCH_URL.format(keyword=slug)

                if not self._can_request(url):
                    continue

                try:
                    page.goto(url, timeout=self.settings.get("page_timeout_ms", 30000))
                    # Wait for content to render (Naukri is heavy JS)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        try:
                            page.wait_for_load_state("domcontentloaded", timeout=10000)
                        except Exception:
                            pass

                    # Extra wait for JS rendering
                    page.wait_for_timeout(3000)

                    # Scroll to trigger lazy loading
                    for _ in range(3):
                        page.mouse.wheel(0, 1000)
                        page.wait_for_timeout(1000)

                    html = page.content()
                    self._record_request(url)
                    self._delay()
                except Exception as e:
                    self.logger.error(f"Failed to fetch {url}: {e}")
                    self._record_request(url)
                    continue

                # Check for access denied
                if "Access Denied" in html or len(html) < 500:
                    self.logger.warning(f"Naukri blocked access for '{keyword}' (likely anti-bot)")
                    continue

                soup = BeautifulSoup(html, "html.parser")

                # Try multiple selector patterns — Naukri changes these frequently
                cards = soup.select("div.srp-jobtuple-wrapper")
                if not cards:
                    cards = soup.select("article.jobTuple")
                if not cards:
                    cards = soup.select("div.cust-job-tuple")
                if not cards:
                    cards = soup.select("div[class*='jobTuple']")
                if not cards:
                    # Try newer Naukri layout selectors
                    cards = soup.select("div[class*='styles_jlc__main']")
                if not cards:
                    cards = soup.select("div[data-job-id]")
                if not cards:
                    cards = soup.select("article[data-job-id]")

                if not cards:
                    # Fallback: try Playwright-based extraction
                    pw_results = self._extract_via_playwright(page, keyword, seen_keys)
                    if pw_results:
                        results.extend(pw_results)
                    else:
                        self.logger.warning(f"No listing cards found for '{keyword}' on Naukri "
                                            f"-- selectors may need updating or site is blocked.")
                    continue

                for card in cards:
                    try:
                        # Title: try multiple selectors
                        title = None
                        for sel in ["a.title", "a.ellipsis", "h2 a", "a[class*='title']",
                                    "a[class*='Title']", "div[class*='title'] a"]:
                            el = card.select_one(sel)
                            if el:
                                title = el.get_text(strip=True)
                                break

                        # Company: try multiple selectors
                        company = None
                        for sel in ["a.comp-name", "span.comp-name", "a.subTitle",
                                    "a[class*='comp']", "span[class*='comp']"]:
                            el = card.select_one(sel)
                            if el:
                                company = el.get_text(strip=True)
                                break

                        # Location: try multiple selectors
                        location = None
                        for sel in ["span.locWdth", "li.location", "span.loc",
                                    "span[class*='loc']", "div[class*='location']"]:
                            el = card.select_one(sel)
                            if el:
                                location = el.get_text(strip=True)
                                break

                        # Posted date
                        raw_posted = None
                        for sel in ["span.job-post-day", "span.fleft.postedDate",
                                    "span[class*='posted']", "span[class*='date']"]:
                            el = card.select_one(sel)
                            if el:
                                raw_posted = el.get_text(strip=True)
                                break

                        # Description
                        desc = None
                        for sel in ["span.job-desc", "div.job-description",
                                    "span[class*='desc']"]:
                            el = card.select_one(sel)
                            if el:
                                desc = el.get_text(strip=True)[:200]
                                break

                        # Link
                        link = None
                        for sel in ["a.title", "a.ellipsis", "h2 a"]:
                            el = card.select_one(sel)
                            if el and el.has_attr("href"):
                                link = el["href"]
                                break

                        if not title or not company:
                            continue

                        dedup_key = (company.strip().lower(), title.strip().lower())
                        if dedup_key in seen_keys:
                            continue
                        seen_keys.add(dedup_key)

                        results.append({
                            "source_portal": "Naukri",
                            "company_name": company,
                            "job_title": title,
                            "location": location,
                            "raw_posted_text": raw_posted,
                            "description_snippet": desc,
                            "application_link": link,
                            "search_keyword": keyword,
                        })
                    except Exception as e:
                        self.logger.error(f"Error parsing Naukri card: {e}")

            context.close()
            browser.close()

        self.logger.info(f"Naukri scrape complete: {len(results)} listings found")
        return results

    def _extract_via_playwright(self, page, keyword: str, seen_keys: set) -> list:
        """Fallback: use Playwright locators when BS4 selectors fail."""
        listings = []
        try:
            # Try to find job cards using broad Playwright locators
            job_cards = page.locator(
                "div[class*='jobTuple'], article[class*='jobTuple'], "
                "div[data-job-id], div[class*='srp-jobtuple']"
            ).all()

            if not job_cards:
                return listings

            self.logger.info(f"Playwright fallback found {len(job_cards)} Naukri cards for '{keyword}'")

            for card in job_cards[:15]:
                try:
                    title_el = card.locator("a[class*='title'], h2 a").first
                    title = title_el.inner_text(timeout=2000)

                    company_el = card.locator("a[class*='comp'], span[class*='comp']").first
                    company = company_el.inner_text(timeout=2000)

                    location = None
                    try:
                        loc_el = card.locator("span[class*='loc'], li[class*='location']").first
                        location = loc_el.inner_text(timeout=1000)
                    except Exception:
                        pass

                    if not title or not company:
                        continue

                    dedup_key = (company.strip().lower(), title.strip().lower())
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    listings.append({
                        "source_portal": "Naukri",
                        "company_name": company.strip(),
                        "job_title": title.strip(),
                        "location": location,
                        "raw_posted_text": None,
                        "description_snippet": None,
                        "application_link": None,
                        "search_keyword": keyword,
                    })
                except Exception:
                    continue

        except Exception as e:
            self.logger.error(f"Naukri Playwright fallback failed: {e}")

        return listings
