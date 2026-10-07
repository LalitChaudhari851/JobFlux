"""
email_scorer.py
Assigns priority scores to discovered emails based on their prefix,
the page they were found on, and the discovery method (mailto vs regex).

Higher scores indicate more valuable recruiter/outreach emails.
"""


# ── Base priority by email prefix ────────────────────────────────
PREFIX_SCORES = {
    "hr": 95,
    "careers": 95,
    "career": 95,
    "jobs": 90,
    "talent": 90,
    "people": 85,
    "recruitment": 80,
    "recruiting": 80,
    "recruit": 80,
    "hiring": 75,
    "humanresources": 75,
    "join": 70,
    "apply": 70,
    "internship": 70,
    "internships": 70,
    "info": 60,
    "contact": 55,
    "hello": 45,
    "team": 45,
    "admin": 40,
    "office": 40,
    "support": 35,
    "help": 35,
    "sales": 25,
    "marketing": 20,
    "press": 15,
    "media": 15,
    "legal": 10,
    "complaints": 10,
    "noreply": 0,
    "no-reply": 0,
    "mailer-daemon": 0,
    "postmaster": 0,
}

# Default score for unrecognized prefixes (e.g., personal names like "john@")
DEFAULT_SCORE = 50

# Pages that suggest the email is recruiter-relevant
CAREER_PAGE_KEYWORDS = {"careers", "jobs", "hiring", "join", "work-with-us",
                        "join-us", "people", "team", "our-team"}

# ── Excluded email patterns ──────────────────────────────────────
# These are almost never useful for outreach
EXCLUDED_PATTERNS = {
    "noreply", "no-reply", "mailer-daemon", "postmaster",
    "bounce", "unsubscribe", "donotreply", "do-not-reply",
}


def score_email(email: str, page_url: str = None, found_via_mailto: bool = False) -> int:
    """
    Calculate a priority score for an email address.
    
    Args:
        email: The email address to score.
        page_url: The URL where the email was found (used for page bonus).
        found_via_mailto: True if found via <a href="mailto:..."> link.
    
    Returns:
        Integer priority score (0-100+).
    """
    if not email:
        return 0

    prefix = email.split("@")[0].strip().lower()

    # Check for excluded patterns
    if prefix in EXCLUDED_PATTERNS:
        return 0

    # Base score from prefix
    score = PREFIX_SCORES.get(prefix, DEFAULT_SCORE)

    # Bonus: found on a careers/jobs page
    if page_url:
        page_lower = page_url.lower()
        if any(kw in page_lower for kw in CAREER_PAGE_KEYWORDS):
            score += 5

    # Bonus: found via mailto link (higher confidence — intentionally published)
    if found_via_mailto:
        score += 3

    # Cap at 100
    return min(score, 100)


def is_excluded_email(email: str) -> bool:
    """Check if an email should be completely excluded from results."""
    if not email:
        return True
    prefix = email.split("@")[0].strip().lower()
    return prefix in EXCLUDED_PATTERNS


def sort_emails_by_priority(emails: list) -> list:
    """
    Sort a list of email dicts by priority_score descending.
    Each dict should have at least an 'email' and 'priority_score' key.
    """
    return sorted(emails, key=lambda e: e.get("priority_score", 0), reverse=True)


def get_best_email(emails: list) -> dict:
    """Return the highest-priority email from a list of email dicts."""
    if not emails:
        return None
    sorted_emails = sort_emails_by_priority(emails)
    return sorted_emails[0]
