"""
server.py
Lightweight multi-threaded HTTP server for AI/ML Internship Dashboard.
Serves static dashboard assets and dynamic REST APIs querying the actual
scraper database (output/scraper.db) and generated CSV outputs.
"""

import os
import sys
import json
import csv
import sqlite3
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from datetime import datetime

PORT = 8000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(BASE_DIR, "dashboard")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DB_PATH = os.path.join(OUTPUT_DIR, "scraper.db")


def load_all_jobs():
    """
    Loads all real job listings from output/job_listings.csv and supplements
    with any job roles tracked in output/all_cold_email_targets.csv and 
    output/cold_email_hiring_now.csv.
    """
    jobs = []
    seen_keys = set()

    # 1. Load from job_listings.csv
    job_csv = os.path.join(OUTPUT_DIR, "job_listings.csv")
    if os.path.exists(job_csv):
        try:
            with open(job_csv, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    comp = (row.get("company_name") or "").strip()
                    title = (row.get("job_title") or "").strip()
                    if not comp and not title:
                        continue
                    key = (comp.lower(), title.lower(), (row.get("source_portal") or "").lower())
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    # Work mode inference
                    loc = row.get("location") or "Remote"
                    loc_lower = loc.lower()
                    if "work from home" in loc_lower or "remote" in loc_lower:
                        work_mode = "Remote"
                    elif "hybrid" in loc_lower:
                        work_mode = "Hybrid"
                    else:
                        work_mode = "On-site"

                    # Format posted date
                    raw_posted = row.get("raw_posted_text") or ""
                    recency = row.get("recency_flag") or ""
                    posted_norm = row.get("normalized_posted_date") or ""
                    posted_display = raw_posted if raw_posted else (recency if recency else "Recent")

                    jobs.append({
                        "id": f"job-{len(jobs)+1}",
                        "company": comp,
                        "role": title,
                        "location": loc,
                        "portal": row.get("source_portal") or "Direct",
                        "type": work_mode,
                        "posted": posted_display,
                        "posted_date": posted_norm,
                        "recency": recency,
                        "website": row.get("company_website") or "",
                        "email": row.get("company_email") or "",
                        "email_priority": row.get("email_priority_score") or "",
                        "application_link": row.get("application_link") or (row.get("company_website") or ""),
                        "description": row.get("description_snippet") or ""
                    })
        except Exception as e:
            print(f"Error loading job_listings.csv: {e}")

    # 2. Augment from cold_email_hiring_now.csv (contains verified companies actively hiring for AI/Tech)
    hiring_csv = os.path.join(OUTPUT_DIR, "cold_email_hiring_now.csv")
    if os.path.exists(hiring_csv):
        try:
            with open(hiring_csv, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    comp = (row.get("Company") or "").strip()
                    hiring_for = (row.get("Hiring For") or "").strip()
                    if not comp or not hiring_for:
                        continue
                    # Split multiple roles if present (e.g. "Machine Learning | AI Agent Development")
                    roles = [r.strip() for r in hiring_for.split("|") if r.strip()]
                    for role in roles:
                        key = (comp.lower(), role.lower(), (row.get("Source") or "").lower())
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)

                        loc = row.get("Location") or "Pune / Remote"
                        loc_lower = loc.lower()
                        work_mode = "Remote" if ("remote" in loc_lower or "home" in loc_lower) else ("Hybrid" if "hybrid" in loc_lower else "On-site")
                        website = row.get("Website") or ""

                        jobs.append({
                            "id": f"job-{len(jobs)+1}",
                            "company": comp,
                            "role": role,
                            "location": loc if loc else "India / Remote",
                            "portal": row.get("Source") or "Internshala",
                            "type": work_mode,
                            "posted": "Active hiring",
                            "posted_date": "",
                            "recency": "Active",
                            "website": website,
                            "email": row.get("Email") or "",
                            "email_priority": row.get("Priority Score") or "90",
                            "application_link": website if website else f"https://internshala.com/internships/keywords-{urllib.parse.quote(role)}",
                            "description": f"Verified hiring role from {comp}. Direct email: {row.get('Email', '')}"
                        })
        except Exception as e:
            print(f"Error loading cold_email_hiring_now.csv: {e}")

    # 3. Augment from all_cold_email_targets.csv
    targets_csv = os.path.join(OUTPUT_DIR, "all_cold_email_targets.csv")
    if os.path.exists(targets_csv):
        try:
            with open(targets_csv, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    roles = (row.get("Job Roles Listed") or "").strip()
                    if not roles:
                        continue
                    comp = (row.get("Company Name") or "").strip()
                    role_list = [r.strip() for r in roles.split("|") if r.strip()]
                    for r_title in role_list:
                        key = (comp.lower(), r_title.lower(), "internshala")
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        loc = (row.get("Location") or "Remote").strip()
                        loc_lower = loc.lower()
                        work_mode = "Remote" if ("remote" in loc_lower or "home" in loc_lower) else ("Hybrid" if "hybrid" in loc_lower else "On-site")
                        website = row.get("Website") or ""
                        source_page = row.get("Source Page") or ""

                        app_link = source_page if (source_page and source_page.startswith("http")) else (website if website else "")

                        jobs.append({
                            "id": f"job-{len(jobs)+1}",
                            "company": comp,
                            "role": r_title,
                            "location": loc if loc else "Remote",
                            "portal": "Internshala",
                            "type": work_mode,
                            "posted": "Verified listing",
                            "posted_date": "",
                            "recency": "Active",
                            "website": website,
                            "email": row.get("Email") or "",
                            "email_priority": row.get("Priority Score") or "80",
                            "application_link": app_link,
                            "description": f"Role listed at {comp}. Contact: {row.get('Email', '')}"
                        })
        except Exception as e:
            print(f"Error loading all_cold_email_targets.csv: {e}")

    return jobs


def load_verified_contacts():
    """
    Loads verified company contacts from SQLite database or company_contacts.csv.
    """
    contacts = []
    contacts_csv = os.path.join(OUTPUT_DIR, "company_contacts.csv")

    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = """
            SELECT c.name as company, c.website, e.email, e.priority_score, 
                   e.mx_status, e.page_found_on, c.category
            FROM companies c
            JOIN emails e ON c.id = e.company_id
            WHERE e.mx_status = 'Valid - MX confirmed'
            ORDER BY e.priority_score DESC, c.name ASC
            """
            rows = cursor.execute(query).fetchall()
            for r in rows:
                contacts.append({
                    "company": r["company"],
                    "website": r["website"] or "",
                    "email": r["email"],
                    "priority_score": r["priority_score"],
                    "mx_status": r["mx_status"],
                    "page_found_on": r["page_found_on"] or "",
                    "category": r["category"] or "Uncategorized"
                })
            conn.close()
            return contacts
        except Exception as e:
            print(f"Error querying SQLite for contacts: {e}")

    if os.path.exists(contacts_csv):
        try:
            with open(contacts_csv, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    email = r.get("Email") or r.get("email")
                    if email and "@" in email:
                        contacts.append({
                            "company": r.get("Company") or r.get("company") or "",
                            "website": r.get("Website") or r.get("website") or "",
                            "email": email,
                            "priority_score": r.get("Priority Score") or r.get("priority_score") or 50,
                            "mx_status": r.get("MX Status") or r.get("mx_status") or "Valid",
                            "page_found_on": r.get("Page Found") or r.get("page_found_on") or "",
                            "category": r.get("Category") or r.get("category") or "Uncategorized"
                        })
        except Exception as e:
            print(f"Error reading contacts CSV: {e}")

    return contacts


class DashboardHandler(SimpleHTTPRequestHandler):
    """Custom request handler serving static dashboard and REST API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DASHBOARD_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_params = urllib.parse.parse_qs(parsed.query)

        # ── API: Stats ──────────────────────────────────────────────
        if path == "/api/stats":
            jobs = load_all_jobs()
            contacts = load_verified_contacts()

            # Dynamic metrics calculation
            remote_count = sum(1 for j in jobs if j.get("type") == "Remote")
            pune_count = sum(1 for j in jobs if "pune" in j.get("location", "").lower())
            blr_count = sum(1 for j in jobs if any(k in j.get("location", "").lower() for k in ["bangalore", "bengaluru"]))
            portals = sorted(list({j.get("portal") for j in jobs if j.get("portal")}))

            db_companies_count = len(contacts)
            if os.path.exists(DB_PATH):
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM companies")
                    db_companies_count = cur.fetchone()[0]
                    conn.close()
                except Exception:
                    pass

            stats = {
                "total_jobs": len(jobs),
                "total_companies": db_companies_count,
                "verified_emails": len(contacts),
                "remote_jobs": remote_count,
                "pune_jobs": pune_count,
                "bangalore_jobs": blr_count,
                "portals": portals,
                "last_updated": datetime.now().strftime("%b %d, %Y %H:%M")
            }
            self.send_json(stats)
            return

        # ── API: Filter Options ─────────────────────────────────────
        if path == "/api/filters":
            jobs = load_all_jobs()
            portals = sorted(list({j.get("portal") for j in jobs if j.get("portal")}))
            
            # Extract common cleaned locations
            locations_set = set()
            for j in jobs:
                loc = j.get("location")
                if loc:
                    # Simplify compound locations
                    for part in loc.split(","):
                        cleaned = part.strip()
                        if cleaned and len(cleaned) > 2 and not cleaned.isdigit():
                            locations_set.add(cleaned)
            
            types = sorted(list({j.get("type") for j in jobs if j.get("type")}))

            self.send_json({
                "portals": portals,
                "locations": sorted(list(locations_set)),
                "types": types
            })
            return

        # ── API: Jobs with Search, Filters, Sorting, Pagination ─────
        if path == "/api/jobs":
            jobs = load_all_jobs()

            # 1. Search Query (title, company, description)
            q = query_params.get("q", [""])[0].strip().lower()
            if q:
                jobs = [
                    j for j in jobs
                    if q in j.get("role", "").lower()
                    or q in j.get("company", "").lower()
                    or q in j.get("description", "").lower()
                    or q in j.get("location", "").lower()
                ]

            # 2. Location Filter
            loc_filter = query_params.get("location", [""])[0].strip().lower()
            if loc_filter and loc_filter != "all":
                jobs = [j for j in jobs if loc_filter in j.get("location", "").lower()]

            # 3. Portal Filter
            portal_filter = query_params.get("portal", [""])[0].strip()
            if portal_filter and portal_filter.lower() != "all":
                jobs = [j for j in jobs if j.get("portal", "").lower() == portal_filter.lower()]

            # 4. Work Mode / Type Filter
            type_filter = query_params.get("type", [""])[0].strip()
            if type_filter and type_filter.lower() != "all":
                jobs = [j for j in jobs if j.get("type", "").lower() == type_filter.lower()]

            # 5. Sorting
            sort_by = query_params.get("sort", ["posted_desc"])[0]
            if sort_by == "company_asc":
                jobs.sort(key=lambda j: j.get("company", "").lower())
            elif sort_by == "role_asc":
                jobs.sort(key=lambda j: j.get("role", "").lower())
            elif sort_by == "location_asc":
                jobs.sort(key=lambda j: j.get("location", "").lower())
            else:  # default posted newest
                jobs.sort(key=lambda j: j.get("posted_date") or "", reverse=True)

            total_count = len(jobs)

            # 6. Pagination
            try:
                page = max(1, int(query_params.get("page", [1])[0]))
            except ValueError:
                page = 1
            try:
                limit = max(1, int(query_params.get("limit", [10])[0]))
            except ValueError:
                limit = 10

            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            paginated_jobs = jobs[start_idx:end_idx]

            start_num = start_idx + 1 if total_count > 0 else 0
            end_num = min(end_idx, total_count)

            response = {
                "jobs": paginated_jobs,
                "total": total_count,
                "page": page,
                "limit": limit,
                "total_pages": (total_count + limit - 1) // limit if total_count > 0 else 1,
                "start_index": start_num,
                "end_index": end_num
            }
            self.send_json(response)
            return

        # ── API: Verified Company Contacts ──────────────────────────
        if path == "/api/contacts":
            contacts = load_verified_contacts()
            q = query_params.get("q", [""])[0].strip().lower()
            if q:
                contacts = [
                    c for c in contacts
                    if q in c.get("company", "").lower()
                    or q in c.get("email", "").lower()
                    or q in c.get("website", "").lower()
                ]
            self.send_json({
                "contacts": contacts,
                "total": len(contacts)
            })
            return

        # ── API: Export Filtered CSV ─────────────────────────────────
        if path == "/api/export":
            jobs = load_all_jobs()
            q = query_params.get("q", [""])[0].strip().lower()
            if q:
                jobs = [
                    j for j in jobs
                    if q in j.get("role", "").lower() or q in j.get("company", "").lower()
                ]
            loc_filter = query_params.get("location", [""])[0].strip().lower()
            if loc_filter and loc_filter != "all":
                jobs = [j for j in jobs if loc_filter in j.get("location", "").lower()]
            portal_filter = query_params.get("portal", [""])[0].strip()
            if portal_filter and portal_filter.lower() != "all":
                jobs = [j for j in jobs if j.get("portal", "").lower() == portal_filter.lower()]

            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="internship_opportunities.csv"')
            self.end_headers()

            writer = csv.writer(self.wfile)
            writer.writerow(["Company", "Role", "Location", "Portal", "Type", "Posted", "Application Link", "Website", "Contact Email"])
            for j in jobs:
                writer.writerow([
                    j.get("company"),
                    j.get("role"),
                    j.get("location"),
                    j.get("portal"),
                    j.get("type"),
                    j.get("posted"),
                    j.get("application_link"),
                    j.get("website"),
                    j.get("email"),
                ])
            return

        # Fallback to static file serving
        return super().do_GET()

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def run_server():
    server_address = ("127.0.0.1", PORT)
    httpd = ThreadingHTTPServer(server_address, DashboardHandler)
    print(f"\n=======================================================")
    print(f" Dashboard server running at http://localhost:{PORT}")
    print(f" Press Ctrl+C to stop.")
    print(f"=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
