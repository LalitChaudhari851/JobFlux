"""
date_parser.py
Converts raw posted-time strings like "6 hours ago", "1 week ago", "Just now",
"Today", "Yesterday", or absolute dates like "12 Jul 2026" into normalized
datetime objects, using the scrape timestamp as reference.
"""

import re
from datetime import datetime, timedelta
import dateparser


def normalize_posted_date(raw_text: str, scrape_time: datetime = None) -> dict:
    """
    Returns a dict:
    {
        "raw_text": original string,
        "normalized_date": datetime or None,
        "recency_flag": "Today" | "This Week" | "Older" | "Unknown"
    }
    """
    if scrape_time is None:
        scrape_time = datetime.now()

    if not raw_text or not raw_text.strip():
        return {"raw_text": raw_text, "normalized_date": None, "recency_flag": "Unknown"}

    text = raw_text.strip().lower()

    # Handle "just now" / "today"
    if "just now" in text or text == "today":
        normalized = scrape_time
        return _build_result(raw_text, normalized, scrape_time)

    if "yesterday" in text:
        normalized = scrape_time - timedelta(days=1)
        return _build_result(raw_text, normalized, scrape_time)

    # Handle "X hours ago", "X hour ago"
    hour_match = re.search(r"(\d+)\s*hour", text)
    if hour_match:
        hours = int(hour_match.group(1))
        normalized = scrape_time - timedelta(hours=hours)
        return _build_result(raw_text, normalized, scrape_time)

    # Handle "X minutes ago"
    min_match = re.search(r"(\d+)\s*min", text)
    if min_match:
        minutes = int(min_match.group(1))
        normalized = scrape_time - timedelta(minutes=minutes)
        return _build_result(raw_text, normalized, scrape_time)

    # Handle "X days ago"
    day_match = re.search(r"(\d+)\s*day", text)
    if day_match:
        days = int(day_match.group(1))
        normalized = scrape_time - timedelta(days=days)
        return _build_result(raw_text, normalized, scrape_time)

    # Handle "X weeks ago" / "1 week ago"
    week_match = re.search(r"(\d+)\s*week", text)
    if week_match:
        weeks = int(week_match.group(1))
        normalized = scrape_time - timedelta(weeks=weeks)
        return _build_result(raw_text, normalized, scrape_time)

    # Handle "X months ago"
    month_match = re.search(r"(\d+)\s*month", text)
    if month_match:
        months = int(month_match.group(1))
        normalized = scrape_time - timedelta(days=months * 30)
        return _build_result(raw_text, normalized, scrape_time)

    # Fallback: try dateparser for absolute dates like "12 Jul 2026"
    parsed = dateparser.parse(raw_text, settings={"RELATIVE_BASE": scrape_time})
    if parsed:
        return _build_result(raw_text, parsed, scrape_time)

    return {"raw_text": raw_text, "normalized_date": None, "recency_flag": "Unknown"}


def _build_result(raw_text: str, normalized: datetime, scrape_time: datetime) -> dict:
    delta = scrape_time - normalized
    if normalized.date() == scrape_time.date():
        flag = "Today"
    elif delta <= timedelta(days=7):
        flag = "This Week"
    else:
        flag = "Older"
    return {"raw_text": raw_text, "normalized_date": normalized, "recency_flag": flag}


def is_within_window(normalized_date: datetime, scrape_time: datetime, window_days: int) -> bool:
    if normalized_date is None:
        return True  # keep unknown dates rather than silently dropping them
    return (scrape_time - normalized_date) <= timedelta(days=window_days)


if __name__ == "__main__":
    # quick manual test
    now = datetime(2026, 7, 14, 12, 0, 0)
    tests = ["6 hours ago", "Just now", "1 week ago", "3 days ago", "Yesterday", "2 weeks ago", "12 Jul 2026"]
    for t in tests:
        print(t, "->", normalize_posted_date(t, now))
