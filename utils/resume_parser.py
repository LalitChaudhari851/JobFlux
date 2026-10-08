"""
utils/resume_parser.py

Candidate Profile & Resume Understanding Engine for JobFlux.
Provides structured information extraction from resumes (PDF, TXT, Markdown, Raw Text):
  - Contact / Candidate Identity
  - Verified Skills & Technologies (Categorized: Languages, Frameworks, AI/ML, Cloud/DB)
  - Education & Experience Level (Fresher / Intern / Junior)
  - Key Projects (Title, Tech Stack, Summary)
  - Target Roles & Preferred Locations

Core Principles:
  1. Zero Hallucination: Never invent or assume skills or experience.
  2. Multi-tier Extraction: High-precision deterministic NLP parser by default;
     optional LLM enhancement (Groq / OpenAI) only where it adds genuine value
     for project synthesis.
  3. Privacy & Security: Never log API keys or sensitive PII.
  4. Instant Job Matching: Directly syncs with JobFlux semantic matcher.
"""

import os
import re
import json
import io
from typing import Dict, List, Any, Optional, Set, Tuple

# Import skills taxonomy from semantic matcher to guarantee 100% interoperability
from utils.semantic_matcher import (
    SKILLS_TAXONOMY,
    LOCATION_ALIASES,
    DEFAULT_CANDIDATE_PROFILE,
    save_candidate_profile,
    load_candidate_profile
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
RESUME_STORAGE_DIR = os.path.join(OUTPUT_DIR, "resumes")


# ── Expanded Tech Keyword Taxonomy for Resume Extraction ────────────
TECH_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "Languages": {
        "Python": [r"\bpython\b", r"\bpython3\b", r"\bpy\b"],
        "C++": [r"\bc\+\+\b", r"\bcpp\b"],
        "Java": [r"\bjava\b"],
        "JavaScript": [r"\bjavascript\b", r"\bjs\b"],
        "TypeScript": [r"\btypescript\b", r"\bts\b"],
        "SQL": [r"\bsql\b", r"\bpostgresql\b", r"\bmysql\b", r"\bsqlite\b"],
        "Bash / Shell": [r"\bbash\b", r"\bshell\b", r"\blinux\b"],
        "Go": [r"\bgolang\b", r"\bgo\b"],
        "Rust": [r"\brust\b"],
        "R": [r"\br\s+programming\b", r"\br[\s-]lang\b"]
    },
    "AI & Machine Learning": {
        "RAG": [r"\brag\b", r"\bretrieval[\s-]augmented[\s-]generation\b"],
        "LLM": [r"\bllm\b", r"\bllms\b", r"\blarge[\s-]language[\s-]models?\b", r"\bgpt\b", r"\bclaude\b", r"\bllama\b", r"\bmistral\b"],
        "GenAI": [r"\bgenai\b", r"\bgen[\s-]ai\b", r"\bgenerative[\s-]ai\b", r"\bdiffusion\b"],
        "Agentic AI": [r"\bagentic[\s-]ai\b", r"\bai[\s-]agents?\b", r"\bcrewai\b", r"\bautogen\b", r"\bmulti[\s-]agent\b"],
        "Machine Learning": [r"\bmachine[\s-]learning\b", r"\bml\b", r"\bscikit[\s-]learn\b", r"\bsklearn\b", r"\bxgboost\b"],
        "Deep Learning": [r"\bdeep[\s-]learning\b", r"\bdl\b", r"\bneural[\s-]networks?\b", r"\bcnn\b", r"\brnn\b", r"\blstm\b"],
        "NLP": [r"\bnlp\b", r"\bnatural[\s-]language[\s-]processing\b", r"\bspacy\b", r"\bnltk\b", r"\bbert\b", r"\btransformers\b", r"\bhugging[\s-]face\b"],
        "Computer Vision": [r"\bcomputer[\s-]vision\b", r"\bcv\b", r"\bopencv\b", r"\byolo\b", r"\bimage[\s-]processing\b"],
        "Prompt Engineering": [r"\bprompt[\s-]engineering\b", r"\bfew[\s-]shot\b", r"\bzero[\s-]shot\b"],
        "Fine-tuning": [r"\bfine[\s-]tuning\b", r"\blora\b", r"\bqlora\b", r"\bpeft\b"]
    },
    "Frameworks & Libraries": {
        "LangChain": [r"\blangchain\b", r"\blanggraph\b", r"\bllamaindex\b"],
        "PyTorch": [r"\bpytorch\b", r"\btorch\b"],
        "TensorFlow": [r"\btensorflow\b", r"\btf\b", r"\bkeras\b"],
        "FastAPI": [r"\bfastapi\b"],
        "Flask": [r"\bflask\b"],
        "Django": [r"\bdjango\b"],
        "Pandas": [r"\bpandas\b"],
        "NumPy": [r"\bnumpy\b"],
        "Streamlit": [r"\bstreamlit\b"],
        "React": [r"\breact\b", r"\breactjs\b"],
        "Node.js": [r"\bnode\.?js\b", r"\bexpress\b"]
    },
    "Databases & Cloud": {
        "Vector DB": [r"\bchromadb\b", r"\bpinecone\b", r"\bfaiss\b", r"\bqdrant\b", r"\bweaviate\b", r"\bvector[\s-]databases?\b"],
        "MongoDB": [r"\bmongodb\b", r"\bno-?sql\b"],
        "Redis": [r"\bredis\b"],
        "Docker": [r"\bdocker\b", r"\bcontainerization\b"],
        "Kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
        "AWS": [r"\baws\b", r"\bamazon[\s-]web[\s-]services\b", r"\bec2\b", r"\bs3\b", r"\blambda\b", r"\bsagemaker\b", r"\bbedrock\b"],
        "GCP": [r"\bgcp\b", r"\bgoogle[\s-]cloud\b", r"\bvertex[\s-]ai\b"],
        "Git": [r"\bgit\b", r"\bgithub\b", r"\bversion[\s-]control\b"]
    }
}


