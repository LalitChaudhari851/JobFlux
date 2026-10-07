"""
website_resolver.py
Resolves a company's official website using Bing Search with multi-signal validation.

Improvements over the original:
- Multi-signal validation (title, meta description, Organization schema, domain similarity)
- Fallback search queries when first query fails
- Search engine email discovery when crawling finds no emails
- Stricter rejection of mismatched domains
"""

import base64
import urllib.parse
import time
import random
import re
import json
from bs4 import BeautifulSoup
import tldextract

# Social media, directories, search engines, and portal domains to exclude
EXCLUDED_DOMAINS = {
    "linkedin.com", "glassdoor.com", "indeed.com", "internshala.com", "naukri.com",
    "wellfound.com", "facebook.com", "twitter.com", "instagram.com", "github.com",
    "youtube.com", "wikipedia.org", "crunchbase.com", "ambitionbox.com", "google.com",
    "duckduckgo.com", "pinterest.com", "medium.com", "jobspire.com", "shine.com",
    "bing.com", "yahoo.com", "reddit.com", "quora.com", "tiktok.com", "x.com",
    "threads.net", "snapchat.com", "tumblr.com", "flickr.com",
}


def decode_bing_url(url: str) -> str:
    """Decodes Bing's redirection URL parameter 'u' which contains Base64 encoded target."""
    try:
        parsed = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed.query)
        if "u" in query_params:
            u_val = query_params["u"][0]
            # Strip the 'a1' prefix commonly added by Bing
            if u_val.startswith("a1"):
                u_val = u_val[2:]
            # Standard Base64 padding
            padding = len(u_val) % 4
            if padding:
                u_val += "=" * (4 - padding)
            decoded = base64.b64decode(u_val).decode("utf-8", errors="ignore")
            return decoded
    except Exception:
        pass
    return url


def clean_company_name_keywords(name: str) -> list:
    """Extracts significant keywords from a company name for domain matching."""
    # Convert to lowercase and remove common corporate designators and punctuation
    cleaned = re.sub(
        r"\b(private|limited|ltd|llp|solutions|technologies|services|group|india|us|advocate|advisors|fze|inc|co|corp|corporation|pvt)\b",
        "",
        name.lower()
    )
    # Find all alphanumeric sequences of length >= 3
    words = re.findall(r"\b[a-z0-9]{3,}\b", cleaned)
    return words


def _compute_domain_similarity(company_name: str, domain: str) -> float:
    """
    Compute a similarity score (0-1) between the company name and domain.
    Higher = more likely to be the correct match.
    """
    name_lower = company_name.strip().lower()
    domain_lower = domain.lower()

    # Extract just the domain name part (without TLD)
    ext = tldextract.extract(domain_lower)
    domain_name = ext.domain

    # Exact match or containment
    name_cleaned = re.sub(r"[^a-z0-9]", "", name_lower)
    domain_cleaned = re.sub(r"[^a-z0-9]", "", domain_name)

    if name_cleaned == domain_cleaned:
        return 1.0
    if name_cleaned in domain_cleaned or domain_cleaned in name_cleaned:
        return 0.8

    # Check if all keywords appear in domain
    keywords = clean_company_name_keywords(company_name)
    if keywords:
        matched = sum(1 for kw in keywords if kw in domain_cleaned)
        return matched / len(keywords) * 0.7

    return 0.0


