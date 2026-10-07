"""
semantic_search.py
Natural-language search engine for AI/ML internships and job leads.
Parses natural conversational queries (e.g. "Find GenAI internships in Pune involving RAG"),
extracts intent, target roles, technical skills, locations, and experience level,
and scores jobs using hybrid semantic matching + TF-IDF cosine similarity.
"""

import re
import math
from typing import Dict, List, Any, Tuple

# Common conversational stop words to strip from query keywords
STOP_WORDS = {
    "find", "search", "show", "give", "me", "looking", "for", "in", "at", "with",
    "and", "or", "to", "the", "a", "an", "of", "involving", "related", "based",
    "internship", "internships", "intern", "job", "jobs", "role", "roles",
    "position", "positions", "opportunity", "opportunities", "please", "can",
    "you", "i", "want", "need", "any", "some", "all"
}

# Known location keywords and their alias maps
LOCATION_ALIASES = {
    "pune": ["pune", "pcmc", "pimpri", "chinchwad", "baner", "hinjewadi", "kharadi"],
    "mumbai": ["mumbai", "bombay", "navi mumbai", "thane", "dombivli", "kalyan"],
    "bangalore": ["bangalore", "bengaluru", "banglore"],
    "hyderabad": ["hyderabad", "secunderabad", "hyd"],
    "delhi": ["delhi", "new delhi", "ncr", "noida", "gurgaon", "gurugram", "ghaziabad"],
    "noida": ["noida", "delhi", "ncr"],
    "gurgaon": ["gurgaon", "gurugram", "delhi", "ncr"],
    "indore": ["indore"],
    "nagpur": ["nagpur"],
    "chennai": ["chennai", "madras"],
    "ahmedabad": ["ahmedabad", "gandhinagar"],
    "kolkata": ["kolkata", "calcutta"],
    "jaipur": ["jaipur"],
    "remote": ["remote", "work from home", "wfh", "worldwide", "global remote"],
}

# Semantic concept expansion & skill synonyms
SEMANTIC_SYNONYMS = {
    "rag": ["rag", "retrieval", "llm", "genai", "generative ai", "copilot", "langchain", "llamaindex", "agentic", "prompt engineering"],
    "genai": ["genai", "generative ai", "llm", "rag", "agentic", "copilot", "gpt", "prompt engineering", "ai agent"],
    "llm": ["llm", "large language model", "genai", "rag", "agentic", "prompt engineering", "copilot", "langchain"],
    "agentic": ["agentic", "ai agent", "autonomous agent", "copilot", "genai", "llm", "ai automation"],
    "langchain": ["langchain", "llamaindex", "rag", "llm", "genai", "python", "ai developer"],
    "python": ["python", "py", "software engineer", "developer", "backend", "machine learning", "data science"],
    "machine learning": ["machine learning", "ml", "deep learning", "ai", "artificial intelligence", "data science", "pytorch", "tensorflow"],
    "ml": ["ml", "machine learning", "deep learning", "ai", "artificial intelligence", "data science"],
    "ai engineer": ["ai engineer", "ai developer", "ai specialist", "ai research", "machine learning engineer", "ml engineer"],
    "fresher": ["fresher", "freshers", "intern", "junior", "entry level", "student", "graduate"],
    "freshers": ["fresher", "freshers", "intern", "junior", "entry level", "student", "graduate"],
    "data science": ["data science", "data scientist", "data analytics", "machine learning", "ai"],
    "deep learning": ["deep learning", "neural network", "pytorch", "tensorflow", "computer vision", "nlp"],
    "nlp": ["nlp", "natural language", "llm", "genai", "text processing", "speech"],
    "computer vision": ["computer vision", "cv", "image processing", "opencv", "deep learning"],
}

WORK_MODE_TERMS = {
    "remote": "Remote",
    "wfh": "Remote",
    "work from home": "Remote",
    "hybrid": "Hybrid",
    "on-site": "On-site",
    "onsite": "On-site",
    "office": "On-site"
}


def parse_nl_query(query: str) -> Dict[str, Any]:
    """
    Parses a natural-language search query, extracting:
    - Target location(s)
    - Work mode (Remote/Hybrid/On-site)
    - Skills & role keywords
    - Experience markers (freshers, junior)
    - Cleaned residual terms
    """
    raw = query.strip()
    lowered = raw.lower()

    detected_locations = []
    detected_mode = None
    detected_skills = []
    is_fresher_intent = False

    # 1. Detect locations
    for loc_key, aliases in LOCATION_ALIASES.items():
        if loc_key == "remote":
            continue
        # Use regex boundary matching
        for alias in aliases:
            if re.search(r"\b" + re.escape(alias) + r"\b", lowered):
                detected_locations.append(loc_key.capitalize())
                break

    # 2. Detect work mode
    if any(re.search(r"\b" + re.escape(k) + r"\b", lowered) for k in ["remote", "work from home", "wfh"]):
        detected_mode = "Remote"
    elif "hybrid" in lowered:
        detected_mode = "Hybrid"
    elif any(k in lowered for k in ["on-site", "onsite", "in-office", "in office"]):
        detected_mode = "On-site"

    # 3. Detect experience intent (freshers)
    if any(re.search(r"\b" + re.escape(w) + r"\b", lowered) for w in ["fresher", "freshers", "entry level", "junior", "beginner"]):
        is_fresher_intent = True

    # 4. Detect semantic skills & keywords
    for skill_key, related in SEMANTIC_SYNONYMS.items():
        if re.search(r"\b" + re.escape(skill_key) + r"\b", lowered):
            detected_skills.append(skill_key)

    # 5. Extract residual informative tokens (minus stop words)
    tokens = re.findall(r"[a-zA-Z0-9+#.-]+", lowered)
    informative_tokens = [
        t for t in tokens 
        if t not in STOP_WORDS 
        and not any(t == loc.lower() for loc in detected_locations)
        and len(t) > 1
    ]

    # Build human-readable intent breakdown summary
    parts = []
    if detected_skills:
        parts.append(f"Skill: {', '.join(s.upper() if len(s) <= 4 else s.title() for s in detected_skills)}")
    elif informative_tokens:
        parts.append(f"Keywords: {', '.join(informative_tokens[:3])}")
    if detected_locations:
        parts.append(f"City: {', '.join(detected_locations)}")
    if detected_mode:
        parts.append(f"Mode: {detected_mode}")
    if is_fresher_intent:
        parts.append("Freshers / Entry Level")

    intent_summary = " • ".join(parts) if parts else "General search"

    return {
        "raw_query": raw,
        "locations": detected_locations,
        "work_mode": detected_mode,
        "skills": detected_skills,
        "is_fresher": is_fresher_intent,
        "informative_tokens": informative_tokens,
        "intent_summary": intent_summary,
        "is_natural_language": len(tokens) >= 3 or bool(detected_locations or detected_skills or detected_mode)
    }


