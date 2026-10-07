"""
google_jobs.py
Scrapes AI/ML internship listings from Google Jobs (Google for Jobs).
Google Jobs aggregates listings from LinkedIn, Naukri, Indeed, Glassdoor,
Foundit, Shine, Cutshort, and many other portals — giving broad coverage
from a single source.

NOTE: Google's DOM structure changes frequently. If selectors stop matching,
open the page in a real browser, inspect a job card, and update accordingly.
"""

import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from scrapers.base import BaseScraper


class GoogleJobsScraper(BaseScraper):
    BASE_SEARCH_URL = "https://www.google.com/search?q={keyword}&ibp=htl;jobs"

    def scrape(self, keywords: list, locations: list) -> list:
        results = []
        seen_keys = set()

        with sync_playwright() as p:
            browser, context = self.new_browser_context(p)
            page = context.new_page()

            for keyword in keywords:
                slug = keyword.strip().replace(" ", "+")
                url = self.BASE_SEARCH_URL.format(keyword=slug)

                if not self._can_request(url):
                    continue

                try:
                    page.goto(url, timeout=self.settings.get("page_timeout_ms", 30000))
                    # Wait for job listings panel to render
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass

                    # Scroll the job listings panel to load more results
                    # Google Jobs uses a scrollable container for job cards
                    for _ in range(5):
                        page.mouse.wheel(0, 1500)
                        page.wait_for_timeout(800)

                    self._record_request(url)
                    self._delay()
                except Exception as e:
                    self.logger.error(f"Failed to load Google Jobs for '{keyword}': {e}")
                    continue

                # Strategy: click each job card and extract details from the
                # detail panel on the right side of the page.
                try:
                    listings = self._extract_from_page(page, keyword, seen_keys)
                    results.extend(listings)
                except Exception as e:
                    self.logger.error(f"Error extracting Google Jobs listings for '{keyword}': {e}")

            context.close()
            browser.close()

        self.logger.info(f"Google Jobs scrape complete: {len(results)} listings found")
        return results

    def _extract_from_page(self, page, keyword: str, seen_keys: set) -> list:
        """Extract job listings by clicking each card in the Google Jobs panel."""
        listings = []

        # Find all clickable job card elements
        # Google Jobs uses li elements inside a scrollable list
        card_selectors = [
            "li.iFjolb",          # Common Google Jobs card selector
            "div.PwjeAc",         # Alternative card container
            "li[data-ved]",       # Cards with data attributes
        ]

        cards = []
        for selector in card_selectors:
            cards = page.query_selector_all(selector)
            if cards:
                self.logger.info(f"Found {len(cards)} job cards using selector: {selector}")
                break

        if not cards:
            # Fallback: parse the full page text for job information
            self.logger.info("No cards found via selectors, using text-based extraction")
            return self._extract_from_text(page, keyword, seen_keys)

        for i, card in enumerate(cards):
            try:
                # Click the card to load details in the right panel
                card.click()
                page.wait_for_timeout(600)

                # Get the full page HTML after clicking
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")

                # Extract from the detail panel
                # Title
                title_el = soup.select_one("h2.KLsYvd, div.sH3zFd h2")
                title = title_el.get_text(strip=True) if title_el else None

                # Company
                company_el = soup.select_one("div.nJlQNd.sMzDkb, div.pwbHOb")
                company = company_el.get_text(strip=True) if company_el else None

                # Location
                location_el = soup.select_one("div.sMzDkb:not(.nJlQNd), span.pwbHOb + span")
                location_text = location_el.get_text(strip=True) if location_el else None

                # Posted time / via source
                posted_el = soup.select_one("span.SuWscb, div.LL4CDc")
                raw_posted = posted_el.get_text(strip=True) if posted_el else None

                # Apply links
                apply_links = []
                for link_el in soup.select("a.pMhGee, a[data-ved][href*='utm_campaign=google_jobs_apply']"):
                    href = link_el.get("href", "")
                    if href and "google_jobs_apply" in href:
                        apply_links.append(href)

                # Use the first apply link, or fall back to Google Jobs URL
                application_link = apply_links[0] if apply_links else None

                # Description snippet
                desc_el = soup.select_one("div.YgLbBe, span.HBvzbc")
                desc_snippet = desc_el.get_text(strip=True)[:200] if desc_el else None

                if not title or not company:
                    continue

                # Deduplicate
                dedup_key = (company.strip().lower(), title.strip().lower())
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                listings.append({
                    "source_portal": "Google Jobs",
                    "company_name": company.strip(),
                    "job_title": title.strip(),
                    "location": location_text,
                    "raw_posted_text": raw_posted,
                    "description_snippet": desc_snippet,
                    "application_link": application_link,
                    "search_keyword": keyword,
                })

            except Exception as e:
                self.logger.error(f"Error parsing Google Jobs card #{i}: {e}")
                continue

        return listings

    def _extract_from_text(self, page, keyword: str, seen_keys: set) -> list:
        """
        Fallback text-based extraction when CSS selectors fail.
        Parses the visible text on the page to identify job listings.
        """
        listings = []

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # Look for any structured job data in the page
        # Google Jobs sometimes embeds structured data as JSON-LD
        for script in soup.select("script[type='application/ld+json']"):
            try:
                import json
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "JobPosting":
                            self._parse_jsonld_job(item, keyword, listings, seen_keys)
                elif isinstance(data, dict):
                    if data.get("@type") == "JobPosting":
                        self._parse_jsonld_job(data, keyword, listings, seen_keys)
            except Exception:
                continue

        # Also try to parse visible text blocks that look like job listings
        # Look for elements that contain job-like content
        for el in soup.select("[role='treeitem'], [data-ved] div[jscontroller]"):
            try:
                text = el.get_text("\n", strip=True)
                lines = [l.strip() for l in text.split("\n") if l.strip()]

                if len(lines) < 2:
                    continue

                # Heuristic: first line is often the title, second is company
                title = lines[0] if len(lines) > 0 else None
                company = lines[1] if len(lines) > 1 else None
                location_text = lines[2] if len(lines) > 2 else None

                if not title or not company or len(title) < 5:
                    continue

                dedup_key = (company.strip().lower(), title.strip().lower())
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                # Find any link in the element
                link_el = el.select_one("a[href]")
                link = link_el["href"] if link_el else None

                listings.append({
                    "source_portal": "Google Jobs",
                    "company_name": company.strip(),
                    "job_title": title.strip(),
                    "location": location_text,
                    "raw_posted_text": None,
                    "description_snippet": None,
                    "application_link": link,
                    "search_keyword": keyword,
                })
            except Exception:
                continue

        return listings

    def _parse_jsonld_job(self, data: dict, keyword: str, listings: list, seen_keys: set):
        """Parse a JSON-LD JobPosting object into our listing format."""
        title = data.get("title")
        company_data = data.get("hiringOrganization", {})
        company = company_data.get("name") if isinstance(company_data, dict) else None
        location_data = data.get("jobLocation", {})
        if isinstance(location_data, dict):
            address = location_data.get("address", {})
            location_text = address.get("addressLocality", "") if isinstance(address, dict) else ""
        else:
            location_text = None

        if not title or not company:
            return

        dedup_key = (company.strip().lower(), title.strip().lower())
        if dedup_key in seen_keys:
            return
        seen_keys.add(dedup_key)

        listings.append({
            "source_portal": "Google Jobs",
            "company_name": company.strip(),
            "job_title": title.strip(),
            "location": location_text,
            "raw_posted_text": data.get("datePosted"),
            "description_snippet": (data.get("description", "") or "")[:200],
            "application_link": data.get("url"),
            "search_keyword": keyword,
        })
