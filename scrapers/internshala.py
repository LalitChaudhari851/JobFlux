"""
internshala.py
Scrapes AI/ML internship listings from Internshala's public search results.
NOTE: Internshala's HTML structure changes periodically -- if selectors stop
matching, open the page in a real browser, right-click a listing card ->
Inspect, and update the CSS selectors below accordingly.
"""

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from scrapers.base import BaseScraper


class InternshalaScraper(BaseScraper):
    BASE_SEARCH_URL = "https://internshala.com/internships/keywords-{keyword}/"

    def scrape(self, keywords: list, locations: list) -> list:
        results = []
        with sync_playwright() as p:
            browser, context = self.new_browser_context(p)
            page = context.new_page()

            for keyword in keywords:
                slug = keyword.strip().replace(" ", "%20")
                url = self.BASE_SEARCH_URL.format(keyword=slug)
                html = self.fetch_page_html(page, url)
                if not html:
                    continue

                soup = BeautifulSoup(html, "html.parser")
                cards = soup.select("div.internship_meta") or soup.select("div.individual_internship")

                if not cards:
                    self.logger.warning(f"No listing cards found for '{keyword}' on Internshala "
                                         f"-- selectors may need updating.")
                    continue

                for card in cards:
                    try:
                        title_el = card.select_one("a.job-title-href, h3.job-internship-name")
                        company_el = card.select_one("p.company-name, a.link_display_like_text")
                        location_el = card.select_one("div.locations, p.locations, a.location_link")
                        posted_el = card.select_one("div.status-inactive, div.status-success, span.status")
                        link_el = card.select_one("a")

                        title = title_el.get_text(strip=True) if title_el else None
                        company = company_el.get_text(strip=True) if company_el else None
                        location = location_el.get_text(strip=True) if location_el else None
                        raw_posted = posted_el.get_text(strip=True) if posted_el else None
                        link = link_el["href"] if link_el and link_el.has_attr("href") else None
                        if link and link.startswith("/"):
                            link = "https://internshala.com" + link

                        if not title or not company:
                            continue

                        results.append({
                            "source_portal": "Internshala",
                            "company_name": company,
                            "job_title": title,
                            "location": location,
                            "raw_posted_text": raw_posted,
                            "description_snippet": None,
                            "application_link": link,
                            "search_keyword": keyword,
                        })
                    except Exception as e:
                        self.logger.error(f"Error parsing Internshala card: {e}")

            context.close()
            browser.close()

        self.logger.info(f"Internshala scrape complete: {len(results)} listings found")
        return results
