"""
yc.py
Scrapes AI/ML job listings from Y Combinator's Work at a Startup.
The site is JS-rendered and uses a text-based list layout.
"""

import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from scrapers.base import BaseScraper


class YCScraper(BaseScraper):
    BASE_SEARCH_URL = "https://www.workatastartup.com/jobs?query={keyword}"

    # Pattern for YC batch markers like (S11), (W14), (P26)
    BATCH_RE = re.compile(r"\(([A-Z]\d{2})\)")

    def scrape(self, keywords: list, locations: list) -> list:
        results = []
        seen_titles = set()

        with sync_playwright() as p:
            browser, context = self.new_browser_context(p)
            page = context.new_page()

            for keyword in keywords:
                slug = keyword.strip().replace(" ", "%20")
                url = self.BASE_SEARCH_URL.format(keyword=slug)

                if not self._can_request(url):
                    continue
                try:
                    page.goto(url, timeout=self.settings.get("page_timeout_ms", 30000))
                    # Wait for content to render
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    # Scroll to load more listings
                    for _ in range(3):
                        page.mouse.wheel(0, 2000)
                        page.wait_for_timeout(1000)
                    html = page.content()
                    self._record_request(url)
                    self._delay()
                except Exception as e:
                    self.logger.error(f"Failed to fetch {url}: {e}")
                    continue

                soup = BeautifulSoup(html, "html.parser")
                body_text = soup.body.get_text("\n", strip=True) if soup.body else ""
                lines = [l.strip() for l in body_text.split("\n") if l.strip()]

                # Parse the text-based listing format.
                # YC shows blocks like:
                #   CompanyName\u00a0(S24)
                #   \u2022 Company description
                #   Role Title
                #   Fulltime/Internship
                #   Location
                #   Category (Full stack, Machine learning, etc.)
                #   Salary range (optional)
                #   Apply

                i = 0
                while i < len(lines):
                    line = lines[i]

                    # Look for "Apply" markers to identify job blocks
                    if line == "Apply":
                        # Work backwards to extract role info
                        # The block before "Apply" has: role_title, type, location, category, [salary]
                        block_start = max(0, i - 8)
                        block = lines[block_start:i]

                        company = None
                        role_title = None
                        location_text = None
                        job_type = None

                        # Find the company name (has batch marker)
                        for j, bl in enumerate(block):
                            if self.BATCH_RE.search(bl):
                                raw_company = bl
                                # Remove batch marker and special chars
                                company = self.BATCH_RE.sub("", raw_company).replace("\u00a0", " ").replace("?", "").strip()
                                # Lines after company: description, then role info
                                remaining = block[j+1:]
                                # Skip description line (starts with bullet or is long)
                                role_lines = []
                                for rl in remaining:
                                    if rl.startswith("\u2022") or rl.startswith("•"):
                                        continue  # Skip description
                                    role_lines.append(rl)

                                if len(role_lines) >= 1:
                                    role_title = role_lines[0]
                                if len(role_lines) >= 2:
                                    job_type = role_lines[1]
                                if len(role_lines) >= 3:
                                    location_text = role_lines[2]
                                break

                        if company and role_title and len(role_title) > 3:
                            dedup_key = f"{company}|{role_title}"
                            if dedup_key not in seen_titles:
                                seen_titles.add(dedup_key)
                                results.append({
                                    "source_portal": "YC (Work at a Startup)",
                                    "company_name": company,
                                    "job_title": role_title,
                                    "location": location_text,
                                    "raw_posted_text": job_type,
                                    "description_snippet": None,
                                    "application_link": url,
                                    "search_keyword": keyword,
                                })
                    i += 1

            context.close()
            browser.close()

        self.logger.info(f"YC scrape complete: {len(results)} listings found")
        return results
