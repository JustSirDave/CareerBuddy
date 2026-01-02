"""
Resume/CV conversation flow - questions, parsers, and validators.
"""
from typing import Dict, List

QUESTIONS = {
    "basics": (
        "Great! Let's start with your details.\n"
        "Please send in one line (comma-separated):\n"
        "Full Name, Email, Phone, City Country\n\n"
        "Example: John Doe, user@example.com, +234-xxx, Lagos Nigeria"
    ),
    "target_role": (
        "What role/position are you applying for?\n\n"
        "Example: Data Analyst\n"
        "Example: Backend Engineer\n"
        "Example: Marketing Manager"
    ),
    "experience": (
        "Let's add a work experience.\n\n"
        "Send: Role, Company, City, Start (MMM YYYY), End (MMM YYYY or Present)\n\n"
        "Example: Backend Engineer, TechCorp, Lagos, Jan 2020, Present\n\n"
        "Next, you'll send 2–4 bullet points describing your achievements.\n"
        "Example bullet: Increased sales by 40% through strategic marketing campaigns"
    ),
    "education": (
        "Education: Degree, School, Year\n\n"
        "Example: B.Sc. Computer Science, University of Lagos, 2020\n\n"
        "You can add multiple—send one per message, or type *skip*."
    ),
    "extras": (
        "Almost done! Any projects, certifications, or volunteer work to add?\n\n"
        "Example: Built an e-commerce platform using React and Node.js\n"
        "Example: AWS Certified Solutions Architect\n"
        "Example: Volunteer coding instructor at Code Club\n\n"
        "Send one per message, or type *done* to finish."
    ),
}


def start_context() -> Dict:
    """Initialize empty conversation context."""
    return {
        "basics": {},
        "target_role": "",
        "summary": "",
        "skills": [],
        "ai_suggested_skills": [],  # Skills suggested by AI
        "experiences": [],
        "education": [],
        "projects": [],
        "volunteer": [],
        "certs": [],
        "_step": "basics",
    }


def _split_commas(line: str) -> List[str]:
    """Split comma-separated string and strip whitespace."""
    return [p.strip() for p in (line or "").split(",")]


def parse_basics(line: str) -> Dict:
    """
    Parse: Full Name, Email, Phone, City Country
    """
    parts = _split_commas(line)
    while len(parts) < 4:
        parts.append("")

    name, email, phone, location = parts[:4]

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "location": location
    }


def parse_skills(text: str) -> List[str]:
    """Parse comma-separated skills."""
    return [s.strip() for s in _split_commas(text) if s.strip()]


def parse_experience_header(line: str) -> Dict:
    """
    Parse: Role, Company, City, Start (MMM YYYY), End (MMM YYYY or Present)
    """
    parts = _split_commas(line)
    while len(parts) < 5:
        parts.append("")

    role, company, location, start, end = parts[:5]

    return {
        "role": role,
        "company": company,
        "location": location,
        "start": start,
        "end": end,
        "bullets": []  # Will be filled in next step
    }


def draft_summary(ctx: Dict) -> str:
    """
    Auto-generate a professional summary based on collected context.
    """
    basics = ctx.get("basics", {})
    title = (basics.get("title") or "professional").strip()
    skills = [s for s in ctx.get("skills", []) if s][:4]
    experiences = ctx.get("experiences", [])

    # Get latest experience
    latest_exp = experiences[-1] if experiences else {}
    company = latest_exp.get("company", "").strip()

    pieces = []

    # Opening line
    if company:
        pieces.append(f"{title.capitalize()} with hands-on experience at {company}.")
    else:
        pieces.append(f"{title.capitalize()} with hands-on experience.")

    # Skills mention
    if skills:
        pieces.append(f"Skilled in {', '.join(skills[:3])}.")
    else:
        pieces.append("Delivering reliable results and clean execution.")

    return " ".join(pieces)


def format_skills_selection(skills: List[str]) -> str:
    """
    Format AI-generated skills as a numbered list for user selection.

    Args:
        skills: List of AI-generated skill suggestions

    Returns:
        Formatted string with numbered skills
    """
    lines = ["🤖 Based on your target role, here are some suggested skills:\n"]

    for i, skill in enumerate(skills, 1):
        lines.append(f"{i}. {skill}")

    lines.append("\n📌 *Select up to 5 skills* by sending their numbers (comma-separated).")
    lines.append("Example: 1,3,5,7,9")
    lines.append("\nOr type your own skills (comma-separated) to skip AI suggestions.")

    return "\n".join(lines)


def parse_skill_selection(text: str, available_skills: List[str]) -> List[str]:
    """
    Parse user's skill selection from numbered choices.

    Args:
        text: User's input (either numbers or custom skills)
        available_skills: List of AI-generated skills to choose from

    Returns:
        List of selected skills
    """
    text = text.strip()

    # Check if user entered numbers (e.g., "1,3,5,7")
    if text and all(c.isdigit() or c in {',', ' '} for c in text):
        try:
            # Parse numbers
            numbers = [int(n.strip()) for n in text.split(",") if n.strip()]

            # Convert to skills (1-indexed)
            selected = []
            for num in numbers:
                if 1 <= num <= len(available_skills):
                    selected.append(available_skills[num - 1])

            # Limit to 5
            return selected[:5]
        except ValueError:
            pass

    # Otherwise treat as custom skills (comma-separated)
    return parse_skills(text)


def validate_basics(basics: Dict) -> bool:
    """Check if basics have minimum required fields."""
    return bool(basics.get("name") and basics.get("email"))


def validate_experience(exp: Dict) -> bool:
    """Check if experience has minimum required fields."""
    return bool(exp.get("role") and exp.get("company"))