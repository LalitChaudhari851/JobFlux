"""
indeed.py
Scrapes AI/ML internship listings from Indeed's public search results.
Indeed frequently changes its HTML structure, so multiple fallback selectors
are used. The scraper also supports location-filtered URLs.
"""

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from scrapers.base import BaseScraper


class IndeedScraper(BaseScraper):
    BASE_SEARCH_URL = "https://in.indeed.com/jobs?q={keyword}&l={location}"

    def scrape(self, keywords: list, locations: list) -> list:
        results = []
        seen_keys = set()

        with sync_playwright() as p:
            browser, context = self.new_browser_context(p)
            page = context.new_page()

            for keyword in keywords:
                slug = keyword.strip().replace(" ", "+")

                # Extract location from the keyword if it contains a city name
                keyword_location = ""
                for loc in locations:
                    if loc.lower() in keyword.lower():
                        keyword_location = loc
                        break

                url = self.BASE_SEARCH_URL.format(
                    keyword=slug,
                    location=keyword_location.replace(" ", "+") if keyword_location else ""
                )

                if not self._can_request(url):
                    continue

                try:
                    page.goto(url, timeout=self.settings.get("page_timeout_ms", 30000))
                    # Wait longer for Indeed — it loads content dynamically
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        try:
                            page.wait_for_load_state("domcontentloaded", timeout=10000)
                        except Exception:
                            pass
                    # Extra wait for JS rendering
                    page.wait_for_timeout(2000)
                    html = page.content()
                    self._record_request(url)
                    self._delay()
                except Exception as e:
                    self.logger.error(f"Failed to fetch Indeed for '{keyword}': {e}")
                    self._record_request(url)
                    continue

                soup = BeautifulSoup(html, "html.parser")

                # Try multiple selectors — Indeed changes their class names frequently
                cards = soup.select("div.cardOutline.tapItem.result")
                if not cards:
                    cards = soup.select("div.job_seen_beacon")
                if not cards:
                    cards = soup.select("div.resultContent")
                if not cards:
                    cards = soup.select("div[data-jk]")
                if not cards:
                    cards = soup.select("a.tapItem")
                if not cards:
                    cards = soup.select("td.resultContent")
                if not cards:
                    cards = soup.select("div.slider_item")

                if not cards:
                    # Fallback: try Playwright-based extraction
                    pw_results = self._extract_via_playwright(page, keyword, seen_keys)
                    if pw_results:
                        results.extend(pw_results)
                    else:
                        self.logger.warning(f"No listing cards found for '{keyword}' on Indeed "
                                            f"-- selectors may need updating.")
                    continue

                for card in cards:
                    try:
                        # Title: multiple possible selectors
                        title = None
                        for sel in ["a.jcs-JobTitle", "h2.jobTitle a", "span[id^='jobTitle-']",
                                    "a[data-jk]", "h2.jobTitle"]:
                            el = card.select_one(sel)
                            if el:
                                title = el.get_text(strip=True)
                                break

                        # Company: multiple possible selectors
                        company = None
                        for sel in ["[data-testid='company-name']", "span.companyName",
                                    "span.css-1x7txa1", "a.companyName"]:
                            el = card.select_one(sel)
                            if el:
                                company = el.get_text(strip=True)
                                break

                        # Location: multiple possible selectors
                        location_text = None
                        for sel in ["[data-testid='text-location']", "div.companyLocation",
                                    "span.companyLocation"]:
                            el = card.select_one(sel)
                            if el:
                                location_text = el.get_text(strip=True)
                                break

                        # If no location found from selectors, use the keyword location
                        if not location_text and keyword_location:
                            location_text = keyword_location

                        # Posted date
                        raw_posted = None
                        for span in card.find_all(["span", "div"]):
                            t = span.get_text(strip=True).lower()
                            if "ago" in t or "posted" in t or "just now" in t:
                                raw_posted = span.get_text(strip=True)
                                break

                        # Snippet
                        desc = None
                        for sel in ["[data-testid='belowJobSnippet']", "div.job-snippet",
                                    "table.jobCardShelfContainer", "div.heading6"]:
                            el = card.select_one(sel)
                            if el:
                                desc = el.get_text(strip=True)[:200]
                                break

                        # Link
                        link = None
                        for sel in ["a.jcs-JobTitle", "a[data-jk]", "h2.jobTitle a"]:
                            link_el = card.select_one(sel)
                            if link_el and link_el.has_attr("href"):
                                href = link_el["href"]
                                if href.startswith("/"):
                                    link = "https://in.indeed.com" + href
                                else:
                                    link = href
                                break

                        if not title or not company:
                            continue

                        dedup_key = (company.strip().lower(), title.strip().lower())
                        if dedup_key in seen_keys:
                            continue
                        seen_keys.add(dedup_key)

                        results.append({
                            "source_portal": "Indeed",
                            "company_name": company,
                            "job_title": title,
                            "location": location_text,
                            "raw_posted_text": raw_posted,
                            "description_snippet": desc,
                            "application_link": link,
                            "search_keyword": keyword,
                        })
                    except Exception as e:
                        self.logger.error(f"Error parsing Indeed card: {e}")

            context.close()
            browser.close()

        self.logger.info(f"Indeed scrape complete: {len(results)} listings found")
        return results

    def _extract_via_playwright(self, page, keyword: str, seen_keys: set) -> list:
        """Fallback: use Playwright locators to extract job data when BS4 selectors fail."""
        listings = []
        try:
            # Try to find job cards using Playwright's more flexible locators
            job_cards = page.locator("[data-jk], .tapItem, .job_seen_beacon, .resultContent").all()
            if not job_cards:
                return listings

            self.logger.info(f"Playwright fallback found {len(job_cards)} cards for '{keyword}'")

            for card in job_cards[:15]:  # Limit to first 15 to avoid timeouts
                try:
                    title = card.locator("h2, [class*='jobTitle'], a[class*='Title']").first.inner_text(timeout=2000)
                    company = card.locator("[data-testid='company-name'], [class*='companyName']").first.inner_text(timeout=2000)

                    location_text = None
                    try:
                        location_text = card.locator("[data-testid='text-location'], [class*='companyLocation']").first.inner_text(timeout=1000)
                    except Exception:
                        pass

                    if not title or not company:
                        continue

                    dedup_key = (company.strip().lower(), title.strip().lower())
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    listings.append({
                        "source_portal": "Indeed",
                        "company_name": company.strip(),
                        "job_title": title.strip(),
                        "location": location_text,
                        "raw_posted_text": None,
                        "description_snippet": None,
                        "application_link": None,
                        "search_keyword": keyword,
                    })
                except Exception:
                    continue

        except Exception as e:
            self.logger.error(f"Playwright fallback failed: {e}")

        return listings
