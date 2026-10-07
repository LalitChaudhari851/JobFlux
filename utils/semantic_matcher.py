"""
utils/semantic_matcher.py

Deterministic, explainable semantic job matching engine.
Evaluates candidate profiles against actual scraped job listings across:
  - Skills (Direct matches, missing skills, transferable skills)
  - Target Role Alignment
  - Experience Level Suitability (Fresher / Intern / Entry)
  - Location Affinity (Tier-1 cities, aliases, remote allowances)
  - Work Mode Compatibility (Remote, Hybrid, On-site)
  - Semantic Text Similarity (Lexical & concept vector overlap)

Guarantees 100% reproducible, explainable scoring without hallucinated or random values.
"""

import os
import re
import math
import json
from typing import Dict, List, Any, Tuple, Set, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
PROFILE_FILE = os.path.join(OUTPUT_DIR, "candidate_profile.json")


# ── Canonical Skills Catalog & Regex Patterns ────────────────────────
SKILLS_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "Python": {
        "aliases": [r"\bpython\b", r"\bpython3\b", r"\bpy\b"],
        "category": "Programming",
        "weight": 1.2
    },
    "RAG": {
        "aliases": [
            r"\brag\b", r"\bretrieval[\s-]augmented[\s-]generation\b",
            r"\bvector[\s-]db\b", r"\bchromadb\b", r"\bpinecone\b",
            r"\bfaiss\b", r"\bqdrant\b", r"\bweaviate\b"
        ],
        "category": "GenAI / Architecture",
        "weight": 1.4
    },
    "LLM": {
        "aliases": [
            r"\bllm\b", r"\bllms\b", r"\blarge[\s-]language[\s-]models?\b",
            r"\bgpt\b", r"\bclaude\b", r"\bllama\b", r"\bmistral\b",
            r"\bgemini\b", r"\bprompt[\s-]engineering\b"
        ],
        "category": "GenAI / Architecture",
        "weight": 1.4
    },
    "LangChain": {
        "aliases": [
            r"\blangchain\b", r"\blanggraph\b", r"\bllamaindex\b",
            r"\bllama[\s-]index\b", r"\blangsmith\b"
        ],
        "category": "Frameworks",
        "weight": 1.3
    },
    "GenAI": {
        "aliases": [
            r"\bgenai\b", r"\bgen[\s-]ai\b", r"\bgenerative[\s-]ai\b",
            r"\bgenerative[\s-]artificial[\s-]intelligence\b",
            r"\bdiffusion\b", r"\bstable[\s-]diffusion\b"
        ],
        "category": "GenAI / Architecture",
        "weight": 1.3
    },
    "Agentic AI": {
        "aliases": [
            r"\bagentic[\s-]ai\b", r"\bai[\s-]agents?\b", r"\bcrewai\b",
            r"\bautogen\b", r"\bmulti[\s-]agent\b"
        ],
        "category": "GenAI / Architecture",
        "weight": 1.3
    },
    "Machine Learning": {
        "aliases": [
            r"\bmachine[\s-]learning\b", r"\bml\b", r"\bscikit[\s-]learn\b",
            r"\bsklearn\b", r"\bsupervised\b", r"\bunsupervised\b",
            r"\bxgboost\b", r"\blightgbm\b"
        ],
        "category": "Core AI",
        "weight": 1.2
    },
    "Deep Learning": {
        "aliases": [
            r"\bdeep[\s-]learning\b", r"\bdl\b", r"\bneural[\s-]networks?\b",
            r"\bcnn\b", r"\brnn\b", r"\blstm\b"
        ],
        "category": "Core AI",
        "weight": 1.2
    },
    "PyTorch": {
        "aliases": [r"\bpytorch\b", r"\btorch\b"],
        "category": "Frameworks",
        "weight": 1.2
    },
    "TensorFlow": {
        "aliases": [r"\btensorflow\b", r"\btf\b", r"\bkeras\b"],
        "category": "Frameworks",
        "weight": 1.1
    },
    "NLP": {
        "aliases": [
            r"\bnlp\b", r"\bnatural[\s-]language[\s-]processing\b",
            r"\bspacy\b", r"\bnltk\b", r"\bbert\b", r"\btransformers\b",
            r"\bhugging[\s-]face\b", r"\bhuggingface\b"
        ],
        "category": "Core AI",
        "weight": 1.2
    },
    "Computer Vision": {
        "aliases": [
            r"\bcomputer[\s-]vision\b", r"\bcv\b", r"\bopencv\b",
            r"\byolo\b", r"\bimage[\s-]processing\b", r"\bobject[\s-]detection\b"
        ],
        "category": "Core AI",
        "weight": 1.2
    },
    "FastAPI": {
        "aliases": [r"\bfastapi\b", r"\bflask\b", r"\bdjango\b", r"\brest[\s-]apis?\b", r"\bapi\b"],
        "category": "Backend",
        "weight": 1.0
    },
    "Docker": {
        "aliases": [r"\bdocker\b", r"\bcontainerization\b", r"\bkubernetes\b", r"\bk8s\b"],
        "category": "DevOps / Infra",
        "weight": 1.0
    },
    "SQL": {
        "aliases": [r"\bsql\b", r"\bpostgresql\b", r"\bmysql\b", r"\bsqlite\b", r"\bdatabase\b"],
        "category": "Data / Databases",
        "weight": 1.0
    },
    "AWS": {
        "aliases": [
            r"\baws\b", r"\bamazon[\s-]web[\s-]services\b", r"\bec2\b",
            r"\bs3\b", r"\blambda\b", r"\bsagemaker\b", r"\bbedrock\b", r"\bcloud\b"
        ],
        "category": "Cloud / Infra",
        "weight": 1.1
    },
    "GCP": {
        "aliases": [r"\bgcp\b", r"\bgoogle[\s-]cloud\b", r"\bvertex[\s-]ai\b"],
        "category": "Cloud / Infra",
        "weight": 1.0
    },
    "Git": {
        "aliases": [r"\bgit\b", r"\bgithub\b", r"\bversion[\s-]control\b"],
        "category": "Tools",
        "weight": 0.8
    },
    "Data Science": {
        "aliases": [
            r"\bdata[\s-]science\b", r"\bpandas\b", r"\bnumpy\b",
            r"\bdata[\s-]analysis\b", r"\bstatistics\b"
        ],
        "category": "Data",
        "weight": 1.1
    },
    "Fine-tuning": {
        "aliases": [r"\bfine[\s-]tuning\b", r"\blora\b", r"\bqlora\b", r"\bpeft\b"],
        "category": "GenAI / Architecture",
        "weight": 1.2
    },
    "C++": {
        "aliases": [r"\bc\+\+\b", r"\bcpp\b"],
        "category": "Programming",
        "weight": 0.9
    },
    "Embedded Systems": {
        "aliases": [r"\bembedded\b", r"\biot\b", r"\bmicrocontroller\b", r"\barduino\b", r"\braspberry[\s-]pi\b"],
        "category": "Hardware / Embedded",
        "weight": 0.9
    }
}


