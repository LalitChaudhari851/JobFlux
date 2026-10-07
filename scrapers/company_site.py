"""
company_site.py
Given a company's website, crawls multiple pages, discovers internal links,
and extracts ALL publicly listed email addresses. Never guesses or generates emails.

Key improvements over the original:
- 20+ predefined paths instead of 5
- Internal link discovery with keyword prioritization
- Sitemap.xml parsing
- Collects ALL emails (not just the first)
- Parses mailto: links AND regex
- Searches footer/header elements specifically
- Configurable page limit
- Async operation for concurrent company crawling
"""

import re
import asyncio
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from scrapers.base import AsyncBaseScraper
from utils.email_scorer import score_email, is_excluded_email
from utils.classifier import classify_from_multiple_pages

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# ── Extended set of candidate paths ──────────────────────────────
CANDIDATE_PATHS = [
    "",              # homepage
    "contact",
    "contact-us",
    "about",
    "about-us",
    "careers",
    "jobs",
    "join-us",
    "work-with-us",
    "hiring",
    "people",
    "team",
    "our-team",
    "company",
    "support",
    "legal",
    "privacy",
    "privacy-policy",
    "press",
    "media",
    "faq",
    "blog",
]

# Keywords that indicate a page is likely to contain recruiter emails
PRIORITY_LINK_KEYWORDS = {
    "career", "careers", "jobs", "job", "join", "hiring", "hire",
    "team", "people", "contact", "company", "about", "support",
    "work-with", "talent", "recruit", "apply", "openings",
    "opportunities", "vacancies",
}

# File extensions to skip when discovering internal links
SKIP_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".mp4", ".mp3", ".avi", ".mov",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
}


