"""
main.py
Entry point. Runs each enabled portal scraper, normalizes posted dates,
finds + validates company emails using async concurrent crawling,
stores everything in SQLite for incremental tracking, and exports
multiple CSV/Excel output files.

Usage:
    python main.py
"""

import json
import logging
import os
import asyncio
from datetime import datetime

import pandas as pd

from scrapers.internshala import InternshalaScraper
from scrapers.naukri import NaukriScraper
from scrapers.wellfound import WellfoundScraper
from scrapers.indeed import IndeedScraper
from scrapers.yc import YCScraper
from scrapers.google_jobs import GoogleJobsScraper
from scrapers.company_site import crawl_companies_async
from utils.date_parser import normalize_posted_date, is_within_window
from utils.email_validator_util import check_email
from utils.email_scorer import score_email
from utils.db import ScraperDB
from utils.website_resolver import resolve_website_via_search, search_for_emails_via_bing


def load_config(path="config.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def setup_logger(log_path: str) -> logging.Logger:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logger = logging.getLogger("scraper")
    logger.setLevel(logging.INFO)
    # Avoid adding duplicate handlers on re-runs
    if not logger.handlers:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        ch = logging.StreamHandler()
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh.setFormatter(fmt)
        ch.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger


def guess_company_website(company_name: str, seed_companies: list) -> str:
    """Look up website from seed list; otherwise return None (no guessing)."""
    for c in seed_companies:
        if c["name"].strip().lower() == company_name.strip().lower():
            return c["website"]
    return None


def run(args=None):
    config = load_config()
    settings = config["request_settings"]
    crawl_settings = config.get("crawl_settings", {})
    email_settings = config.get("email_settings", {})
    logger = setup_logger(config["output"]["log_path"])
    scrape_time = datetime.now()

    # ── Initialize database ──────────────────────────────────────
    db_path = config["output"].get("db_path", "output/scraper.db")
    db = ScraperDB(db_path)

    # Import legacy cache if database is empty and cache exists
    cache_path = os.path.join(os.path.dirname(config["output"]["excel_path"]), "company_cache.json")
    db_stats = db.get_total_counts()
    if db_stats["total_companies"] == 0 and os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                legacy_cache = json.load(f)
            if legacy_cache:
                # Create a migration run
                migration_run = db.start_run()
                db.import_from_cache(legacy_cache, migration_run)
                db.complete_run(migration_run, {
                    "new_companies": len(legacy_cache),
                    "new_emails": sum(1 for v in legacy_cache.values() if v.get("email")),
                    "total_companies": len(legacy_cache),
                    "total_emails": sum(1 for v in legacy_cache.values() if v.get("email")),
                })
                logger.info(f"Migrated {len(legacy_cache)} companies from legacy cache to SQLite")
        except Exception as e:
            logger.warning(f"Error importing legacy cache: {e}")

    # Start this scraping run
    run_id = db.start_run()
    new_companies_count = 0
    new_emails_count = 0

    # ── Phase 1: Scrape Portal Listings ──────────────────────────
    all_listings = []

    portal_map = {
        "internshala": InternshalaScraper,
        "naukri": NaukriScraper,
        "wellfound": WellfoundScraper,
        "indeed": IndeedScraper,
        "yc": YCScraper,
        "google_jobs": GoogleJobsScraper,
    }

    portals_to_run = dict(config.get("portals", {}))
    keywords_to_search = list(config.get("search_keywords", []))

    if args:
        if args.portal:
            target_portal = args.portal.lower()
            portals_to_run = {p: (p.lower() == target_portal) for p in portal_map}
        if args.test:
            keywords_to_search = keywords_to_search[:1]
            if not args.portal:
                portals_to_run = {"internshala": True}
        elif args.limit_keywords:
            keywords_to_search = keywords_to_search[:args.limit_keywords]

    for portal_name, enabled in portals_to_run.items():
        if not enabled:
            continue
        scraper_cls = portal_map.get(portal_name)
        if not scraper_cls:
            continue
        logger.info(f"--- Running {portal_name} scraper ---")
        scraper = scraper_cls(settings, logger)
        try:
            listings = scraper.scrape(keywords_to_search, config["locations"])
            all_listings.extend(listings)
        except Exception as e:
            logger.error(f"{portal_name} scraper failed entirely: {e}")

    logger.info(f"Total raw listings collected: {len(all_listings)}")

    # ── Phase 2: Normalize Dates + Filter ────────────────────────
    window_days = config.get("recency_window_days", 7)
    for listing in all_listings:
        parsed = normalize_posted_date(listing.get("raw_posted_text"), scrape_time)
        listing["normalized_posted_date"] = parsed["normalized_date"]
        listing["recency_flag"] = parsed["recency_flag"]

    filtered_listings = [
        l for l in all_listings
        if is_within_window(l["normalized_posted_date"], scrape_time, window_days)
    ]
    logger.info(f"Listings within {window_days}-day window: {len(filtered_listings)}")

    # ── Phase 3: Deduplicate Listings ────────────────────────────
    seen = set()
    deduped = []
    for l in filtered_listings:
        key = (l["company_name"].strip().lower(), l["job_title"].strip().lower(), l["source_portal"])
        if key not in seen:
            seen.add(key)
            deduped.append(l)
    logger.info(f"Listings after dedup: {len(deduped)}")

    # Sort newest first (unknown dates sink to bottom)
    deduped.sort(key=lambda l: l["normalized_posted_date"] or datetime.min, reverse=True)

    # ── Phase 4: Register Companies in Database ──────────────────
    unique_companies = {l["company_name"] for l in deduped}
    company_db_ids = {}  # company_name -> (company_id, is_new)

    for company_name in unique_companies:
        company_id, is_new = db.get_or_create_company(company_name)
        company_db_ids[company_name] = (company_id, is_new)
        if is_new:
            new_companies_count += 1

    logger.info(
        f"Companies: {len(unique_companies)} total, "
        f"{new_companies_count} new this run"
    )

    # ── Phase 5: Resolve Websites ────────────────────────────────
    from playwright.sync_api import sync_playwright

    logger.info("Resolving websites for companies...")
    resolved_websites = {}
    companies_to_resolve = []

    for company_name in unique_companies:
        company_id, is_new = company_db_ids[company_name]

        # Check seed list first
        website = guess_company_website(company_name, config["seed_companies"])
        if website and website.lower() != "na":
            resolved_websites[company_name] = website
            db.update_company_website(company_id, website)
            continue

        # Check database for existing website
        stored_website = db.get_company_website(company_id)
        if stored_website:
            resolved_websites[company_name] = stored_website
            continue

        companies_to_resolve.append(company_name)

    if args and args.test and companies_to_resolve:
        companies_to_resolve = companies_to_resolve[:2]

    if companies_to_resolve:
        logger.info(f"Resolving {len(companies_to_resolve)} websites via Bing...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=settings.get("user_agent"))

            for company_name in companies_to_resolve:
                search_page = context.new_page()
                try:
                    website = resolve_website_via_search(company_name, search_page, logger)
                finally:
                    search_page.close()

                resolved_websites[company_name] = website
                if website:
                    company_id, _ = company_db_ids[company_name]
                    db.update_company_website(company_id, website)

            context.close()
            browser.close()
    else:
        logger.info("All websites resolved from cache/seed/database.")

    # ── Phase 6: Async Email Discovery ───────────────────────────
    # Identify companies that need email crawling
    companies_to_crawl = []
    for company_name in unique_companies:
        company_id, is_new = company_db_ids[company_name]
        website = resolved_websites.get(company_name)

        if not website:
            continue

        # Skip companies that already have valid emails (unless they're new)
        if not is_new and db.has_valid_emails(company_id):
            logger.info(f"Skipping {company_name} — already has valid emails")
            continue

        companies_to_crawl.append({
            "company_id": company_id,
            "company_name": company_name,
            "website": website,
        })

    if args and args.test and companies_to_crawl:
        companies_to_crawl = companies_to_crawl[:2]

    if companies_to_crawl:
        logger.info(f"Crawling {len(companies_to_crawl)} companies for emails (async)...")
        asyncio.run(
            crawl_companies_async(
                companies_to_crawl, settings, crawl_settings, logger, db, run_id
            )
        )
    else:
        logger.info("No new companies to crawl for emails.")

    # ── Phase 7: Search Engine Fallback ──────────────────────────
    if crawl_settings.get("search_fallback_enabled", True):
        # Find companies that still have no emails after crawling
        companies_without_emails = []
        for company_name in unique_companies:
            company_id, _ = company_db_ids[company_name]
            if not db.has_valid_emails(company_id):
                website = resolved_websites.get(company_name)
                if website:
                    companies_without_emails.append((company_name, company_id, website))

        if args and args.test and companies_without_emails:
            companies_without_emails = companies_without_emails[:2]

        if companies_without_emails:
            logger.info(
                f"Search engine fallback for {len(companies_without_emails)} companies..."
            )
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=settings.get("user_agent"))
                search_page = context.new_page()

                for company_name, company_id, website in companies_without_emails:
                    try:
                        found_emails = search_for_emails_via_bing(
                            company_name, website, search_page, logger
                        )
                        for email_str in found_emails:
                            validation = check_email(email_str, website)
                            priority = score_email(email_str)
                            db.add_email(
                                company_id=company_id,
                                email=validation["email"] or email_str,
                                priority_score=priority,
                                mx_status=validation["status"],
                                page_found_on="Bing Search",
                                run_id=run_id,
                            )
                    except Exception as e:
                        logger.error(f"Search fallback failed for {company_name}: {e}")

                search_page.close()
                context.close()
                browser.close()

    # ── Phase 7.5: Extract Emails from Job Listings ──────────────
    logger.info("Extracting emails from job description snippets...")
    import re
    from utils.email_scorer import score_email, is_excluded_email
    EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    
    listing_emails_extracted = 0
    for l in deduped:
        desc = l.get("description_snippet") or ""
        title = l.get("job_title") or ""
        combined_text = f"{title} {desc}"
        
        company_name = l.get("company_name")
        if company_name:
            found_emails = EMAIL_REGEX.findall(combined_text)
            if found_emails:
                company_id, _ = company_db_ids[company_name]
                website = resolved_websites.get(company_name) or db.get_company_website(company_id)
                for email_str in found_emails:
                    email_str = email_str.strip()
                    if not is_excluded_email(email_str):
                        validation = check_email(email_str, website)
                        priority = score_email(email_str)
                        is_new_email = db.add_email(
                            company_id=company_id,
                            email=validation["email"] or email_str,
                            priority_score=priority,
                            mx_status=validation["status"],
                            page_found_on=f"Job Listing: {l.get('job_title')} ({l.get('source_portal')})",
                            run_id=run_id,
                        )
                        if is_new_email:
                            listing_emails_extracted += 1
                            
    logger.info(f"Extracted {listing_emails_extracted} new emails from job listing descriptions.")

    # ── Phase 8: Count New Emails ────────────────────────────────
    new_contacts = db.get_new_contacts(run_id)
    new_emails_count = len(new_contacts)

    # ── Phase 9: Complete Run ────────────────────────────────────
    total_stats = db.get_total_counts()
    db.complete_run(run_id, {
        "new_companies": new_companies_count,
        "new_emails": new_emails_count,
        "total_companies": total_stats["total_companies"],
        "total_emails": total_stats["total_emails"],
    })

    # ── Phase 10: Export Outputs ─────────────────────────────────
    csv_dir = config["output"].get("csv_dir", "output/")
    os.makedirs(csv_dir, exist_ok=True)

    # Standardized column names for all CSVs
    CSV_COLUMNS = [
        "company", "website", "email", "priority_score",
        "mx_status", "page_found_on", "category", "status"
    ]
    COLUMN_RENAME = {
        "company": "Company",
        "website": "Website",
        "email": "Email",
        "priority_score": "Priority Score",
        "mx_status": "MX Status",
        "page_found_on": "Page Found",
        "category": "Category",
        "status": "New/Existing",
    }

    def save_csv(data: list, filename: str, description: str):
        """Helper to save a list of dicts as a CSV with standardized columns."""
        if not data:
            df = pd.DataFrame(columns=list(COLUMN_RENAME.values()))
        else:
            df = pd.DataFrame(data)
            # Ensure all expected columns exist
            for col in CSV_COLUMNS:
                if col not in df.columns:
                    df[col] = None
            df = df[[c for c in CSV_COLUMNS if c in df.columns]]
            df = df.rename(columns=COLUMN_RENAME)
        filepath = os.path.join(csv_dir, filename)
        df.to_csv(filepath, index=False)
        logger.info(f"Exported {description}: {filepath} ({len(df)} rows)")
        return df

    # 1. company_contacts.csv — All companies with their best email
    all_contacts = db.get_all_contacts()
    contacts_df = save_csv(all_contacts, "company_contacts.csv", "All company contacts")

    # 2. new_company_contacts.csv — Only new companies/emails from this run
    new_data = db.get_new_contacts(run_id)
    save_csv(new_data, "new_company_contacts.csv", "New contacts this run")

    # 3. high_priority_contacts.csv — Emails with score >= 75
    min_score = email_settings.get("min_priority_score", 25)
    high_priority = db.get_high_priority_contacts(min_score=75)
    save_csv(high_priority, "high_priority_contacts.csv", "High priority contacts")

    # 4. ai_companies.csv — Companies classified as AI/ML
    ai_companies = db.get_ai_companies()
    save_csv(ai_companies, "ai_companies.csv", "AI/ML companies")

    # 5. internship_companies.csv — All companies with internship listings
    internship_companies = db.get_internship_companies()
    save_csv(internship_companies, "internship_companies.csv", "Internship companies")

    # 6. all_emails.csv — Every single discovered email
    all_emails = db.get_all_emails()
    save_csv(all_emails, "all_emails.csv", "All discovered emails")

    # Map company names to their best contacts to link them in listings
    contacts_lookup = {}
    for c in all_contacts:
        comp = c.get("company")
        if comp:
            contacts_lookup[comp.strip().lower()] = c

    for l in deduped:
        comp = l.get("company_name", "")
        c_info = contacts_lookup.get(comp.strip().lower())
        if c_info:
            l["company_website"] = c_info.get("website")
            l["company_email"] = c_info.get("email")
            l["email_priority_score"] = c_info.get("priority_score")
            l["email_mx_status"] = c_info.get("mx_status")
            l["company_category"] = c_info.get("category")
        else:
            website = resolved_websites.get(comp)
            if website:
                l["company_website"] = website
            else:
                l["company_website"] = None
            l["company_email"] = None
            l["email_priority_score"] = None
            l["email_mx_status"] = None
            l["company_category"] = None

    # ── Phase 11: Export Excel (preserving original format) ──────
    listings_df = pd.DataFrame(deduped) if deduped else pd.DataFrame()

    # Reorder columns so apply link is prominent
    preferred_listing_cols = [
        "source_portal",
        "company_name",
        "job_title",
        "company_website",
        "company_email",
        "email_priority_score",
        "email_mx_status",
        "application_link",
        "location",
        "recency_flag",
        "normalized_posted_date",
        "raw_posted_text",
        "description_snippet",
        "search_keyword",
        "company_category",
    ]
    if not listings_df.empty:
        listing_cols = [c for c in preferred_listing_cols if c in listings_df.columns]
        listing_cols += [c for c in listings_df.columns if c not in listing_cols]
        listings_df = listings_df[listing_cols]

    # Export job listings as CSV for easier reading in code editors
    try:
        job_listings_csv_path = os.path.join(csv_dir, "job_listings.csv")
        listings_df.to_csv(job_listings_csv_path, index=False)
        logger.info(f"Exported Job Listings CSV: {job_listings_csv_path} ({len(listings_df)} rows)")
    except Exception as e:
        logger.warning(f"Failed to export Job Listings CSV: {e}")

    # Build contact DataFrames for Excel
    valid_contacts_df = pd.DataFrame(
        [c for c in all_contacts if c.get("mx_status") == "Valid - MX confirmed"]
    ) if all_contacts else pd.DataFrame()

    rejected_contacts_df = pd.DataFrame(
        [c for c in all_contacts if c.get("mx_status") != "Valid - MX confirmed"]
    ) if all_contacts else pd.DataFrame()

    new_contacts_df = pd.DataFrame(new_data) if new_data else pd.DataFrame()

    # Build summary
    summary_data = {
        "Metric": [
            "Scrape Time",
            "Run ID",
            "Total Raw Listings",
            "After Date Filter",
            "After Dedup",
            "Unique Companies (This Run)",
            "New Companies (This Run)",
            "Websites Resolved",
            "Valid Emails Found (Total)",
            "New Emails (This Run)",
            "High Priority Emails (≥75)",
            "AI/ML Companies",
            "Portals Scraped",
            "Total Companies (All Runs)",
            "Total Verified Emails (All Runs)",
        ],
        "Value": [
            str(scrape_time),
            run_id,
            len(all_listings),
            len(filtered_listings),
            len(deduped),
            len(unique_companies),
            new_companies_count,
            sum(1 for v in resolved_websites.values() if v),
            total_stats["verified_emails"],
            new_emails_count,
            len(high_priority),
            len(ai_companies),
            ", ".join(k for k, v in config["portals"].items() if v),
            total_stats["total_companies"],
            total_stats["total_emails"],
        ],
    }
    summary_df = pd.DataFrame(summary_data)

    # Export Excel
    excel_path = config["output"]["excel_path"]
    os.makedirs(os.path.dirname(excel_path), exist_ok=True)
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        listings_df.to_excel(writer, sheet_name="Job Listings", index=False)
        if not valid_contacts_df.empty:
            valid_contacts_df.to_excel(writer, sheet_name="Company Contacts", index=False)
        if not rejected_contacts_df.empty:
            rejected_contacts_df.to_excel(writer, sheet_name="Rejected_Unverified", index=False)
        if not new_contacts_df.empty:
            new_contacts_df.to_excel(writer, sheet_name="New This Run", index=False)

    # ── Phase 12: Print Summary ──────────────────────────────────
    logger.info("=" * 60)
    logger.info("SCRAPING RUN COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Run ID:               {run_id}")
    logger.info(f"  New companies:         {new_companies_count}")
    logger.info(f"  New emails:            {new_emails_count}")
    logger.info(f"  Total companies (DB):  {total_stats['total_companies']}")
    logger.info(f"  Total emails (DB):     {total_stats['total_emails']}")
    logger.info(f"  Verified emails (DB):  {total_stats['verified_emails']}")
    logger.info(f"  Excel:                 {excel_path}")
    logger.info(f"  CSVs:                  {csv_dir}")
    logger.info(f"  Database:              {db_path}")
    logger.info("=" * 60)

    # Also update the legacy cache for backward compatibility
    try:
        all_contacts_for_cache = db.get_all_contacts()
        company_cache = {}
        for contact in all_contacts_for_cache:
            name = contact.get("company")
            if name:
                company_cache[name] = {
                    "website": contact.get("website"),
                    "email": contact.get("email"),
                    "email_status": contact.get("mx_status"),
                    "page_found_on": contact.get("page_found_on"),
                }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(company_cache, f, indent=2)
    except Exception as e:
        logger.warning(f"Error updating legacy cache: {e}")

    db.close()
    logger.info(f"Done. Results written to {excel_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI/ML Internship Scraper")
    parser.add_argument("--test", action="store_true", help="Run a quick test scrape (1 keyword, 1 portal)")
    parser.add_argument("--limit-keywords", type=int, default=None, help="Limit number of keywords to scrape")
    parser.add_argument("--portal", type=str, default=None, help="Run only a specific portal (internshala, naukri, wellfound, indeed, yc, google_jobs)")
    cli_args = parser.parse_args()
    run(cli_args)