# ── Location Aliases & Tier-1 Cities ────────────────────────────────
LOCATION_ALIASES: Dict[str, List[str]] = {
    "pune": ["pune", "pcmc", "pimpri", "chinchwad", "baner", "hinjewadi", "kharadi", "viman nagar"],
    "mumbai": ["mumbai", "bombay", "navi mumbai", "thane", "dombivli", "kalyan"],
    "bangalore": ["bangalore", "bengaluru", "banglore", "whitefield", "koramangala", "indiranagar"],
    "hyderabad": ["hyderabad", "secunderabad", "hyd", "gachibowli", "hitec city"],
    "delhi / ncr": ["delhi", "new delhi", "ncr", "noida", "gurgaon", "gurugram", "ghaziabad"],
    "indore": ["indore"],
    "nagpur": ["nagpur"],
    "chennai": ["chennai", "madras"],
    "ahmedabad": ["ahmedabad", "gandhinagar"],
    "kolkata": ["kolkata", "calcutta"],
    "jaipur": ["jaipur"],
    "remote": ["remote", "work from home", "wfh", "anywhere in india", "pan india"]
}


# ── Default Candidate Profile ────────────────────────────────────────
DEFAULT_CANDIDATE_PROFILE: Dict[str, Any] = {
    "name": "Lalit Chaudhari",
    "email": "lalitchoudhari851@gmail.com",
    "headline": "AI/ML Engineer & GenAI Developer (Fresher)",
    "skills": [
        "Python",
        "RAG",
        "LLM",
        "LangChain",
        "GenAI",
        "Machine Learning",
        "Deep Learning",
        "PyTorch",
        "NLP",
        "FastAPI",
        "SQL",
        "Docker",
        "Agentic AI"
    ],
    "target_roles": [
        "AI/ML Engineer Intern",
        "GenAI Developer Intern",
        "LLM Engineer Intern",
        "Machine Learning Intern",
        "Data Science Intern"
    ],
    "experience_level": "Fresher / Intern",  # "Fresher / Intern", "0-1 Years", "1-3 Years"
    "preferred_locations": ["Pune", "Bangalore", "Remote", "Mumbai", "Hyderabad"],
    "preferred_work_modes": ["Remote", "Hybrid", "On-site"]
}


