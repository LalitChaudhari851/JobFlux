"""
classifier.py
Classifies companies into industry categories (AI, GenAI, ML, SaaS, etc.)
based on keyword evidence found on their website.

Uses a weighted keyword approach:
- Title/H1 mentions: 3x weight
- Meta description: 2x weight
- Body text: 1x weight
"""

import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger("scraper")


# ── Category keyword definitions ─────────────────────────────────
# Each category maps to a list of (keyword, weight_multiplier) tuples.
# More specific terms have higher multipliers to avoid false positives.
CATEGORY_KEYWORDS = {
    "AI": [
        ("artificial intelligence", 2), ("ai platform", 2), ("ai-powered", 2),
        ("ai solutions", 2), ("ai company", 3), ("computer vision", 2),
        ("natural language processing", 2), ("nlp", 1), ("neural network", 2),
        ("deep learning", 2), ("ai/ml", 3), ("ai agent", 2),
        ("agentic ai", 3), ("ai startup", 3),
    ],
    "GenAI": [
        ("generative ai", 3), ("genai", 3), ("gen ai", 3),
        ("text generation", 2), ("image generation", 2),
        ("foundation model", 2), ("diffusion model", 2),
        ("prompt engineering", 2), ("ai-generated", 2),
    ],
    "Machine Learning": [
        ("machine learning", 3), ("ml engineer", 3), ("ml platform", 3),
        ("ml ops", 2), ("mlops", 2), ("predictive model", 2),
        ("training model", 2), ("feature engineering", 2),
        ("ml pipeline", 2), ("supervised learning", 2),
        ("unsupervised learning", 2), ("reinforcement learning", 2),
    ],
    "LLM": [
        ("large language model", 3), ("llm", 2), ("chatbot", 1),
        ("gpt", 1), ("transformer model", 2), ("fine-tuning", 1),
        ("retrieval augmented", 2), ("rag", 1), ("vector database", 2),
        ("embedding", 1), ("language model", 2),
    ],
    "Data Science": [
        ("data science", 3), ("data scientist", 3), ("data analytics", 2),
        ("data engineering", 2), ("big data", 2), ("data pipeline", 2),
        ("data warehouse", 2), ("etl", 1), ("data visualization", 2),
        ("statistical analysis", 2), ("data-driven", 1),
    ],
    "Analytics": [
        ("analytics", 1), ("business intelligence", 2), ("bi platform", 2),
        ("dashboard", 1), ("reporting tool", 2), ("metrics", 1),
        ("insights platform", 2), ("analytics platform", 3),
    ],
    "SaaS": [
        ("saas", 2), ("software as a service", 3), ("cloud platform", 2),
        ("subscription software", 2), ("saas platform", 3),
        ("b2b software", 2), ("enterprise software", 2),
    ],
    "FinTech": [
        ("fintech", 3), ("financial technology", 3), ("digital payments", 2),
        ("neobank", 3), ("lending platform", 2), ("insurtech", 3),
        ("wealth management", 2), ("trading platform", 2),
        ("cryptocurrency", 2), ("blockchain", 2), ("defi", 2),
    ],
    "Healthcare": [
        ("healthtech", 3), ("health tech", 3), ("medtech", 3),
        ("digital health", 3), ("telemedicine", 3), ("clinical", 1),
        ("pharmaceutical", 2), ("biotech", 2), ("medical device", 2),
        ("healthcare ai", 3), ("patient care", 2),
    ],
    "EdTech": [
        ("edtech", 3), ("ed tech", 3), ("education technology", 3),
        ("e-learning", 2), ("elearning", 2), ("online learning", 2),
        ("lms", 1), ("learning management", 2), ("online education", 2),
        ("skill development", 1), ("upskilling", 2),
    ],
    "Cloud": [
        ("cloud computing", 3), ("cloud infrastructure", 3),
        ("cloud native", 2), ("kubernetes", 1), ("docker", 1),
        ("devops", 1), ("infrastructure as a service", 2),
        ("iaas", 2), ("paas", 2), ("serverless", 2),
    ],
    "Automation": [
        ("automation", 1), ("rpa", 2), ("robotic process automation", 3),
        ("workflow automation", 2), ("process automation", 2),
        ("test automation", 2), ("hyperautomation", 3),
        ("intelligent automation", 3), ("no-code automation", 2),
    ],
}

