"""
email_validator_util.py
Validates scraped emails WITHOUT sending any mail (no SMTP handshake, which is
unreliable and can get your IP flagged). Checks:
  1. Syntax
  2. MX record existence on the domain
  3. Whether the email's domain matches the company's actual website domain
Never generates or guesses emails -- only validates ones that were actually
found on a page.

Enhanced with:
- Batch validation support
- MX result caching for performance
- Normalization (lowercase, trim whitespace)
"""

import tldextract
from email_validator import validate_email, EmailNotValidError

# Cache MX lookup results to avoid redundant DNS queries
_mx_cache = {}


def check_email(email: str, company_website: str = None) -> dict:
    """
    Returns:
    {
        "email": str,
        "status": "Valid - MX confirmed" | "Syntax OK - MX check failed"
                   | "Domain mismatch" | "Invalid syntax" | "No email found",
        "domain": str or None
    }
    """
    if not email:
        return {"email": None, "status": "No email found", "domain": None}

    # Normalize: lowercase and trim whitespace
    email = email.strip().lower()

    # Step 1 + 2: syntax check and MX check (email-validator does both when
    # check_deliverability=True -- it queries MX records, not SMTP)
    try:
        result = validate_email(email, check_deliverability=True)
        normalized_email = result.normalized
        domain = result.domain
        # Cache successful MX lookup
        _mx_cache[domain] = True
    except EmailNotValidError:
        # Retry with deliverability check off, just to see if it's a syntax
        # issue vs an MX issue
        try:
            result = validate_email(email, check_deliverability=False)
            domain = result.domain
            # Check if we've already verified MX for this domain
            if _mx_cache.get(domain):
                return {"email": email, "status": "Valid - MX confirmed", "domain": domain}
            _mx_cache[domain] = False
            return {"email": email, "status": "Syntax OK - MX check failed", "domain": domain}
        except EmailNotValidError:
            return {"email": email, "status": "Invalid syntax", "domain": None}

    # Step 3: domain match against company website (if provided)
    if company_website:
        website_domain = _extract_root_domain(company_website)
        email_domain = _extract_root_domain(domain)
        if website_domain and email_domain and website_domain != email_domain:
            return {"email": normalized_email, "status": "Domain mismatch", "domain": domain}

    return {"email": normalized_email, "status": "Valid - MX confirmed", "domain": domain}


def check_emails_batch(emails: list, company_website: str = None) -> list:
    """
    Validate a list of email strings or dicts in batch.
    
    Args:
        emails: List of email strings, or list of dicts with an 'email' key.
        company_website: Optional company website for domain matching.
    
    Returns:
        List of validation result dicts.
    """
    results = []
    for item in emails:
        if isinstance(item, dict):
            email = item.get("email", "")
        else:
            email = item
        result = check_email(email, company_website)
        results.append(result)
    return results


def normalize_email(email: str) -> str:
    """Normalize an email for comparison: lowercase + strip whitespace."""
    if not email:
        return ""
    return email.strip().lower()


def deduplicate_emails(emails: list) -> list:
    """
    Remove duplicate emails from a list of email dicts.
    Each dict should have an 'email' key.
    Keeps the first occurrence.
    """
    seen = set()
    unique = []
    for item in emails:
        normalized = normalize_email(item.get("email", ""))
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(item)
    return unique


def _extract_root_domain(url_or_domain: str) -> str:
    if not url_or_domain:
        return None
    extracted = tldextract.extract(url_or_domain)
    if extracted.domain and extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}".lower()
    return None


if __name__ == "__main__":
    print(check_email("hr@solnixmedia.com", "https://solnixmedia.com"))
    print(check_email("careers@somefakecompanyxyz123.com"))
    print(check_email("not-an-email"))