def extract_skills_from_text(text: str) -> Set[str]:
    """
    Extracts canonical skill names from any job text snippet using regex rules.
    """
    if not text:
        return set()
    
    clean_text = text.lower()
    found_skills = set()

    for skill_name, meta in SKILLS_TAXONOMY.items():
        for pattern in meta["aliases"]:
            if re.search(pattern, clean_text, re.IGNORECASE):
                found_skills.add(skill_name)
                break

    return found_skills


def infer_job_required_skills(job: Dict[str, Any]) -> Set[str]:
    """
    Extracts both explicit and domain-implied skills from a job listing.
    """
    role = job.get("role") or ""
    desc = job.get("description") or ""
    search_kw = job.get("search_keyword") or ""
    comp = job.get("company") or ""

    composite_text = f"{role} {desc} {search_kw} {comp}".lower()
    skills = extract_skills_from_text(composite_text)

    # Contextual inference for common AI/ML job roles
    role_lower = role.lower()
    if any(k in role_lower for k in ["genai", "generative ai", "llm", "rag", "prompt"]):
        skills.update({"GenAI", "Python", "LLM"})
        if "rag" in role_lower:
            skills.add("RAG")
        if "agent" in role_lower:
            skills.add("Agentic AI")

    if any(k in role_lower for k in ["machine learning", "ml intern", "ml engineer"]):
        skills.update({"Machine Learning", "Python"})

    if any(k in role_lower for k in ["deep learning", "computer vision", "nlp"]):
        skills.update({"Deep Learning", "Python"})
        if "vision" in role_lower:
            skills.add("Computer Vision")
        if "nlp" in role_lower or "language" in role_lower:
            skills.add("NLP")

    if "python" in role_lower:
        skills.add("Python")

    if "data science" in role_lower or "data scientist" in role_lower:
        skills.update({"Data Science", "Python", "Machine Learning"})

    if "embedded" in role_lower or "iot" in role_lower:
        skills.update({"Embedded Systems", "C++"})

    # If still empty, infer baseline AI/ML expectation
    if not skills:
        skills.update({"Python", "Machine Learning"})

    return skills