# Minimum confidence score to assign a category
MIN_CONFIDENCE = 5


def classify_company(html_content: str, company_name: str = None) -> str:
    """
    Classify a company based on its website HTML content using fast regex.
    
    Args:
        html_content: Raw HTML of the company's homepage or about page.
        company_name: Optional company name for additional context.
    
    Returns:
        The best-matching category string, or "Uncategorized" if no match.
    """
    if not html_content:
        return "Uncategorized"

    # Slice HTML content to first 50,000 characters to prevent catastrophic backtracking/long regex runs on huge pages
    html_content = html_content[:50000]

    # Regex for title text
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
    title_text = title_match.group(1).strip().lower() if title_match else ""

    # Regex for H1 texts
    h1_text = " ".join(
        re.findall(r"<h1[^>]*>(.*?)</h1>", html_content, re.IGNORECASE | re.DOTALL)
    ).strip().lower()

    # Regex for meta description content
    meta_desc = ""
    # Try different meta tag formats
    meta_matches = re.findall(
        r'<meta[^>]*content=["\'](.*?)["\'][^>]*name=["\']description["\']',
        html_content,
        re.IGNORECASE | re.DOTALL
    )
    if not meta_matches:
        meta_matches = re.findall(
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']',
            html_content,
            re.IGNORECASE | re.DOTALL
        )
    if meta_matches:
        meta_desc = meta_matches[0].strip().lower()

    # Fast body text extraction by stripping scripts, styles, and markup tags
    # Remove script and style blocks
    clean_html = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.IGNORECASE | re.DOTALL)
    clean_html = re.sub(r"<style[^>]*>.*?</style>", "", clean_html, flags=re.IGNORECASE | re.DOTALL)
    clean_html = re.sub(r"<noscript[^>]*>.*?</noscript>", "", clean_html, flags=re.IGNORECASE | re.DOTALL)
    
    # Strip HTML tags
    body_text = re.sub(r"<[^>]+>", " ", clean_html)
    # Normalize spaces
    body_text = " ".join(body_text.split()).strip().lower()
    # Limit to first 5000 characters for performance
    body_text = body_text[:5000]

    # Score each category
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for keyword, weight in keywords:
            kw_lower = keyword.lower()
            # Title/H1 mentions: 3x
            if kw_lower in title_text or kw_lower in h1_text:
                score += weight * 3
            # Meta description: 2x
            if kw_lower in meta_desc:
                score += weight * 2
            # Body text: 1x (count occurrences, capped at 3)
            count = min(body_text.count(kw_lower), 3)
            score += weight * count

        if score >= MIN_CONFIDENCE:
            scores[category] = score

    if not scores:
        return "Uncategorized"

    # Return the top category (or top 2 if they're close)
    sorted_categories = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_category = sorted_categories[0][0]
    best_score = sorted_categories[0][1]

    # If second category is within 60% of best, combine them
    if len(sorted_categories) > 1:
        second_category = sorted_categories[1][0]
        second_score = sorted_categories[1][1]
        if second_score >= best_score * 0.6:
            return f"{best_category}, {second_category}"

    return best_category


def classify_from_multiple_pages(html_pages: list, company_name: str = None) -> str:
    """
    Classify using content from multiple pages (homepage, about, etc.).
    Merges evidence from all pages before classifying.
    
    Args:
        html_pages: List of raw HTML strings from different pages.
        company_name: Optional company name for context.
    
    Returns:
        Category string.
    """
    # Concatenate all HTML for a combined signal
    combined = "\n".join(page for page in html_pages if page)
    if not combined:
        return "Uncategorized"
    return classify_company(combined, company_name)
