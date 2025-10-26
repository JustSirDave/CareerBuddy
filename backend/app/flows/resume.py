# backend/app/flows/resume.py
from typing import Dict, List

QUESTIONS = {
    "basics": (
        "Great! Let’s start with your details.\n"
        "Please send in one line (comma-separated):\n"
        "Full Name, Target Title, Email, Phone, City Country\n"
        "Example: David Lucas, Backend Engineer, david@example.com, +234-xxx, Lagos Nigeria"
    ),
    "summary": "Share a short professional summary (2–3 lines). Type *skip* to auto-draft.",
    # explicitly note skip here (optional but recommended)
    "skills": "List your skills (comma-separated). You can *skip*.",
    "experience": (
        "Let’s add a role.\n"
        "Send: Role, Company, City, Start (MMM YYYY), End (MMM YYYY or Present)\n"
        "Then send 2–4 bullet points (one message each). Type *done* when finished."
    ),
    "education": "Education: Degree, School, Year. You can add multiple—send one per message, or *skip*.",
    "extras": "Any projects or certifications to add? Send a brief line each, or *done* to finish."
}

def start_context() -> Dict:
    return {
        "basics": {},
        "summary": "",
        "skills": [],
        "experiences": [],
        "education": [],
        "projects": [],
        "certs": [],
        "_step": "basics",  # <-- important for the router/state machine
    }

def _split_commas(line: str) -> List[str]:
    return [p.strip() for p in (line or "").split(",")]

def parse_basics(line: str) -> Dict:
    parts = _split_commas(line)
    while len(parts) < 5:
        parts.append("")
    name, title, email, phone, location = parts[:5]
    return {"name": name, "title": title, "email": email, "phone": phone, "location": location}

def parse_skills(text: str) -> list[str]:
    return [s.strip() for s in _split_commas(text) if s.strip()]

def parse_experience_header(line: str) -> Dict:
    parts = _split_commas(line)
    while len(parts) < 5:
        parts.append("")
    role, company, location, start, end = parts[:5]
    return {"role": role, "company": company, "location": location, "start": start, "end": end, "bullets": []}

def draft_summary(ctx: Dict) -> str:
    title = (ctx.get("basics", {}).get("title") or "professional").strip()
    skills = [s for s in ctx.get("skills", []) if s][:4]
    exp = ctx.get("experiences", [])
    latest = exp[-1] if exp else {}
    company = latest.get("company", "").strip()
    pieces = []
    pieces.append(f"{title.capitalize()} with hands-on experience")
    if company:
        pieces[-1] += f" at {company}"
    if skills:
        pieces.append("Skilled in " + ", ".join(skills) + ".")
    else:
        pieces.append("Delivering reliable results and clean execution.")
    return " ".join(pieces)