def compute_skill_alignment(candidate_skills: Set[str], job_skills: Set[str]) -> Tuple[float, List[str], List[str]]:
    """
    Calculates skill matching score, strong matches, and missing skills.
    Returns: (score_0_to_100, strong_matches, missing_skills)
    """
    candidate_skills_lower = {s.lower(): s for s in candidate_skills}
    job_skills_lower = {s.lower(): s for s in job_skills}

    matched = []
    missing = []

    total_weight = 0.0
    matched_weight = 0.0

    for j_lower, j_name in job_skills_lower.items():
        w = SKILLS_TAXONOMY.get(j_name, {}).get("weight", 1.0)
        total_weight += w
        if j_lower in candidate_skills_lower:
            matched.append(j_name)
            matched_weight += w
        else:
            missing.append(j_name)

    if total_weight > 0:
        base_score = (matched_weight / total_weight) * 100.0
    else:
        base_score = 75.0

    # Small bonus for candidate possessing extra complementary advanced skills
    extra_relevant = 0
    for c_lower, c_name in candidate_skills_lower.items():
        if c_lower not in job_skills_lower and c_name in ["Python", "FastAPI", "Docker", "SQL", "Git"]:
            extra_relevant += 1

    bonus = min(10.0, extra_relevant * 2.5)
    final_score = min(100.0, base_score + bonus)

    # Sort matches by canonical importance
    matched.sort(key=lambda s: SKILLS_TAXONOMY.get(s, {}).get("weight", 1.0), reverse=True)
    missing.sort(key=lambda s: SKILLS_TAXONOMY.get(s, {}).get("weight", 1.0), reverse=True)

    return final_score, matched, missing


def compute_role_alignment(job_role: str, target_roles: List[str]) -> float:
    """
    Measures semantic role alignment (0 to 100).
    """
    if not job_role:
        return 50.0

    jr = job_role.lower()

    # Direct match with candidate target roles
    for tr in target_roles:
        tr_lower = tr.lower()
        if tr_lower in jr or jr in tr_lower:
            return 100.0

    # Concept cluster alignments
    genai_terms = ["genai", "generative ai", "llm", "rag", "agentic", "prompt engineering", "langchain"]
    ml_terms = ["machine learning", "ml", "data science", "deep learning", "nlp", "computer vision"]
    sw_terms = ["python", "software engineer", "developer", "backend"]

    is_job_genai = any(t in jr for t in genai_terms)
    is_job_ml = any(t in jr for t in ml_terms)
    is_job_sw = any(t in jr for t in sw_terms)

    candidate_str = " ".join(target_roles).lower()
    is_cand_genai = any(t in candidate_str for t in genai_terms)
    is_cand_ml = any(t in candidate_str for t in ml_terms)

    if is_job_genai and is_cand_genai:
        return 96.0
    if is_job_ml and is_cand_ml:
        return 95.0
    if (is_job_genai and is_cand_ml) or (is_job_ml and is_cand_genai):
        return 88.0
    if is_job_sw and (is_cand_genai or is_cand_ml):
        return 82.0
    if "intern" in jr or "trainee" in jr or "fresher" in jr:
        return 78.0

    return 60.0


def compute_experience_alignment(job: Dict[str, Any], candidate_exp: str) -> float:
    """
    Determines experience suitability.
    """
    role = (job.get("role") or "").lower()
    desc = (job.get("description") or "").lower()
    full_text = f"{role} {desc}"

    # Explicit intern / fresher indicators
    is_intern = bool(re.search(r"\b(intern|internship|fresher|freshers|trainee|entry[\s-]level|graduate|student)\b", full_text, re.I))
    is_senior = bool(re.search(r"\b(senior|lead|principal|staff|\d+\+?\s*years?)\b", full_text, re.I))

    if "fresher" in candidate_exp.lower() or "intern" in candidate_exp.lower():
        if is_intern and not is_senior:
            return 100.0
        if not is_senior:
            return 90.0
        return 40.0

    # 1-3 years profile
    if is_senior:
        return 65.0
    return 95.0


def compute_location_alignment(job_location: str, preferred_locations: List[str]) -> Tuple[float, str]:
    """
    Calculates location affinity (0 to 100).
    """
    if not job_location:
        return 85.0, "India / Flexible"

    loc_lower = job_location.lower()

    # Remote check
    is_remote = any(r in loc_lower for r in ["remote", "work from home", "wfh", "anywhere"])
    prefers_remote = any("remote" in p.lower() or "home" in p.lower() for p in preferred_locations)

    if is_remote and prefers_remote:
        return 100.0, "Remote / Work From Home"

    # Preferred cities check
    for pref in preferred_locations:
        pref_key = pref.lower().split(",")[0].strip()
        aliases = LOCATION_ALIASES.get(pref_key, [pref_key])
        if any(a in loc_lower for a in aliases):
            return 100.0, pref

    if is_remote:
        return 90.0, "Remote option available"

    # Non-preferred location
    return 45.0, job_location