class CompanySiteScraper(AsyncBaseScraper):
    """
    Async company site crawler that discovers ALL emails across
    multiple pages of a company's website.
    """

    def __init__(self, settings: dict, logger, crawl_settings: dict = None):
        super().__init__(settings, logger)
        self.crawl_settings = crawl_settings or {}
        self.max_pages = self.crawl_settings.get("max_pages_per_company", 20)
        self.discover_links = self.crawl_settings.get("discover_internal_links", True)
        self.parse_sitemap = self.crawl_settings.get("parse_sitemap", True)

    async def find_all_emails(self, website: str, page) -> dict:
        """
        Crawl a company website and extract ALL emails.

        Returns:
            {
                "emails": [{"email": str, "priority_score": int, "page_found_on": str, "found_via_mailto": bool}, ...],
                "pages_crawled": int,
                "classification_html": [str, ...]  # HTML from key pages for classification
            }
        """
        if not website:
            return {"emails": [], "pages_crawled": 0, "classification_html": []}

        website = website.rstrip("/")
        base_domain = urlparse(website).netloc.lower()

        all_emails = {}  # email_normalized -> email_dict (dedup by email)
        pages_crawled = 0
        classification_html = []
        visited_urls = set()

        # Build initial crawl queue from predefined paths
        crawl_queue = []
        for path in CANDIDATE_PATHS:
            url = f"{website}/{path}" if path else website
            crawl_queue.append(url)

        # Try sitemap.xml
        if self.parse_sitemap:
            sitemap_urls = await self._parse_sitemap(page, website)
            crawl_queue.extend(sitemap_urls)

        # Discovered internal links (added during crawling)
        discovered_links = []

        # Phase 1: Crawl predefined paths
        for url in crawl_queue:
            if pages_crawled >= self.max_pages:
                break
            url_normalized = self._normalize_url(url)
            if url_normalized in visited_urls:
                continue
            visited_urls.add(url_normalized)

            html = await self.fetch_page_html(page, url)
            if not html:
                continue

            pages_crawled += 1
            soup = BeautifulSoup(html, "html.parser")

            # Store HTML for classification (homepage and about pages)
            if pages_crawled <= 3:
                classification_html.append(html)

            # Extract emails from this page
            page_emails = self._extract_emails_from_soup(soup, url, base_domain)
            for email_dict in page_emails:
                normalized = email_dict["email"].strip().lower()
                if normalized not in all_emails:
                    all_emails[normalized] = email_dict
                else:
                    # Keep the higher priority version
                    if email_dict["priority_score"] > all_emails[normalized]["priority_score"]:
                        all_emails[normalized] = email_dict

            # Discover internal links for Phase 2
            if self.discover_links:
                new_links = self._discover_internal_links(soup, website, base_domain)
                for link in new_links:
                    link_normalized = self._normalize_url(link)
                    if link_normalized not in visited_urls:
                        discovered_links.append(link)

        # Phase 2: Crawl discovered internal links (prioritized by keyword relevance)
        discovered_links = self._prioritize_links(discovered_links)
        for url in discovered_links:
            if pages_crawled >= self.max_pages:
                break
            url_normalized = self._normalize_url(url)
            if url_normalized in visited_urls:
                continue
            visited_urls.add(url_normalized)

            html = await self.fetch_page_html(page, url)
            if not html:
                continue

            pages_crawled += 1
            soup = BeautifulSoup(html, "html.parser")

            page_emails = self._extract_emails_from_soup(soup, url, base_domain)
            for email_dict in page_emails:
                normalized = email_dict["email"].strip().lower()
                if normalized not in all_emails:
                    all_emails[normalized] = email_dict
                else:
                    if email_dict["priority_score"] > all_emails[normalized]["priority_score"]:
                        all_emails[normalized] = email_dict

        self.logger.info(
            f"Crawled {pages_crawled} pages on {website}, "
            f"found {len(all_emails)} unique emails"
        )

        return {
            "emails": list(all_emails.values()),
            "pages_crawled": pages_crawled,
            "classification_html": classification_html,
        }

    def _extract_emails_from_soup(self, soup: BeautifulSoup, page_url: str,
                                   base_domain: str) -> list:
        """
        Extract all emails from a parsed page using both mailto links and regex.
        Returns a list of email dicts with priority scores.
        """
        found = []
        seen_on_page = set()

        # ── Method 1: mailto: links (highest confidence) ─────────
        mailto_links = soup.select("a[href^='mailto:']")
        for link in mailto_links:
            raw = link["href"].replace("mailto:", "").split("?")[0].strip()
            if raw and EMAIL_REGEX.match(raw) and not is_excluded_email(raw):
                normalized = raw.strip().lower()
                if normalized not in seen_on_page:
                    seen_on_page.add(normalized)
                    found.append({
                        "email": raw.strip(),
                        "priority_score": score_email(raw, page_url, found_via_mailto=True),
                        "page_found_on": page_url,
                        "found_via_mailto": True,
                    })

        # ── Method 2: Footer/Header elements ─────────────────────
        for zone_tag in ["footer", "header", "nav"]:
            for zone in soup.find_all(zone_tag):
                text = zone.get_text(" ", strip=True)
                matches = EMAIL_REGEX.findall(text)
                for email in matches:
                    normalized = email.strip().lower()
                    if normalized not in seen_on_page and not is_excluded_email(email):
                        seen_on_page.add(normalized)
                        found.append({
                            "email": email.strip(),
                            "priority_score": score_email(email, page_url, found_via_mailto=False),
                            "page_found_on": page_url,
                            "found_via_mailto": False,
                        })

        # ── Method 3: Regex over entire visible text ─────────────
        text = soup.get_text(" ", strip=True)
        matches = EMAIL_REGEX.findall(text)
        for email in matches:
            normalized = email.strip().lower()
            if normalized not in seen_on_page and not is_excluded_email(email):
                seen_on_page.add(normalized)
                found.append({
                    "email": email.strip(),
                    "priority_score": score_email(email, page_url, found_via_mailto=False),
                    "page_found_on": page_url,
                    "found_via_mailto": False,
                })

        # ── Method 4: HTML source (catches obfuscated/hidden emails) ──
        raw_html = str(soup)
        html_matches = EMAIL_REGEX.findall(raw_html)
        for email in html_matches:
            normalized = email.strip().lower()
            # Filter out CSS/JS artifact emails (e.g., "font@face", "keyframes@media")
            if normalized not in seen_on_page and not is_excluded_email(email):
                # Sanity check: domain should have at least one dot and reasonable TLD
                parts = email.split("@")
                if len(parts) == 2 and "." in parts[1] and len(parts[1]) >= 4:
                    seen_on_page.add(normalized)
                    found.append({
                        "email": email.strip(),
                        "priority_score": score_email(email, page_url, found_via_mailto=False),
                        "page_found_on": page_url,
                        "found_via_mailto": False,
                    })

        return found

    def _discover_internal_links(self, soup: BeautifulSoup, base_url: str,
                                  base_domain: str) -> list:
        """
        Extract internal links from a page that might contain email addresses.
        Only returns same-domain links.
        """
        links = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()

            # Skip anchors, javascript, mailto, tel
            if href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            # Resolve relative URLs
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            # Must be same domain
            if parsed.netloc.lower() != base_domain:
                continue

            # Skip file downloads
            path_lower = parsed.path.lower()
            if any(path_lower.endswith(ext) for ext in SKIP_EXTENSIONS):
                continue

            # Clean URL (remove fragments and query params for dedup)
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
            links.append(clean)

        return list(set(links))

    def _prioritize_links(self, links: list) -> list:
        """
        Sort discovered links so that career/jobs/contact pages are crawled first.
        Links containing priority keywords get sorted to the top.
        """
        def priority_key(url):
            path = urlparse(url).path.lower()
            for keyword in PRIORITY_LINK_KEYWORDS:
                if keyword in path:
                    return 0  # High priority
            return 1  # Normal priority

        return sorted(links, key=priority_key)

    async def _parse_sitemap(self, page, website: str) -> list:
        """
        Try to parse sitemap.xml for additional URLs to crawl.
        Returns a list of URLs from the sitemap.
        """
        sitemap_url = f"{website}/sitemap.xml"
        urls = []
        try:
            html = await self.fetch_page_html(page, sitemap_url)
            if not html:
                return urls

            soup = BeautifulSoup(html, "xml")
            loc_tags = soup.find_all("loc")
            for loc in loc_tags:
                url = loc.get_text(strip=True)
                if url:
                    # Only include pages likely to contain emails
                    path_lower = urlparse(url).path.lower()
                    if any(kw in path_lower for kw in PRIORITY_LINK_KEYWORDS):
                        urls.append(url)

            if urls:
                self.logger.info(f"Found {len(urls)} relevant URLs in sitemap for {website}")

        except Exception as e:
            self.logger.debug(f"Sitemap parsing failed for {website}: {e}")

        return urls[:10]  # Cap sitemap URLs to avoid bloat

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize a URL for deduplication (lowercase, no trailing slash, no fragment)."""
        parsed = urlparse(url.lower())
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


async def crawl_companies_async(companies: list, settings: dict, crawl_settings: dict,
                                 logger, db, run_id: int):
    """
    Crawl multiple companies concurrently for email discovery.

    Args:
        companies: List of dicts with 'company_id', 'company_name', 'website'.
        settings: Request settings from config.
        crawl_settings: Crawl-specific settings from config.
        logger: Logger instance.
        db: ScraperDB instance.
        run_id: Current run ID for tracking new emails.

    Returns:
        dict of company_id -> crawl results
    """
    from utils.email_validator_util import check_email

    concurrent = crawl_settings.get("concurrent_companies", 5)
    semaphore = asyncio.Semaphore(concurrent)
    results = {}

    async with async_playwright() as p:
        # Launch a single Chromium browser instance to be shared across contexts
        browser = await p.chromium.launch(headless=True)

        async def crawl_one(company_info):
            async with semaphore:
                company_id = company_info["company_id"]
                company_name = company_info["company_name"]
                website = company_info["website"]

                if not website:
                    results[company_id] = {"emails": [], "pages_crawled": 0}
                    return

                logger.info(f"Crawling emails for: {company_name} ({website})")

                # Create separate context and page to isolate states
                context = await browser.new_context(user_agent=settings.get("user_agent"))
                page = await context.new_page()

                try:
                    scraper = CompanySiteScraper(settings, logger, crawl_settings)
                    crawl_result = await scraper.find_all_emails(website, page)

                    # Validate and store each email
                    validated_emails = []
                    for email_dict in crawl_result["emails"]:
                        validation = check_email(email_dict["email"], website)
                        email_dict["mx_status"] = validation["status"]
                        email_dict["email"] = validation["email"] or email_dict["email"]
                        validated_emails.append(email_dict)

                    # Store in database
                    new_count = db.add_emails_batch(company_id, validated_emails, run_id)
                    logger.info(
                        f"  {company_name}: {len(validated_emails)} emails found, "
                        f"{new_count} new"
                    )

                    # Classify company from crawled HTML
                    if crawl_result["classification_html"]:
                        category = classify_from_multiple_pages(
                            crawl_result["classification_html"], company_name
                        )
                        db.update_company_category(company_id, category)
                        logger.info(f"  {company_name}: classified as {category}")

                    results[company_id] = crawl_result

                except Exception as e:
                    logger.error(f"Error crawling {company_name}: {e}")
                    results[company_id] = {"emails": [], "pages_crawled": 0}
                finally:
                    await context.close()

        # Create tasks for all companies
        tasks = [crawl_one(c) for c in companies]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Close the shared browser
        await browser.close()

    return results