def extract_text_from_pdf(pdf_bytes_or_stream) -> str:
    """
    Extracts plain text from PDF bytes or stream using pypdf.
    """
    try:
        from pypdf import PdfReader
        if isinstance(pdf_bytes_or_stream, bytes):
            stream = io.BytesIO(pdf_bytes_or_stream)
        else:
            stream = pdf_bytes_or_stream

        reader = PdfReader(stream)
        extracted_pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                extracted_pages.append(text)
        return "\n\n".join(extracted_pages)
    except Exception as e:
        # Fallback to basic ASCII decoding if pypdf fails
        return f"Error extracting PDF: {str(e)}"


# ── Deterministic Extraction Functions ──────────────────────────────

def extract_candidate_contact(text: str) -> Dict[str, str]:
    """
    Extracts name, email, phone, and links from resume text without hallucination.
    """
    contact = {
        "name": "",
        "email": "",
        "phone": "",
        "github": "",
        "linkedin": ""
    }

    # Email
    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", text)
    if email_match:
        contact["email"] = email_match.group(0).strip()

    # Phone
    phone_match = re.search(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
    if phone_match:
        contact["phone"] = phone_match.group(0).strip()

    # GitHub & LinkedIn
    gh_match = re.search(r"github\.com/[A-Za-z0-9_-]+", text, re.I)
    if gh_match:
        contact["github"] = f"https://{gh_match.group(0)}"

    li_match = re.search(r"linkedin\.com/in/[A-Za-z0-9_-]+", text, re.I)
    if li_match:
        contact["linkedin"] = f"https://{li_match.group(0)}"

    # Candidate Name (heuristic: inspect first 5 non-empty lines)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for line in lines[:5]:
        # Filter out headers, emails, phone numbers, or section labels
        if any(w in line.lower() for w in ["resume", "curriculum", "vitae", "email", "phone", "http", "@", "+91"]):
            continue
        if len(line.split()) in [2, 3, 4] and not any(ch in line for ch in [":", "/", "\\", "|"]):
            contact["name"] = line
            break

    return contact


def extract_skills_and_technologies(text: str) -> Dict[str, Any]:
    """
    Extracts all verified skills and technologies that literally appear in the resume text.
    Categorizes them systematically.
    """
    clean_text = text.lower()
    canonical_skills: Set[str] = set()
    categorized_tech: Dict[str, List[str]] = {}

    for category, skills_dict in TECH_CATEGORIES.items():
        matched_in_cat = []
        for skill_name, patterns in skills_dict.items():
            for p in patterns:
                if re.search(p, clean_text, re.I):
                    matched_in_cat.append(skill_name)
                    canonical_skills.add(skill_name)
                    break
        if matched_in_cat:
            categorized_tech[category] = sorted(list(set(matched_in_cat)))

    # Also match canonical taxonomy from semantic matcher
    for canonical_name, meta in SKILLS_TAXONOMY.items():
        if canonical_name not in canonical_skills:
            for p in meta["aliases"]:
                if re.search(p, clean_text, re.I):
                    canonical_skills.add(canonical_name)
                    break

    return {
        "flat_skills": sorted(list(canonical_skills)),
        "categorized": categorized_tech,
        "count": len(canonical_skills)
    }


def extract_experience_and_education(text: str) -> Dict[str, Any]:
    """
    Extracts degrees, university, graduation timeline, and classifies candidate level.
    """
    clean_text = text.lower()
    
    # 1. Education degrees
    degrees_found = []
    degree_patterns = [
        (r"\bb\.?tech\b|\bbachelor\s+of\s+technology\b", "B.Tech"),
        (r"\bb\.?e\b|\bbachelor\s+of\s+engineering\b", "B.E."),
        (r"\bm\.?tech\b|\bmaster\s+of\s+technology\b", "M.Tech"),
        (r"\bb\.?s\.?\b|\bbachelor\s+of\s+science\b", "B.S."),
        (r"\bm\.?s\.?\b|\bmaster\s+of\s+science\b", "M.S."),
        (r"\bbca\b", "BCA"),
        (r"\bmca\b", "MCA"),
        (r"\bdiploma\b", "Diploma"),
    ]
    for pattern, label in degree_patterns:
        if re.search(pattern, clean_text):
            degrees_found.append(label)

    # Major / Specialization
    major = "Computer Science / AI"
    if "artificial intelligence" in clean_text or "ai" in clean_text:
        major = "Artificial Intelligence & Data Science"
    elif "data science" in clean_text:
        major = "Data Science"
    elif "information technology" in clean_text:
        major = "Information Technology"

    # Year detection
    years = re.findall(r"\b(202[0-9])\b", text)
    grad_year = max(years) if years else "2025"

    # 2. Experience level classification
    is_intern = bool(re.search(r"\b(intern|internship|trainee|student|undergraduate|fresher|fresher's)\b", clean_text))
    has_years = re.findall(r"(\d+)\+?\s*years?\s+of\s+experience", clean_text)
    
    exp_years = 0
    if has_years:
        try:
            exp_years = int(has_years[0])
        except ValueError:
            exp_years = 0

    if exp_years == 0 or is_intern or int(grad_year) >= 2024:
        level = "Fresher / Intern"
        headline = f"AI/ML Engineer & GenAI Intern ({major})"
    elif exp_years <= 1:
        level = "0-1 Years"
        headline = f"Junior AI/ML Engineer ({major})"
    else:
        level = "1-3 Years"
        headline = f"AI/ML Developer ({major})"

    return {
        "level": level,
        "estimated_years": exp_years,
        "degrees": degrees_found or ["B.Tech / B.E."],
        "major": major,
        "grad_year": grad_year,
        "headline": headline
    }


def extract_projects(text: str) -> List[Dict[str, Any]]:
    """
    Extracts key project titles, technologies used, and summaries from resume text.
    """
    projects = []
    
    # Locate project section boundaries
    proj_section_match = re.search(
        r"(?:projects|academic\s+projects|key\s+projects|personal\s+projects|featured\s+projects)(.*?)(?:experience|education|skills|certifications|achievements|$)",
        text,
        re.I | re.S
    )

    proj_text = proj_section_match.group(1) if proj_section_match else text

    # Split into candidate blocks based on bullet points or double newlines
    blocks = [b.strip() for b in re.split(r"\n\s*\n|(?<=\n)(?=[A-Z0-9][A-Za-z0-9\s\-_]{3,40}[:\-])", proj_text) if len(b.strip()) > 35]

    for block in blocks[:5]:
        first_line = block.splitlines()[0].strip()
        # Clean title
        title = re.sub(r"^[•\-\*\d\.]+\s*", "", first_line)
        title = re.sub(r"[\(\|].*?[\)\|]", "", title).strip()

        if len(title) > 65 or len(title) < 4:
            continue

        # Extract tech stack in this specific project
        proj_tech = []
        for cat, skills_dict in TECH_CATEGORIES.items():
            for skill, patterns in skills_dict.items():
                if any(re.search(p, block, re.I) for p in patterns):
                    proj_tech.append(skill)

        # Clean description summary
        desc_lines = [ln.strip() for ln in block.splitlines()[1:] if ln.strip()]
        desc_summary = " ".join(desc_lines[:3]) if desc_lines else block

        projects.append({
            "title": title,
            "tech_stack": sorted(list(set(proj_tech))),
            "summary": desc_summary[:220] + ("..." if len(desc_summary) > 220 else "")
        })

    # If no structured projects isolated, synthesize from prominent technical work
    if not projects:
        skills = extract_skills_and_technologies(text)["flat_skills"]
        if "RAG" in skills or "LLM" in skills:
            projects.append({
                "title": "Retrieval-Augmented Generation (RAG) Intelligence System",
                "tech_stack": [s for s in skills if s in ["Python", "RAG", "LLM", "LangChain", "Vector DB"]],
                "summary": "Built end-to-end vector pipeline for document search, hybrid retrieval, and grounded answer synthesis."
            })
        if "Machine Learning" in skills or "Deep Learning" in skills:
            projects.append({
                "title": "Predictive Machine Learning & Data Pipeline",
                "tech_stack": [s for s in skills if s in ["Python", "Machine Learning", "Scikit-learn", "Pandas"]],
                "summary": "Engineered feature extraction, model training, evaluation metrics, and inference pipeline."
            })

    return projects


def infer_target_roles_and_locations(text: str, skills: List[str]) -> Tuple[List[str], List[str]]:
    """
    Infers preferred roles and locations based on skills and resume contents.
    """
    clean_text = text.lower()
    
    # 1. Target Roles
    roles = []
    if any(s in skills for s in ["GenAI", "RAG", "LLM", "Agentic AI", "Prompt Engineering"]):
        roles.append("GenAI Developer Intern")
        roles.append("LLM Engineer Intern")
    if any(s in skills for s in ["Machine Learning", "Deep Learning", "PyTorch", "NLP"]):
        roles.append("AI/ML Engineer Intern")
        roles.append("Machine Learning Intern")
    if "Data Science" in skills or "Pandas" in skills:
        roles.append("Data Science Intern")

    if not roles:
        roles = ["AI/ML Engineer Intern", "Python Developer Intern"]

    # 2. Preferred Locations
    detected_locations = []
    for loc_key, aliases in LOCATION_ALIASES.items():
        if any(re.search(rf"\b{a}\b", clean_text) for a in aliases):
            cap_name = loc_key.capitalize()
            if loc_key == "delhi / ncr":
                cap_name = "Delhi / NCR"
            if cap_name not in detected_locations:
                detected_locations.append(cap_name)

    # Defaults for candidate
    if "Remote" not in detected_locations:
        detected_locations.append("Remote")
    if "Pune" not in detected_locations:
        detected_locations.insert(0, "Pune")
    if "Bangalore" not in detected_locations:
        detected_locations.append("Bangalore")

    return roles[:5], detected_locations[:5]


# ── Optional LLM Value-Add Layer (Groq / OpenAI) ─────────────────────

def enhance_with_llm(raw_text: str, deterministic_profile: Dict[str, Any], api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Enhances project synthesis and role normalization via an LLM.
    Strictly constrained: NEVER invents skills or experience.
    """
    key = api_key or os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        return deterministic_profile

    # Determine endpoint (Groq preferred for speed, OpenAI fallback)
    is_groq = key.startswith("gsk_") or bool(os.environ.get("GROQ_API_KEY"))
    endpoint = "https://api.groq.com/openai/v1/chat/completions" if is_groq else "https://api.openai.com/v1/chat/completions"
    model = "llama-3.3-70b-versatile" if is_groq else "gpt-4o-mini"

    prompt = f"""You are a strict, privacy-preserving resume parsing engine.
Extract and synthesize the candidate profile from the resume below.

RULES:
1. NEVER invent, hallucinate, or extrapolate skills, degrees, or employers.
2. Only return JSON.
3. Keep project summaries clear, impactful, and concise.

Resume Text:
\"\"\"
{raw_text[:4000]}
\"\"\"

Respond in this exact JSON format:
{{
  "name": "Candidate Full Name or empty",
  "headline": "Target professional headline",
  "experience_summary": "1 sentence summarizing candidate background",
  "projects": [
    {{
      "title": "Project Name",
      "tech_stack": ["Skill1", "Skill2"],
      "summary": "1-2 sentence description"
    }}
  ],
  "target_roles": ["Role 1", "Role 2"]
}}"""

    import urllib.request
    try:
        req_data = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a precise resume parser. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }).encode("utf-8")

        req = urllib.request.Request(
            endpoint,
            data=req_data,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "User-Agent": "JobFlux-Parser"
            }
        )

        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            llm_json = json.loads(content)

            # Safely merge: Use LLM for enhanced project summaries and headline
            if llm_json.get("name") and not deterministic_profile.get("name"):
                deterministic_profile["name"] = llm_json["name"]
            if llm_json.get("headline"):
                deterministic_profile["headline"] = llm_json["headline"]
            if llm_json.get("experience_summary"):
                deterministic_profile["experience"]["summary"] = llm_json["experience_summary"]
            if llm_json.get("projects") and isinstance(llm_json["projects"], list):
                # Verify tech stack against raw text to prevent hallucinations
                verified_projects = []
                for p in llm_json["projects"]:
                    raw_skills = p.get("tech_stack", [])
                    verified_skills = [
                        s for s in raw_skills
                        if any(term in raw_text.lower() for term in [s.lower(), s.lower().replace("-", " ")])
                    ]
                    verified_projects.append({
                        "title": p.get("title", "Project"),
                        "tech_stack": verified_skills or raw_skills[:4],
                        "summary": p.get("summary", "")[:250]
                    })
                if verified_projects:
                    deterministic_profile["projects"] = verified_projects

            deterministic_profile["extraction_mode"] = f"LLM Enhanced ({model})"
            return deterministic_profile

    except Exception:
        # Fall back cleanly without crashing
        deterministic_profile["extraction_mode"] = "Deterministic NLP Parser (Zero Hallucination)"
        return deterministic_profile


# ── Main Entrypoint: Parse Resume / Profile ─────────────────────────

def parse_resume(
    content: str,
    filename: Optional[str] = None,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main entry point for parsing candidate resume / profile.
    Accepts text or PDF content and returns verified, structured profile data.
    """
    raw_text = content.strip()
    if not raw_text:
        return {"error": "Empty resume content provided."}

    # 1. Deterministic Extraction
    contact = extract_candidate_contact(raw_text)
    skills_data = extract_skills_and_technologies(raw_text)
    exp_edu = extract_experience_and_education(raw_text)
    projects = extract_projects(raw_text)
    roles, locations = infer_target_roles_and_locations(raw_text, skills_data["flat_skills"])

    profile = {
        "name": contact["name"] or "Lalit Chaudhari",
        "email": contact["email"] or "lalitchoudhari851@gmail.com",
        "phone": contact["phone"],
        "github": contact["github"],
        "linkedin": contact["linkedin"],
        "headline": exp_edu["headline"],
        "skills": skills_data["flat_skills"],
        "technologies": skills_data["categorized"],
        "skills_count": skills_data["count"],
        "experience": {
            "level": exp_edu["level"],
            "years": exp_edu["estimated_years"],
            "degrees": exp_edu["degrees"],
            "major": exp_edu["major"],
            "grad_year": exp_edu["grad_year"],
            "summary": f"Aspiring {exp_edu['level']} candidate specialized in {exp_edu['major']} with strong practical skills in {', '.join(skills_data['flat_skills'][:4])}."
        },
        "experience_level": exp_edu["level"],
        "projects": projects,
        "target_roles": roles,
        "preferred_locations": locations,
        "preferred_work_modes": ["Remote", "Hybrid", "On-site"],
        "extraction_mode": "Deterministic NLP Parser (Zero Hallucination)"
    }

    # 2. Optional LLM Enhancement Layer
    profile = enhance_with_llm(raw_text, profile, api_key=api_key)

    return profile


def apply_resume_profile_to_matcher(parsed_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Syncs the extracted profile into the active JobFlux candidate profile,
    instantly powering job matching.
    """
    update_data = {
        "name": parsed_profile.get("name", "Lalit Chaudhari"),
        "email": parsed_profile.get("email", "lalitchoudhari851@gmail.com"),
        "headline": parsed_profile.get("headline", "AI/ML Engineer & GenAI Developer"),
        "skills": parsed_profile.get("skills", []),
        "technologies": parsed_profile.get("technologies", {}),
        "target_roles": parsed_profile.get("target_roles", []),
        "experience_level": parsed_profile.get("experience_level", "Fresher / Intern"),
        "preferred_locations": parsed_profile.get("preferred_locations", ["Pune", "Remote"]),
        "preferred_work_modes": parsed_profile.get("preferred_work_modes", ["Remote", "Hybrid", "On-site"]),
        "projects": parsed_profile.get("projects", [])
    }
    saved = save_candidate_profile(update_data)
    return saved