def compute_work_mode_alignment(job_type: str, preferred_modes: List[str]) -> float:
    """
    Checks work mode compatibility (0 to 100).
    """
    if not job_type or not preferred_modes:
        return 85.0

    jt = job_type.lower()
    preferred_lower = [m.lower() for m in preferred_modes]

    if "any" in preferred_lower:
        return 100.0

    for pref in preferred_lower:
        if pref in jt or jt in pref:
            return 100.0

    # Hybrid is generally compatible with on-site or remote
    if "hybrid" in jt and ("remote" in preferred_lower or "on-site" in preferred_lower):
        return 85.0

    return 60.0


def compute_text_semantic_similarity(candidate_summary: str, job_text: str) -> float:
    """
    Calculates lexical & concept cosine similarity using character and word n-grams.
    """
    def tokenize(s: str) -> List[str]:
        return [w for w in re.findall(r"\b[a-zA-Z0-9_\-\.\+]{2,}\b", s.lower()) if len(w) > 1]

    cand_tokens = tokenize(candidate_summary)
    job_tokens = tokenize(job_text)

    if not cand_tokens or not job_tokens:
        return 65.0

    cand_set = set(cand_tokens)
    job_set = set(job_tokens)

    intersection = len(cand_set.intersection(job_set))
    union = len(cand_set.union(job_set))

    jaccard = (intersection / union) if union > 0 else 0.0

    # Character bigram similarity for fuzzy technical terms (e.g. 'genai', 'langchain')
    def get_bigrams(tokens: List[str]) -> Set[str]:
        bigrams = set()
        for t in tokens:
            for i in range(len(t) - 1):
                bigrams.add(t[i:i+2])
        return bigrams

    cand_bigrams = get_bigrams(cand_tokens)
    job_bigrams = get_bigrams(job_tokens)
    bi_intersection = len(cand_bigrams.intersection(job_bigrams))
    bi_union = len(cand_bigrams.union(job_bigrams))
    bi_jaccard = (bi_intersection / bi_union) if bi_union > 0 else 0.0

    combined = (jaccard * 0.5) + (bi_jaccard * 0.5)
    scaled = min(100.0, combined * 180.0)
    return max(40.0, scaled)


