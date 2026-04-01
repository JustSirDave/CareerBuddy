"""
Guided revision flow for CareerBuddy.
Handles section selection, re-collection, and document regeneration.
"""
import re
from datetime import datetime
from app.models import Job
from app.flows import resume as resume_flow
from app.services import renderer, storage
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from loguru import logger

REVISION_SECTIONS = {
    "1": {"key": "basics", "label": "Basic details"},
    "2": {"key": "experiences", "label": "Work experience"},
    "3": {"key": "skills", "label": "Skills"},
    "4": {"key": "summary", "label": "Professional summary"},
    "5": {"key": "education", "label": "Education"},
    "6": {"key": "certifications", "label": "Certifications"},
    "7": {"key": "projects", "label": "Projects & links"},
}

SECTION_PROMPTS = {
    "basics": (
        "Let's update your basic details.\n\n"
        "Share your updated info:\n"
        "*Full Name, email@example.com, 08012345678, City*"
    ),
    "experiences": (
        "Let's update your work experience.\n\n"
        "Tell me about your most recent role:\n"
        "*Role title, Company, City, Start – End date*\n\n"
        "Type *done* when you've added all roles."
    ),
    "skills": (
        "Let's update your skills.\n\n"
        "List your skills (comma-separated):\n"
        "*Example:* Python, SQL, Communication"
    ),
    "summary": (
        "Let's update your professional summary.\n\n"
        "Write your summary below, or type *skip* to keep the current one."
    ),
    "education": (
        "Let's update your education.\n\n"
        "Format: *Degree, Institution, Year*\n"
        "(e.g. B.Sc Computer Science, University of Lagos, 2019)\n\n"
        "Type *done* when finished."
    ),
    "certifications": (
        "List your updated certifications.\n"
        "(e.g. AWS Certified Developer, 2023)\n\nType *skip* if none."
    ),
    "projects": (
        "Share your updated projects and profile links.\n"
        "(e.g. LinkedIn: linkedin.com/in/yourname)\n\nType *skip* if none."
    ),
}

MULTI_STEP_SECTIONS = ["experiences"]


def _generate_filename(job: Job) -> str:
    from app.utils import generate_filename
    return generate_filename(job)


def _get_latest_done_job(db: Session, user_id: str) -> Job | None:
    """Get user's most recent completed/delivered job (preview_ready or done)."""
    return (
        db.query(Job)
        .filter(
            Job.user_id == user_id,
            Job.status.in_(["preview_ready", "done", "completed"]),
        )
        .order_by(Job.updated_at.desc())
        .first()
    )


def start_revision(db: Session, job: Job, telegram_id: str) -> str:
    """Entry point — check eligibility, show section menu. Returns message to send."""
    rev_count = getattr(job, "revision_count", 0) or 0
    if rev_count >= 1:
        return (
            "You've used your free revision for this document.\n\n"
            "Paid revisions are coming soon! In the meantime, "
            "you can create a new document with your updates."
        )

    answers = job.answers or {}
    if not isinstance(answers, dict):
        answers = {}
    answers["_revision_step"] = "select_section"
    job.answers = answers
    job.revision_answers = job.revision_answers if job.revision_answers else {}
    if not isinstance(job.revision_answers, dict):
        job.revision_answers = {}
    flag_modified(job, "answers")
    db.commit()

    doc_label = {"resume": "resume", "cv": "CV", "cover": "cover letter"}.get(job.type, job.type)
    return (
        f"Let's update your {doc_label}. Which section would you like to change?\n\n"
        "1. Basic details (name, contact, location)\n"
        "2. Work experience\n"
        "3. Skills\n"
        "4. Professional summary\n"
        "5. Education\n"
        "6. Certifications\n"
        "7. Projects & links\n\n"
        "Reply with the number of the section."
    )


def handle_revision_step(db: Session, job: Job, message_text: str, telegram_id: str) -> str:
    """Route revision flow based on _revision_step. Returns message to send."""
    answers = job.answers or {}
    if not isinstance(answers, dict):
        answers = {}
    revision_step = answers.get("_revision_step")

    if revision_step == "select_section":
        return _handle_section_selection(db, job, message_text)
    if revision_step and revision_step.startswith("collecting_"):
        section_key = revision_step.replace("collecting_", "")
        return _handle_section_collection(db, job, section_key, message_text)
    if revision_step == "confirm":
        return _handle_revision_confirmation(db, job, message_text, telegram_id)

    return "Something went wrong. Type /revise to try again."


def _handle_section_selection(db: Session, job: Job, selection: str) -> str:
    section = REVISION_SECTIONS.get(selection.strip())
    if not section:
        return "Please reply with a number from 1 to 7."

    answers = job.answers or {}
    answers["_revision_section"] = section["key"]
    answers["_revision_step"] = f"collecting_{section['key']}"
    job.answers = answers
    flag_modified(job, "answers")
    db.commit()

    return SECTION_PROMPTS.get(section["key"], "Let's update this section.")