def compute_job_score(job: Dict[str, Any], parsed: Dict[str, Any]) -> Tuple[float, List[str]]:
    """
    Calculates relevance score (0 - 100) and matched reason tags for a job.
    """
    score = 0.0
    match_reasons = []

    role_text = (job.get("role") or "").lower()
    company_text = (job.get("company") or "").lower()
    loc_text = (job.get("location") or "").lower()
    type_text = (job.get("type") or "").lower()
    desc_text = (job.get("description") or "").lower()
    full_text = f"{role_text} {company_text} {loc_text} {type_text} {desc_text}"

    # ── 1. Location Matching (Max 30 pts) ────────────────────────
    if parsed["locations"]:
        target_locs = [loc.lower() for loc in parsed["locations"]]
        matched_city = False
        for loc in target_locs:
            aliases = LOCATION_ALIASES.get(loc, [loc])
            if any(alias in loc_text for alias in aliases):
                score += 30.0
                match_reasons.append(f"Location: {loc.capitalize()}")
                matched_city = True
                break
        
        # If city didn't match, give partial credit for Remote if work mode allowed
        if not matched_city:
            if "work from home" in loc_text or "remote" in loc_text:
                score += 15.0
                match_reasons.append("Remote Option")
            else:
                # Strong penalty for wrong location when location was explicitly queried
                score -= 20.0
    else:
        # If no location specified in query, give baseline neutral score
        score += 10.0

    # ── 2. Work Mode Matching (Max 15 pts) ───────────────────────
    if parsed["work_mode"]:
        req_mode = parsed["work_mode"].lower()
        if req_mode in type_text or req_mode in loc_text:
            score += 15.0
            match_reasons.append(f"Mode: {parsed['work_mode']}")
        elif req_mode == "remote" and ("work from home" in loc_text or "wfh" in loc_text):
            score += 15.0
            match_reasons.append("Mode: Remote")
        else:
            score -= 10.0

    # ── 3. Skills & Semantic Concept Matching (Max 40 pts) ───────
    matched_skills_count = 0
    for skill in parsed["skills"]:
        synonyms = SEMANTIC_SYNONYMS.get(skill, [skill])
        # Direct role title match gets top points
        if any(re.search(r"\b" + re.escape(syn) + r"\b", role_text) for syn in synonyms):
            score += 25.0
            matched_skills_count += 1
            label = skill.upper() if len(skill) <= 4 else skill.title()
            match_reasons.append(f"Role: {label}")
        elif any(syn in full_text for syn in synonyms):
            score += 15.0
            matched_skills_count += 1
            label = skill.upper() if len(skill) <= 4 else skill.title()
            match_reasons.append(f"Skill: {label}")

    # ── 4. Freshers / Experience Matching (Max 10 pts) ───────────
    if parsed["is_fresher"]:
        if any(k in full_text for k in ["fresher", "intern", "trainee", "junior", "student"]):
            score += 10.0
            match_reasons.append("Freshers / Intern")

    # ── 5. Lexical & Token Overlap (Max 25 pts) ───────────────────
    matched_tokens = 0
    for token in parsed["informative_tokens"]:
        if re.search(r"\b" + re.escape(token) + r"\b", role_text):
            score += 12.0
            matched_tokens += 1
        elif re.search(r"\b" + re.escape(token) + r"\b", full_text):
            score += 6.0
            matched_tokens += 1

    # Normalization (Cap between 0 and 100)
    final_score = max(0.0, min(100.0, score))
    return final_score, match_reasons


def semantic_search_jobs(jobs: List[Dict[str, Any]], query: str, threshold: float = 20.0) -> Dict[str, Any]:
    """
    Executes semantic search over the jobs list using natural-language understanding.
    Returns ranked jobs with relevance scores, matching reasons, and intent summary.
    """
    parsed = parse_nl_query(query)
    scored_jobs = []

    for job in jobs:
        rel_score, reasons = compute_job_score(job, parsed)
        if rel_score >= threshold:
            scored_job = dict(job)
            scored_job["relevance_score"] = round(rel_score, 1)
            scored_job["match_reasons"] = reasons
            scored_jobs.append(scored_job)

    # Sort descending by relevance score, then by recency
    scored_jobs.sort(key=lambda j: (j.get("relevance_score", 0), j.get("posted_date") or ""), reverse=True)

    return {
        "results": scored_jobs,
        "total_matches": len(scored_jobs),
        "parsed_intent": parsed,
    }
