"""
db.py
SQLite-backed persistence layer for incremental scraping.
Tracks companies, emails, crawl history, and run metadata so that
each new run can export ONLY newly discovered data.
"""

import sqlite3
import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("scraper")


class ScraperDB:
    """Manages SQLite database for incremental scraping state."""

    def __init__(self, db_path: str = "output/scraper.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                name_normalized TEXT NOT NULL UNIQUE,
                website TEXT,
                category TEXT DEFAULT 'Uncategorized',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                email_normalized TEXT NOT NULL,
                priority_score INTEGER DEFAULT 50,
                mx_status TEXT DEFAULT 'Pending',
                page_found_on TEXT,
                first_seen TEXT NOT NULL,
                run_id INTEGER,
                FOREIGN KEY (company_id) REFERENCES companies(id),
                UNIQUE(company_id, email_normalized)
            );

            CREATE TABLE IF NOT EXISTS crawl_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                crawled_at TEXT NOT NULL,
                emails_found INTEGER DEFAULT 0,
                FOREIGN KEY (company_id) REFERENCES companies(id)
            );

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                new_companies INTEGER DEFAULT 0,
                new_emails INTEGER DEFAULT 0,
                total_companies INTEGER DEFAULT 0,
                total_emails INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_emails_company ON emails(company_id);
            CREATE INDEX IF NOT EXISTS idx_emails_normalized ON emails(email_normalized);
            CREATE INDEX IF NOT EXISTS idx_companies_normalized ON companies(name_normalized);
            CREATE INDEX IF NOT EXISTS idx_emails_run ON emails(run_id);
        """)
        self.conn.commit()

    # ── Run Management ──────────────────────────────────────────────

    def start_run(self) -> int:
        """Start a new scraping run and return its ID."""
        now = datetime.now().isoformat()
        cursor = self.conn.execute(
            "INSERT INTO runs (started_at) VALUES (?)", (now,)
        )
        self.conn.commit()
        run_id = cursor.lastrowid
        logger.info(f"Started scraping run #{run_id}")
        return run_id

    def complete_run(self, run_id: int, stats: dict):
        """Mark a run as complete with summary statistics."""
        now = datetime.now().isoformat()
        self.conn.execute(
            """UPDATE runs SET completed_at=?, new_companies=?, new_emails=?,
               total_companies=?, total_emails=?
               WHERE id=?""",
            (now, stats.get("new_companies", 0), stats.get("new_emails", 0),
             stats.get("total_companies", 0), stats.get("total_emails", 0),
             run_id)
        )
        self.conn.commit()
        logger.info(f"Completed run #{run_id}: {stats}")

    # ── Company Management ──────────────────────────────────────────

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize company name for deduplication."""
        return name.strip().lower()

    def get_or_create_company(self, name: str, website: str = None) -> tuple:
        """
        Returns (company_id, is_new).
        Creates the company if it doesn't exist; updates last_seen if it does.
        """
        normalized = self._normalize_name(name)
        now = datetime.now().isoformat()

        row = self.conn.execute(
            "SELECT id FROM companies WHERE name_normalized = ?", (normalized,)
        ).fetchone()

        if row:
            company_id = row["id"]
            # Update last_seen and website if we now have one
            if website:
                self.conn.execute(
                    "UPDATE companies SET last_seen=?, website=COALESCE(NULLIF(?, ''), website) WHERE id=?",
                    (now, website, company_id)
                )
            else:
                self.conn.execute(
                    "UPDATE companies SET last_seen=? WHERE id=?",
                    (now, company_id)
                )
            self.conn.commit()
            return company_id, False

        cursor = self.conn.execute(
            "INSERT INTO companies (name, name_normalized, website, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
            (name.strip(), normalized, website, now, now)
        )
        self.conn.commit()
        return cursor.lastrowid, True

    def update_company_category(self, company_id: int, category: str):
        """Update the classification category for a company."""
        self.conn.execute(
            "UPDATE companies SET category=? WHERE id=?",
            (category, company_id)
        )
        self.conn.commit()

    def update_company_website(self, company_id: int, website: str):
        """Update the resolved website for a company."""
        self.conn.execute(
            "UPDATE companies SET website=? WHERE id=?",
            (website, company_id)
        )
        self.conn.commit()

    def get_company_website(self, company_id: int) -> Optional[str]:
        """Get the stored website for a company."""
        row = self.conn.execute(
            "SELECT website FROM companies WHERE id=?", (company_id,)
        ).fetchone()
        return row["website"] if row else None

    def has_valid_emails(self, company_id: int) -> bool:
        """Check if this company already has MX-verified emails."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM emails WHERE company_id=? AND mx_status='Valid - MX confirmed'",
            (company_id,)
        ).fetchone()
        return row["cnt"] > 0

    # ── Email Management ────────────────────────────────────────────

    def add_email(self, company_id: int, email: str, priority_score: int,
                  mx_status: str, page_found_on: str, run_id: int) -> bool:
        """
        Add an email for a company. Returns True if it's a NEW email
        (not previously stored), False if duplicate.
        """
        email_normalized = email.strip().lower()
        now = datetime.now().isoformat()

        try:
            self.conn.execute(
                """INSERT INTO emails
                   (company_id, email, email_normalized, priority_score, mx_status, page_found_on, first_seen, run_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (company_id, email.strip(), email_normalized, priority_score,
                 mx_status, page_found_on, now, run_id)
            )
            self.conn.commit()
            return True  # New email
        except sqlite3.IntegrityError:
            # Already exists — update status if needed
            self.conn.execute(
                """UPDATE emails SET mx_status=?, priority_score=MAX(priority_score, ?)
                   WHERE company_id=? AND email_normalized=?""",
                (mx_status, priority_score, company_id, email_normalized)
            )
            self.conn.commit()
            return False  # Existing email

    def add_emails_batch(self, company_id: int, emails: list, run_id: int) -> int:
        """
        Add multiple emails for a company.
        Each item in emails is a dict with: email, priority_score, mx_status, page_found_on.
        Returns the count of NEW emails added.
        """
        new_count = 0
        for item in emails:
            is_new = self.add_email(
                company_id=company_id,
                email=item["email"],
                priority_score=item.get("priority_score", 50),
                mx_status=item.get("mx_status", "Pending"),
                page_found_on=item.get("page_found_on"),
                run_id=run_id,
            )
            if is_new:
                new_count += 1
        return new_count

    # ── Crawl Log ───────────────────────────────────────────────────

    def log_crawl(self, company_id: int, url: str, emails_found: int = 0):
        """Record that a URL was crawled for a company."""
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO crawl_log (company_id, url, crawled_at, emails_found) VALUES (?, ?, ?, ?)",
            (company_id, url, now, emails_found)
        )
        self.conn.commit()

    def was_url_crawled(self, company_id: int, url: str) -> bool:
        """Check if a URL was already crawled for this company."""
        row = self.conn.execute(
            "SELECT id FROM crawl_log WHERE company_id=? AND url=?",
            (company_id, url)
        ).fetchone()
        return row is not None

    # ── Query / Export Methods ──────────────────────────────────────

    def get_all_contacts(self) -> list:
        """Get all companies with their best (highest priority) email."""
        rows = self.conn.execute("""
            SELECT c.name AS company, c.website, c.category,
                   e.email, e.priority_score, e.mx_status, e.page_found_on,
                   CASE WHEN e.run_id = (SELECT MAX(id) FROM runs) THEN 'New' ELSE 'Existing' END AS status
            FROM companies c
            LEFT JOIN emails e ON e.company_id = c.id
                AND e.id = (
                    SELECT e2.id FROM emails e2
                    WHERE e2.company_id = c.id AND e2.mx_status = 'Valid - MX confirmed'
                    ORDER BY e2.priority_score DESC, e2.first_seen ASC
                    LIMIT 1
                )
            ORDER BY e.priority_score DESC NULLS LAST
        """).fetchall()
        return [dict(row) for row in rows]

    def get_new_contacts(self, run_id: int) -> list:
        """Get only contacts discovered in a specific run."""
        rows = self.conn.execute("""
            SELECT c.name AS company, c.website, c.category,
                   e.email, e.priority_score, e.mx_status, e.page_found_on,
                   'New' AS status
            FROM emails e
            JOIN companies c ON c.id = e.company_id
            WHERE e.run_id = ?
            ORDER BY e.priority_score DESC
        """, (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_high_priority_contacts(self, min_score: int = 75) -> list:
        """Get contacts with priority score >= threshold."""
        rows = self.conn.execute("""
            SELECT c.name AS company, c.website, c.category,
                   e.email, e.priority_score, e.mx_status, e.page_found_on,
                   CASE WHEN e.run_id = (SELECT MAX(id) FROM runs) THEN 'New' ELSE 'Existing' END AS status
            FROM emails e
            JOIN companies c ON c.id = e.company_id
            WHERE e.priority_score >= ? AND e.mx_status = 'Valid - MX confirmed'
            ORDER BY e.priority_score DESC
        """, (min_score,)).fetchall()
        return [dict(row) for row in rows]

    def get_ai_companies(self) -> list:
        """Get companies classified as AI/ML related."""
        ai_categories = ('AI', 'GenAI', 'Machine Learning', 'LLM', 'Data Science', 'Analytics')
        placeholders = ','.join('?' * len(ai_categories))
        rows = self.conn.execute(f"""
            SELECT c.name AS company, c.website, c.category,
                   e.email, e.priority_score, e.mx_status, e.page_found_on,
                   CASE WHEN e.run_id = (SELECT MAX(id) FROM runs) THEN 'New' ELSE 'Existing' END AS status
            FROM companies c
            LEFT JOIN emails e ON e.company_id = c.id
                AND e.id = (
                    SELECT e2.id FROM emails e2
                    WHERE e2.company_id = c.id AND e2.mx_status = 'Valid - MX confirmed'
                    ORDER BY e2.priority_score DESC LIMIT 1
                )
            WHERE c.category IN ({placeholders})
            ORDER BY e.priority_score DESC NULLS LAST
        """, ai_categories).fetchall()
        return [dict(row) for row in rows]

    def get_all_emails(self) -> list:
        """Get every discovered email across all companies."""
        rows = self.conn.execute("""
            SELECT c.name AS company, c.website, c.category,
                   e.email, e.priority_score, e.mx_status, e.page_found_on,
                   CASE WHEN e.run_id = (SELECT MAX(id) FROM runs) THEN 'New' ELSE 'Existing' END AS status
            FROM emails e
            JOIN companies c ON c.id = e.company_id
            ORDER BY c.name, e.priority_score DESC
        """).fetchall()
        return [dict(row) for row in rows]

    def get_internship_companies(self) -> list:
        """Get all companies that have active internship listings (same as all contacts)."""
        return self.get_all_contacts()

    def get_run_stats(self, run_id: int) -> dict:
        """Get summary stats for a specific run."""
        row = self.conn.execute(
            "SELECT * FROM runs WHERE id=?", (run_id,)
        ).fetchone()
        return dict(row) if row else {}

    def get_total_counts(self) -> dict:
        """Get overall database statistics."""
        companies = self.conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        emails = self.conn.execute(
            "SELECT COUNT(*) FROM emails WHERE mx_status='Valid - MX confirmed'"
        ).fetchone()[0]
        total_emails = self.conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
        return {
            "total_companies": companies,
            "verified_emails": emails,
            "total_emails": total_emails,
        }

    # ── Migration: Import from legacy cache ─────────────────────────

    def import_from_cache(self, cache_data: dict, run_id: int):
        """
        Import companies and emails from the legacy company_cache.json format.
        This allows seamless upgrade from the old system.
        """
        imported = 0
        for company_name, info in cache_data.items():
            website = info.get("website")
            email = info.get("email")
            mx_status = info.get("email_status", "Pending")
            page_found_on = info.get("page_found_on")

            company_id, _ = self.get_or_create_company(company_name, website)

            if email:
                self.add_email(
                    company_id=company_id,
                    email=email,
                    priority_score=50,  # Legacy emails get default score
                    mx_status=mx_status,
                    page_found_on=page_found_on,
                    run_id=run_id,
                )
                imported += 1

        logger.info(f"Imported {imported} emails from legacy cache")

    def close(self):
        """Close the database connection."""
        self.conn.close()