def _handle_section_collection(db: Session, job: Job, section_key: str, message_text: str) -> str:
    rev_answers = job.revision_answers or {}
    if not isinstance(rev_answers, dict):
        rev_answers = {}

    text = (message_text or "").strip().lower()

    if section_key == "experiences":
        if text == "done":
            if not rev_answers.get("experiences"):
                return "Please add at least one work experience before typing *done*."
            return _show_revision_confirmation(db, job, section_key)
        # Parse experience header
        header = resume_flow.parse_experience_header(message_text)
        if not header.get("role"):
            return "Please use format: *Role, Company, City, Start (MMM YYYY), End (MMM YYYY or Present)*"
        exps = rev_answers.get("experiences", [])
        exps.append(header)
        rev_answers["experiences"] = exps
        job.revision_answers = rev_answers
        flag_modified(job, "revision_answers")
        db.commit()
        return "Got it! Add another role, or type *done* to continue."

    if section_key == "basics":
        if "," not in message_text:
            return "Please use format: *Full Name, email@example.com, 08012345678, City*"
        rev_answers["basics"] = resume_flow.parse_basics(message_text)
    elif section_key == "skills":
        rev_answers["skills"] = resume_flow.parse_skills(message_text)
    elif section_key == "summary":
        if text == "skip":
            rev_answers["summary"] = (job.answers or {}).get("summary", "")
        else:
            rev_answers["summary"] = message_text.strip()
    elif section_key == "education":
        if text in ("done", "skip"):
            if not rev_answers.get("education"):
                return "Please add at least one education entry, or type *done* to skip."
            return _show_revision_confirmation(db, job, section_key)
        parsed = resume_flow.parse_education(message_text)
        if not parsed:
            return "Please use format: *Degree, School, Year*"
        edus = rev_answers.get("education", [])
        edus.append(parsed)
        rev_answers["education"] = edus
    elif section_key == "certifications":
        if text == "skip":
            rev_answers["certifications"] = []
        else:
            rev_answers["certifications"] = [{"details": message_text.strip()}]
    elif section_key == "projects":
        if text == "skip":
            rev_answers["projects"] = []
        else:
            rev_answers["projects"] = [{"details": message_text.strip()}]

    job.revision_answers = rev_answers
    flag_modified(job, "revision_answers")
    db.commit()

    if section_key in ("education",):
        return "✅ Added. Send another or type *done* to continue."
    return _show_revision_confirmation(db, job, section_key)


def _show_revision_confirmation(db: Session, job: Job, section_key: str) -> str:
    section_label = next(
        (s["label"] for s in REVISION_SECTIONS.values() if s["key"] == section_key),
        section_key,
    )
    answers = job.answers or {}
    answers["_revision_step"] = "confirm"
    job.answers = answers
    flag_modified(job, "answers")
    db.commit()

    doc_label = {"resume": "resume", "cv": "CV", "cover": "cover letter"}.get(job.type, job.type)
    return (
        f"Here's what will change in your {doc_label}:\n\n"
        f"✓ *{section_label}* updated\n\n"
        "Ready to regenerate your document?\n\n"
        "Type *yes* to regenerate, or *back* to pick a different section."
    )


def _handle_revision_confirmation(db: Session, job: Job, message_text: str, telegram_id: str) -> str:
    text = (message_text or "").strip().lower()

    if text == "back":
        answers = job.answers or {}
        answers["_revision_step"] = "select_section"
        job.answers = answers
        flag_modified(job, "answers")
        db.commit()
        return start_revision(db, job, telegram_id)

    if text not in ("yes", "y", "regenerate"):
        return "Type *yes* to regenerate, or *back* to pick a different section."

    # Merge revision_answers into job.answers
    rev_answers = job.revision_answers or {}
    answers = job.answers or {}
    for key, value in rev_answers.items():
        if not key.startswith("_"):
            answers[key] = value
    answers.pop("_revision_step", None)
    answers.pop("_revision_section", None)
    job.answers = answers
    job.revision_answers = {}
    job.revision_count = (job.revision_count or 0) + 1
    job.status = "preview_ready"
    flag_modified(job, "answers")
    db.commit()
    db.refresh(job)

    # Regenerate document
    try:
        if job.type == "cv":
            doc_bytes = renderer.render_cv(job)
        elif job.type == "cover":
            doc_bytes = renderer.render_cover_letter(job)
        else:
            doc_bytes = renderer.render_resume(job)

        filename = _generate_filename(job)
        file_path = storage.save_file_locally(job.id, doc_bytes, filename)
        job.draft_text = file_path
        db.commit()

        return f"__SEND_DOCUMENT__|{job.id}|{filename}"
    except Exception as e:
        logger.error(f"[revision] Render failed: {e}")
        job.revision_count = max(0, (job.revision_count or 1) - 1)
        db.commit()
        return f"❌ Sorry, document regeneration failed. Your data is safe — type /revise to try again."