def match_job_to_profile(job: Dict[str, Any], candidate_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Main entry point: Computes an explainable, deterministic match score (0 to 100%)
    for a given job against a candidate profile.
    """
    profile = candidate_profile or DEFAULT_CANDIDATE_PROFILE

    candidate_skills = set(profile.get("skills") or DEFAULT_CANDIDATE_PROFILE["skills"])
    target_roles = profile.get("target_roles") or DEFAULT_CANDIDATE_PROFILE["target_roles"]
    exp_level = profile.get("experience_level") or DEFAULT_CANDIDATE_PROFILE["experience_level"]
    preferred_locs = profile.get("preferred_locations") or DEFAULT_CANDIDATE_PROFILE["preferred_locations"]
    preferred_modes = profile.get("preferred_work_modes") or DEFAULT_CANDIDATE_PROFILE["preferred_work_modes"]

    # 1. Skills Matching
    job_required_skills = infer_job_required_skills(job)
    skills_score, strong_matches, missing_skills = compute_skill_alignment(candidate_skills, job_required_skills)

    # 2. Role Alignment
    role_score = compute_role_alignment(job.get("role") or "", target_roles)

    # 3. Experience Alignment
    exp_score = compute_experience_alignment(job, exp_level)

    # 4. Location Affinity
    loc_score, loc_label = compute_location_alignment(job.get("location") or "", preferred_locs)

    # 5. Work Mode Compatibility
    mode_score = compute_work_mode_alignment(job.get("type") or "", preferred_modes)

    # 6. Semantic Concept Similarity
    cand_summary = f"{' '.join(target_roles)} {' '.join(candidate_skills)} {exp_level}"
    job_full_text = f"{job.get('role', '')} {job.get('company', '')} {job.get('description', '')} {job.get('location', '')}"
    sem_score = compute_text_semantic_similarity(cand_summary, job_full_text)

    # Weighted composite score
    weights = {
        "skills": 0.35,
        "role": 0.25,
        "semantic": 0.15,
        "location": 0.10,
        "work_mode": 0.08,
        "experience": 0.07
    }

    raw_score = (
        (skills_score * weights["skills"]) +
        (role_score * weights["role"]) +
        (sem_score * weights["semantic"]) +
        (loc_score * weights["location"]) +
        (mode_score * weights["work_mode"]) +
        (exp_score * weights["experience"])
    )

    final_pct = int(round(raw_score))
    final_pct = max(35, min(99, final_pct))

    # Match Grade Classification
    if final_pct >= 85:
        match_grade = "Exceptional Match"
        grade_color = "#059669"  # Emerald
    elif final_pct >= 75:
        match_grade = "Strong Match"
        grade_color = "#0284C7"  # Sky blue
    elif final_pct >= 60:
        match_grade = "Moderate Match"
        grade_color = "#D97706"  # Amber
    else:
        match_grade = "Low Alignment"
        grade_color = "#6B7280"  # Gray

    # Construct explainable summary bullet points
    explanations = []
    if strong_matches:
        explanations.append(f"Strong overlap on {', '.join(strong_matches[:3])}.")
    if loc_score >= 90:
        explanations.append(f"Matches preferred location ({loc_label}).")
    if exp_score >= 90:
        explanations.append("Role is tailored for freshers & interns.")
    if missing_skills:
        explanations.append(f"Missing mentions of {', '.join(missing_skills[:2])}.")

    summary_text = " ".join(explanations)

    return {
        "score": final_pct,
        "match_percentage": f"{final_pct}% Match",
        "match_grade": match_grade,
        "grade_color": grade_color,
        "strong_matches": strong_matches,
        "missing_skills": missing_skills,
        "job_skills": sorted(list(job_required_skills)),
        "breakdown": {
            "skills": int(round(skills_score)),
            "role": int(round(role_score)),
            "semantic": int(round(sem_score)),
            "location": int(round(loc_score)),
            "work_mode": int(round(mode_score)),
            "experience": int(round(exp_score))
        },
        "summary": summary_text
    }


def enrich_jobs_with_matching(jobs: List[Dict[str, Any]], candidate_profile: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Enriches a list of jobs with reproducible semantic match profiles.
    """
    profile = candidate_profile or load_candidate_profile()
    for job in jobs:
        match_res = match_job_to_profile(job, profile)
        job["match"] = match_res
        job["match_score"] = match_res["score"]
        job["strong_matches"] = match_res["strong_matches"]
        job["missing_skills"] = match_res["missing_skills"]
    return jobs


def get_available_skills() -> List[Dict[str, str]]:
    """
    Returns a sorted list of all skills in taxonomy with categories.
    """
    skills = []
    for name, data in SKILLS_TAXONOMY.items():
        skills.append({
            "name": name,
            "category": data.get("category", "General")
        })
    skills.sort(key=lambda s: s["name"])
    return skills


def load_candidate_profile() -> Dict[str, Any]:
    """
    Loads saved candidate profile or returns default candidate profile.
    """
    if os.path.exists(PROFILE_FILE):
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**DEFAULT_CANDIDATE_PROFILE, **data}
        except Exception as e:
            print(f"Error loading candidate profile: {e}")
    return dict(DEFAULT_CANDIDATE_PROFILE)


def save_candidate_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Saves updated candidate profile to disk.
    """
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        current = load_candidate_profile()
        updated = {**current, **data}
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=2, ensure_ascii=False)
        return updated
    except Exception as e:
        print(f"Error saving candidate profile: {e}")
        return {**DEFAULT_CANDIDATE_PROFILE, **data}

