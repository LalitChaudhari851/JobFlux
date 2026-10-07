"""
wellfound.py
Scrapes AI/ML internship listings from Wellfound (formerly AngelList).
NOTE: Wellfound is heavily JS-rendered and may require scrolling to
trigger lazy-loaded content -- handled below via page.mouse.wheel scrolling.
Selectors may need updating if Wellfound changes its markup.
"""

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from scrapers.base import BaseScraper


class WellfoundScraper(BaseScraper):
    BASE_SEARCH_URL = "https://wellfound.com/role/internship/{keyword}"

    def scrape(self, keywords: list, locations: list) -> list:
        results = []
        with sync_playwright() as p:
            browser, context = self.new_browser_context(p)
            page = context.new_page()

            for keyword in keywords:
                slug = keyword.strip().lower().replace(" ", "-")
                url = self.BASE_SEARCH_URL.format(keyword=slug)

                if not self._can_request(url):
                    continue
                try:
                    page.goto(url, timeout=self.settings.get("page_timeout_ms", 30000))
                    # Scroll a few times to trigger lazy-loaded listings
                    for _ in range(4):
                        page.mouse.wheel(0, 2000)
                        page.wait_for_timeout(1000)
                    html = page.content()
                    self._record_request(url)
                    self._delay()
                except Exception as e:
                    self.logger.error(f"Failed to fetch {url}: {e}")
                    continue

                soup = BeautifulSoup(html, "html.parser")
                cards = soup.select("div[data-test='StartupResult'], div.job-listing")

                if not cards:
                    self.logger.warning(f"No listing cards found for '{keyword}' on Wellfound "
                                         f"-- selectors may need updating.")
                    continue

                for card in cards:
                    try:
                        company_el = card.select_one("h2, a[data-test='StartupResult-name']")
                        title_el = card.select_one("a[data-test='JobSearchResult-title'], span.job-title")
                        location_el = card.select_one("span.location, div.job-location")
                        posted_el = card.select_one("span.posted, time")

                        company = company_el.get_text(strip=True) if company_el else None
                        title = title_el.get_text(strip=True) if title_el else None
                        location = location_el.get_text(strip=True) if location_el else None
                        raw_posted = posted_el.get_text(strip=True) if posted_el else None
                        link = title_el["href"] if title_el and title_el.has_attr("href") else None
                        if link and link.startswith("/"):
                            link = "https://wellfound.com" + link

                        if not title or not company:
                            continue

                        results.append({
                            "source_portal": "Wellfound",
                            "company_name": company,
                            "job_title": title,
                            "location": location,
                            "raw_posted_text": raw_posted,
                            "description_snippet": None,
                            "application_link": link,
                            "search_keyword": keyword,
                        })
                    except Exception as e:
                        self.logger.error(f"Error parsing Wellfound card: {e}")

            context.close()
            browser.close()

        self.logger.info(f"Wellfound scrape complete: {len(results)} listings found")
        return results