def _validate_website_content(page, url: str, company_name: str, logger) -> float:
    """
    Fetch the candidate website and validate it actually belongs to the company.
    Returns a confidence score (0-1).
    """
    confidence = 0.0
    company_keywords = clean_company_name_keywords(company_name)

    try:
        page.goto(url, timeout=10000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # Signal 1: Check <title> tag
        title_tag = soup.find("title")
        if title_tag:
            title_text = title_tag.get_text(strip=True).lower()
            if any(kw in title_text for kw in company_keywords):
                confidence += 0.3

        # Signal 2: Check <meta name="description">
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            desc_text = meta_desc["content"].lower()
            if any(kw in desc_text for kw in company_keywords):
                confidence += 0.2

        # Signal 3: Check Organization schema (JSON-LD)
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                # Handle both single objects and arrays
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") in ("Organization", "Corporation", "LocalBusiness"):
                        org_name = item.get("name", "").lower()
                        if any(kw in org_name for kw in company_keywords):
                            confidence += 0.3
                            break
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue

        # Signal 4: Check H1 tags
        for h1 in soup.find_all("h1"):
            h1_text = h1.get_text(strip=True).lower()
            if any(kw in h1_text for kw in company_keywords):
                confidence += 0.1
                break

    except Exception as e:
        logger.debug(f"Website validation failed for {url}: {e}")

    return min(confidence, 1.0)


# Global tracker flags to detect rate-limits or blocks by Bing and fail-fast
BING_BLOCKED_FLAG = False
BING_FAIL_COOLDOWN_COUNT = 0


def resolve_website_via_search(company_name: str, page, logger) -> str:
    """
    Search Bing for the company's official website with multi-signal validation.
    Returns the first matching URL that passes validation, or None.
    """
    global BING_BLOCKED_FLAG, BING_FAIL_COOLDOWN_COUNT

    if BING_BLOCKED_FLAG:
        logger.debug(f"Skipping Bing search for '{company_name}' — Bing search is currently disabled/blocked.")
        return None

    if not company_name or company_name.lower().strip() == "na":
        return None

    # Try multiple search queries (fallback strategy)
    queries = [
        f"{company_name}",
        f'"{company_name}" official website',
        f"{company_name} careers",
    ]

    company_keywords = clean_company_name_keywords(company_name)

    for query_idx, query in enumerate(queries):
        # Implement a randomized delay to avoid rate-limiting/blocking by Bing
        delay = random.uniform(2.0, 4.0)
        time.sleep(delay)

        encoded_query = urllib.parse.quote_plus(query)
        search_url = f"https://www.bing.com/search?q={encoded_query}"

        logger.info(f"Searching Bing for: {query}")
        try:
            response = page.goto(search_url, timeout=15000)
            if response and response.status != 200:
                logger.warning(f"Bing returned HTTP status {response.status} for '{company_name}'")
                continue

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            results = soup.select("li.b_algo")

            for res in results:
                link_el = res.select_one("h2 a")
                if not link_el or not link_el.has_attr("href"):
                    continue

                href = link_el["href"]

                # If it's a Bing redirection link, decode it
                if "bing.com/ck/a" in href:
                    href = decode_bing_url(href)

                ext = tldextract.extract(href)
                domain = f"{ext.domain}.{ext.suffix}".lower()

                if domain in EXCLUDED_DOMAINS or not ext.suffix:
                    continue

                # ── Multi-signal domain validation ───────────────
                # Signal 1: Domain keyword matching (fast, no extra requests)
                domain_similarity = _compute_domain_similarity(company_name, domain)

                if domain_similarity < 0.3 and company_keywords:
                    # Domain doesn't match well — skip unless it's the first query
                    # and we haven't tried anything else yet
                    if query_idx == 0:
                        # For first query, also check if search result title matches
                        result_title = link_el.get_text(strip=True).lower()
                        if not any(kw in result_title for kw in company_keywords):
                            continue
                    else:
                        continue

                # Standardize URL to scheme + domain (e.g., https://example.com)
                parsed_dest = urllib.parse.urlparse(href)
                company_url = f"{parsed_dest.scheme}://{parsed_dest.netloc}"

                # Signal 2: For weak domain matches, validate by fetching the page
                if domain_similarity < 0.6:
                    content_confidence = _validate_website_content(
                        page, company_url, company_name, logger
                    )
                    total_confidence = (domain_similarity + content_confidence) / 2
                    if total_confidence < 0.2:
                        logger.debug(
                            f"Rejected {company_url} for '{company_name}' "
                            f"(domain_sim={domain_similarity:.2f}, content={content_confidence:.2f})"
                        )
                        continue

                logger.info(f"Resolved website for '{company_name}': {company_url}")
                # Reset error cooldown on success
                BING_FAIL_COOLDOWN_COUNT = max(0, BING_FAIL_COOLDOWN_COUNT - 1)
                return company_url

        except Exception as e:
            logger.error(f"Error resolving website for '{company_name}': {e}")
            err_msg = str(e).lower()
            # If we hit connection issues (rate limits/network block), fail fast
            if any(term in err_msg for term in ("connection_closed", "connection_reset", "connection_refused", "name_not_resolved")):
                BING_FAIL_COOLDOWN_COUNT += 1
                if BING_FAIL_COOLDOWN_COUNT >= 3:
                    BING_BLOCKED_FLAG = True
                    logger.warning("Bing Search appears to be blocked or rate-limited. Disabling Bing searches for the rest of this run to save time.")
                break  # Skip the other queries for this company since the connection is blocked

    return None


def search_for_emails_via_bing(company_name: str, company_domain: str, page, logger) -> list:
    """
    When crawling fails to find emails, search Bing for publicly listed emails.
    
    Searches:
    - site:company.com "@company.com"
    - site:company.com careers email
    
    Returns a list of email strings found in search results snippets.
    """
    global BING_BLOCKED_FLAG, BING_FAIL_COOLDOWN_COUNT

    if BING_BLOCKED_FLAG:
        return []

    if not company_domain:
        return []

    ext = tldextract.extract(company_domain)
    domain = f"{ext.domain}.{ext.suffix}"

    email_regex = re.compile(r"[a-zA-Z0-9._%+-]+@" + re.escape(domain))

    queries = [
        f'site:{domain} "@{domain}"',
        f'site:{domain} careers email contact',
        f'"{company_name}" email contact "@{domain}"',
    ]

    found_emails = set()

    for query in queries:
        delay = random.uniform(2.0, 4.0)
        time.sleep(delay)

        encoded_query = urllib.parse.quote_plus(query)
        search_url = f"https://www.bing.com/search?q={encoded_query}"

        try:
            response = page.goto(search_url, timeout=15000)
            if response and response.status != 200:
                continue

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            # Extract emails from search result snippets
            text = soup.get_text(" ", strip=True)
            matches = email_regex.findall(text)
            for email in matches:
                found_emails.add(email.strip().lower())

        except Exception as e:
            logger.debug(f"Email search failed for {company_name}: {e}")
            err_msg = str(e).lower()
            if any(term in err_msg for term in ("connection_closed", "connection_reset", "connection_refused", "name_not_resolved")):
                BING_FAIL_COOLDOWN_COUNT += 1
                if BING_FAIL_COOLDOWN_COUNT >= 3:
                    BING_BLOCKED_FLAG = True
                    logger.warning("Bing Search appears to be blocked or rate-limited. Disabling Bing searches for the rest of this run to save time.")
                break

        if found_emails:
            break  # Found some — no need to try more queries

    if found_emails:
        logger.info(f"Search engine discovered {len(found_emails)} emails for {company_name}")

    return list(found_emails)
