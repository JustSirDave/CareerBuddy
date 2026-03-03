"""
CareerBuddy - Conversation Router
Author: Sir Dave
"""
from __future__ import annotations
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import User, Job, Message
from app.flows import resume as resume_flow
from app.flows import onboarding as onboarding_flow
from app.flows.validators import validate_basics, validate_experience_bullets
from app.services.idempotency import seen_or_mark
from app.services import renderer, storage, ai, payments
from app.services.error_handler import handle_error, ErrorType, ERROR_MESSAGES

WELCOME = """👋 *Welcome to Career Buddy!*

Your AI-powered career document assistant. I'll help you create professional resumes, CVs, and cover letters that get results!

*🚀 Quick Start:*
Just answer a few simple questions and I'll:
• ✨ Enhance your content with AI
• 📝 Format everything professionally  
• 📄 Deliver your document instantly

Ready to begin? Choose a document type below! 👇"""
GREETINGS = {"hi", "hello", "hey", "start", "menu", "/start"}
RESETS = {"reset", "/reset", "restart"}
HELP_COMMANDS = {"/help", "help"}
STATUS_COMMANDS = {"/status", "status"}
REVISE_COMMANDS = {"/revise", "revise", "request revision"}
REFERRAL_COMMANDS = {"/referral", "referral"}
HISTORY_COMMANDS = {"/history", "history", "my documents", "documents"}
BUY_COMMANDS = {"/buy_resume", "/buy_cv", "/buy_cover_letter", "/buy_bundle"}
ADMIN_COMMANDS = {"/admin", "/stats", "/broadcast", "/sample", "/makeadmin", "/setpro"}
PDF_COMMANDS = {"/pdf", "pdf", "convert to pdf", "convert pdf"}
FORCE_LOWER = lambda s: (s or "").strip().lower()

STEP_LABELS = {
    "basics": "Your basic details",
    "target_role": "Target job role",
    "experience_header": "Work experience",
    "experience_bullets": "Achievement bullets",
    "add_another_experience": "Add another experience",
    "skills": "Skills",
    "summary": "Professional summary",
    "education": "Education",
    "certifications": "Certifications",
    "profiles": "Online profiles",
    "projects": "Projects",
    "preview": "Final preview",
    "draft_ready": "Finalizing your document",
}

STEP_REPROMPTS = {
    "basics": "What's your full name, email, phone, and location?\n_(e.g. Ada Obi, ada@email.com, 08012345678, Lagos)_",
    "target_role": "What job title are you applying for?",
    "experience_header": "Tell me about your work experience — role, company, city, and dates.",
    "experience_bullets": "Send 2–4 bullet points describing your achievements for this role.",
    "add_another_experience": "Add another experience? (Reply: yes / no)",
    "skills": "Select skills from the list or type your own.",
    "summary": "Share a bit about yourself for your summary, or type *skip*.",
    "education": "Add education: Degree, School, Year. Type *done* when finished.",
    "certifications": "Add certifications or type *done* to continue.",
    "profiles": "Add profile links: Platform, URL. Type *done* to continue.",
    "projects": "Add projects or type *done* to continue.",
    "preview": "Review your document and confirm.",
    "draft_ready": "We're finalizing your document — please wait.",
}


def is_admin(telegram_user_id: str) -> bool:
    from app.config import settings
    return telegram_user_id in settings.admin_telegram_ids


def _progress_bar(current_step: int, total_steps: int) -> str:
    filled = "●" * current_step
    empty = "○" * (total_steps - current_step)
    percentage = int((current_step / total_steps) * 100)
    return f"{filled}{empty} {percentage}% ({current_step}/{total_steps})"


def _add_progress(message: str, step: str) -> str:
    steps_order = ["basics", "summary", "skills", "experiences", "experience_bullets",
                   "education", "projects", "target_role", "review"]
    if step not in steps_order:
        return message
    current = steps_order.index(step) + 1
    total = len(steps_order)
    progress = _progress_bar(current, total)
    return f"📊 *Progress:* {progress}\n\n{message}"


HELP_MESSAGE = """🤖 *Career Buddy - Help Guide*

I help you create professional resumes, CVs, and cover letters tailored to your dream role!

*📝 Available Documents:*
• *Resume* - 1-2 page professional resume
• *CV* - Detailed curriculum vitae
• *Cover Letter* - Tailored application letter

*🎯 How It Works:*
1. Choose your document type
2. Answer my questions step by step
3. I'll enhance your content with AI
4. Receive your professional document!

*💡 Commands:*
/start - Start creating a document
/status - Check your credits
/buy\\_resume - Buy a resume credit (₦7,500)
/buy\\_cv - Buy a CV credit (₦7,500)
/buy\\_cover\\_letter - Buy a cover letter credit (₦3,000)
/buy\\_bundle - 2 docs + 1 cover letter (₦15,000)
/pdf - Convert document to PDF (paid credits)
/referral - Share & earn free credits
/reset - Cancel and start over
/help - Show this help message

*💳 Pricing:*
• *1st document free* — then pay per document
• Resume/CV — ₦7,500
• Cover Letter — ₦3,000
• Bundle (2 docs + 1 cover letter) — ₦15,000

*🆘 Need Support?*
Contact: @your\\_support\\_username

Ready to begin? Just type /start!"""


def _advance(db: Session, job: Job, answers: dict, next_step: str):
    answers["_step"] = next_step
    job.answers = answers
    flag_modified(job, "answers")
    db.commit()
    db.refresh(job)
    logger.info(f"[_advance] job.id={job.id} advanced to step={next_step}")


def _dedupe(db: Session, job: Job, msg_id: str | None) -> bool:
    if not msg_id:
        return False
    if job.last_msg_id == msg_id:
        logger.warning(f"[dedupe] Duplicate msg_id={msg_id}, ignoring.")
        return True
    job.last_msg_id = msg_id
    db.commit()
    logger.info(f"[dedupe] Marked msg_id={msg_id} as seen")
    return False


def _log_state(when: str, job: Job | None):
    if not job:
        logger.info(f"[router] {when}: job=None")
        return
    ans = job.answers if isinstance(job.answers, dict) else {}
    logger.info(
        f"[router] {when}: job.id={job.id} type={job.type} status={job.status} "
        f"keys={list(ans.keys())} step={ans.get('_step')}"
    )


def _generate_filename(job: Job) -> str:
    answers = job.answers or {}
    basics = answers.get('basics', {})
    name = basics.get('name', 'Document')
    import re
    clean_name = re.sub(r'[<>:"/\\|?*]', '', name)
    doc_type_map = {
        'resume': 'Resume',
        'cv': 'CV',
        'cover': 'Cover Letter',
        'revamp': 'Revamp'
    }
    doc_type = doc_type_map.get(job.type, job.type.capitalize())
    filename = f"{clean_name} - {doc_type}.docx"
    return filename


def _format_preview(answers: dict) -> str:
    basics = answers.get("basics", {})
    target_role = answers.get("target_role", "")
    summary = answers.get("summary", "")
    skills = answers.get("skills", [])
    experiences = answers.get("experiences", [])
    education = answers.get("education", [])
    projects = answers.get("projects", [])

    lines = ["📋 *Preview of Your Information*\n"]
    lines.append("*Contact Details:*")
    lines.append(f"Name: {basics.get('name', 'N/A')}")
    if target_role:
        lines.append(f"Target Role: {target_role}")
    lines.append(f"Email: {basics.get('email', 'N/A')}")
    lines.append(f"Phone: {basics.get('phone', 'N/A')}")
    lines.append(f"Location: {basics.get('location', 'N/A')}")
    lines.append("")

    if summary:
        lines.append("*Professional Summary:* 🤖")
        lines.append(summary)
        lines.append("")

    if skills:
        lines.append("*Skills:* 🤖")
        lines.append(", ".join(skills))
        lines.append("")

    if experiences:
        lines.append(f"*Work Experience:* ({len(experiences)} position{'s' if len(experiences) != 1 else ''})")
        for i, exp in enumerate(experiences, 1):
            lines.append(f"{i}. {exp.get('role', 'N/A')} at {exp.get('company', 'N/A')}")
            bullets = exp.get("bullets", [])
            lines.append(f"   ({len(bullets)} achievement{'s' if len(bullets) != 1 else ''})")
        lines.append("")

    if education:
        lines.append(f"*Education:* ({len(education)} entr{'ies' if len(education) != 1 else 'y'})")
        lines.append("")

    if projects:
        lines.append(f"*Projects/Certifications:* ({len(projects)} item{'s' if len(projects) != 1 else ''})")
        lines.append("")

    return "\n".join(lines)


async def convert_to_pdf(db: Session, user: User, telegram_user_id: str) -> str:
    """Check most recent job's credit_type for PDF permission."""
    last_job = (
        db.query(Job)
        .filter(Job.user_id == user.id, Job.status.in_(["done", "preview_ready", "completed"]))
        .order_by(Job.created_at.desc())
        .first()
    )
    if not last_job:
        return "You don't have any documents yet. Create one first with /start!"

    credit_type = (last_job.answers or {}).get("_credit_type", "free")
    if not payments.can_use_pdf(user, credit_type):
        return (
            "🔒 *PDF Format — Paid Credits Only*\n\n"
            "PDF conversion is available when you use a paid credit.\n\n"
            "Free documents are delivered as DOCX only.\n\n"
            "Type /buy\\_resume or /buy\\_bundle to purchase credits!"
        )
    return f"__SEND_PDF__|{telegram_user_id}|placeholder"


def _format_cover_preview(answers: dict) -> str:
    basics = answers.get("basics", {})
    role = answers.get("cover_role") or answers.get("target_role", "")
    company = answers.get("cover_company", "")

    lines = ["📋 *Cover Letter Preview*\n"]
    lines.append(f"*Contact Info:*")
    lines.append(f"Name: {basics.get('name', 'N/A')}")
    lines.append(f"Email: {basics.get('email', 'N/A')}")
    lines.append(f"Phone: {basics.get('phone', 'N/A')}")
    lines.append(f"Location: {basics.get('location', 'N/A')}")
    lines.append("")
    lines.append(f"*Target Position:*")
    lines.append(f"Role: {role or 'N/A'}")
    lines.append(f"Company: {company or 'N/A'}")
    lines.append("")
    lines.append(f"*Experience:*")
    lines.append(f"{answers.get('years_experience', 'N/A')} in {answers.get('industries', 'N/A')}")
    lines.append(f"Current: {answers.get('current_title', 'N/A')} at {answers.get('current_employer', 'N/A')}")
    lines.append("")
    lines.append(f"*Key Achievement:*")
    lines.append(f"{answers.get('achievement_1', 'N/A')}")
    if answers.get('achievement_2'):
        lines.append(f"{answers.get('achievement_2')}")
    lines.append("")
    lines.append(f"*Key Skills:*")
    skills = answers.get('cover_key_skills', [])
    lines.append(", ".join(skills) if skills else "N/A")
    lines.append("")

    return "\n".join(lines)


def infer_type(text: str) -> str | None:
    t = (text or "").strip().lower()
    if t == "choose_resume":
        return "resume"
    if t == "choose_cv":
        return "cv"
    if t == "choose_cover":
        return "cover"
    if t == "choose_revamp" or t == "revamp":
        return "revamp"
    if "resume" in t:
        return "resume"
    if t == "cv" or " cv " in f" {t} ":
        return "cv"
    if "cover" in t:
        return "cover"
    if "revamp" in t or "improve" in t or "enhance" in t:
        return "revamp"
    return None


def _active_collecting_job(db: Session, user_id):
    return (
        db.query(Job)
        .filter(Job.user_id == user_id, Job.status == "collecting")
        .order_by(Job.created_at.desc())
        .first()
    )


def _active_revising_job(db: Session, user_id):
    return (
        db.query(Job)
        .filter(Job.user_id == user_id, Job.status == "revising")
        .order_by(Job.created_at.desc())
        .first()
    )


def _new_job(db: Session, user_id, doc_type: str) -> Job:
    if doc_type == "revamp":
        initial_step = "upload"
    else:
        initial_step = "basics"
    job = Job(
        user_id=user_id,
        type=doc_type,
        status="collecting",
        answers=resume_flow.start_context() | {"_step": initial_step},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info(f"[new_job] Created job.id={job.id} type={doc_type} initial_step={initial_step}")
    return job


def get_active_job(db: Session, user_id, doc_type: str | None) -> Job | None:
    if doc_type:
        existing = (
            db.query(Job)
            .filter(Job.user_id == user_id, Job.status == "collecting", Job.type == doc_type)
            .order_by(Job.created_at.desc())
            .first()
        )
        return existing or _new_job(db, user_id, doc_type)
    return _active_collecting_job(db, user_id)


async def handle_resume(db: Session, job: Job, text: str) -> str:
    user = db.query(User).filter(User.id == job.user_id).first()
    answers = job.answers or resume_flow.start_context()
    step = FORCE_LOWER(answers.get("_step") or "basics")
    t = (text or "").strip()
    t_lower = t.lower()
    logger.info(f"[resume] step={step} text='{t[:80]}'")

    # ---- BASICS ----
    if step == "basics":
        if answers.get("basics", {}).get("name"):
            _advance(db, job, answers, "target_role")
            return resume_flow.QUESTIONS["target_role"]
        if "," not in t:
            return resume_flow.QUESTIONS["basics"]

        is_valid, error_key = validate_basics(t)
        if not is_valid:
            return ERROR_MESSAGES.get(error_key, resume_flow.QUESTIONS["basics"])

        answers["basics"] = resume_flow.parse_basics(t)
        _advance(db, job, answers, "target_role")
        return resume_flow.QUESTIONS["target_role"]

    # ---- TARGET ROLE ----
    if step == "target_role":
        if not t:
            return resume_flow.QUESTIONS["target_role"]
        answers["target_role"] = t.strip()
        if "basics" not in answers:
            answers["basics"] = {}
        answers["basics"]["title"] = t.strip()
        _advance(db, job, answers, "experience_header")
        return resume_flow.QUESTIONS["experiences"]

    # ---- EXPERIENCE HEADER ----
    if step == "experience_header":
        if t.lower() == "skip":
            _advance(db, job, answers, "education")
            return resume_flow.QUESTIONS["education"]
        header = resume_flow.parse_experience_header(t)
        if not header.get("role"):
            return ("Please send: Role, Company, City, Start (MMM YYYY), "
                    "End (MMM YYYY or Present)")
        exps = list(answers.get("experiences", []))
        exps.append(header)
        answers["experiences"] = exps
        _advance(db, job, answers, "experience_bullets")
        return ("Great! Now send 2–4 bullet points (one per message) describing your achievements.\n\n"
                "Example: • Increased sales by 40% through strategic marketing campaigns\n\n"
                "Type *done* when finished.")

    # ---- EXPERIENCE BULLETS ----
    if step == "experience_bullets":
        lt = t.lower()
        exps = list(answers.get("experiences", []))
        if not exps:
            _advance(db, job, answers, "experience_header")
            return resume_flow.QUESTIONS["experiences"]
        if lt == "done" or lt == "skip":
            bullets = exps[-1].get("bullets", [])
            is_valid, error_key = validate_experience_bullets(bullets)
            if not is_valid:
                return ERROR_MESSAGES.get(error_key, "Add at least 2 achievement bullets for this role.")
            _advance(db, job, answers, "add_another_experience")
            return "Add another experience? (Reply: yes / no)"
        if t:
            exps[-1]["bullets"].append(t.strip())
            answers["experiences"] = exps
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()
        bullet_count = len(exps[-1].get("bullets", []))
        return f"Got it! ({bullet_count} bullet{'s' if bullet_count != 1 else ''} added)\n\nSend another bullet point or type *done* to continue."

    # ---- ADD ANOTHER EXPERIENCE ----
    if step == "add_another_experience":
        lt = t.lower()
        if lt in {"yes", "y", "add", "add another"}:
            _advance(db, job, answers, "experience_header")
            return resume_flow.QUESTIONS["experiences"]
        _advance(db, job, answers, "education")
        return resume_flow.QUESTIONS["education"]

    # ---- EDUCATION ----
    if step == "education":
        if t_lower in {"done", "skip"}:
            if not answers.get("education"):
                return "Please add at least one education entry, or type *skip* to continue."
            _advance(db, job, answers, "certifications")
            return resume_flow.QUESTIONS["certifications"]
        parsed = resume_flow.parse_education(t)
        if not parsed:
            return ("❌ *Invalid format!*\n\n"
                    "Please use: *Degree, School, Year*\n\n"
                    "*Example:* B.Sc. Computer Science, University of Lagos, 2020")
        edus = list(answers.get("education", []))
        edus.append(parsed)
        answers["education"] = edus
        job.answers = answers
        flag_modified(job, "answers")
        db.commit()
        return "✅ Added. Send another or type *done* to continue."

    # ---- CERTIFICATIONS ----
    if step == "certifications":
        if t_lower in {"done", "skip"}:
            _advance(db, job, answers, "profiles")
            return resume_flow.QUESTIONS["profiles"]
        if not t:
            return resume_flow.QUESTIONS["certifications"]
        certs = list(answers.get("certifications", []))
        certs.append({"details": t})
        answers["certifications"] = certs
        job.answers = answers
        flag_modified(job, "answers")
        db.commit()
        return "✅ Added. Send another certification or type *done* to continue."

    # ---- PROFILES ----
    if step == "profiles":
        if t_lower in {"done", "skip"}:
            _advance(db, job, answers, "projects")
            return resume_flow.QUESTIONS["projects"]
        if not t:
            return resume_flow.QUESTIONS["profiles"]
        parsed = resume_flow.parse_profile(t)
        if not parsed:
            return ("❌ *Invalid format!*\n\n"
                    "Please use: *Platform, URL*\n\n"
                    "*Examples:*\n"
                    "• LinkedIn, https://linkedin.com/in/yourname\n"
                    "• GitHub, https://github.com/yourname")
        profiles = list(answers.get("profiles", []))
        profiles.append(parsed)
        answers["profiles"] = profiles
        job.answers = answers
        flag_modified(job, "answers")
        db.commit()
        return "✅ Added. Send another profile or type *done* to continue."

    # ---- PROJECTS ----
    if step == "projects":
        if t_lower in {"done", "skip"}:
            _advance(db, job, answers, "skills")
            step = "skills"
        else:
            if not t:
                return resume_flow.QUESTIONS["projects"]
            projs = list(answers.get("projects", []))
            projs.append({"details": t})
            answers["projects"] = projs
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()
            return "✅ Added. Send another project or type *done* to continue."

    # ---- SKILLS (AI-GENERATED WITH NUMBER SELECTION) ----
    if step == "skills":
        SKILLS_WAKE_WORDS = {"continue", "ready", "show", "generate", "next", "proceed", "go"}
        ai_skills = answers.get("ai_suggested_skills", [])

        if not ai_skills:
            if t_lower in SKILLS_WAKE_WORDS:
                return ("⏳ *Generating skill suggestions...*\n\n"
                        "AI is analyzing your role and experience to suggest relevant skills.\n"
                        "This usually takes 3-5 seconds.\n\n"
                        "Type *continue* when ready to see them!")
            try:
                target_role = answers.get("target_role", "")
                experiences = answers.get("experiences", [])
                basics = answers.get("basics", {})
                logger.info(f"[skills] Starting AI skills generation for job {job.id}")
                suggested_skills = ai.generate_skills(target_role, basics, experiences)
                suggested_skills = suggested_skills[:8]
                answers["ai_suggested_skills"] = suggested_skills
                job.answers = answers
                flag_modified(job, "answers")
                db.commit()
                logger.info(f"[skills] AI skills generated successfully for job {job.id}")
                return resume_flow.format_skills_selection(suggested_skills)
            except Exception as e:
                logger.error(f"[skills] AI generation failed: {e}")
                return ("⚠️ AI skills generation unavailable.\n\n"
                        "💡 *List your top 5-8 skills* (comma-separated)\n\n"
                        "*Example:* Python, Data Analysis, SQL, Communication")

        if not t or t_lower in SKILLS_WAKE_WORDS:
            return resume_flow.format_skills_selection(ai_skills)

        selected_skills = resume_flow.parse_skill_selection(t, ai_skills)
        if not selected_skills or len(selected_skills) < 3:
            return ("❌ *Invalid selection!*\n\n"
                    "Please enter skill numbers (comma-separated):\n"
                    "*Example:* 1,3,5,7\n\n"
                    "Or type your own skills (comma-separated).\n"
                    "Need at least 3 skills.")
        answers["skills"] = selected_skills
        _advance(db, job, answers, "personal_info")
        return resume_flow.QUESTIONS["personal_info"]

    # ---- SUMMARY (AI-GENERATED, REQUIRED) ----
    if step == "summary":
        WAKE_WORDS = {"continue", "ready", "show", "generate", "next", "proceed", "go", "ok"}
        if t_lower == "skip":
            return ("✍️ *Write Your Own Summary*\n\n"
                    "Please write a 2-3 sentence professional summary about yourself.\n\n"
                    "*Example:*\n"
                    "Senior Data Analyst with 5+ years of experience in financial modeling and business intelligence. "
                    "Proven track record of delivering actionable insights that drive strategic decisions. "
                    "Expert in Python, SQL, and data visualization tools.")

        if not answers.get("summary"):
            if t_lower in WAKE_WORDS:
                logger.info(f"[summary] User triggered AI generation with wake word: {t_lower}")
                try:
                    logger.info(f"[summary] Starting AI summary generation for job {job.id}")
                    summary = ai.generate_summary(answers)
                    answers["summary"] = summary
                    job.answers = answers
                    flag_modified(job, "answers")
                    db.commit()
                    logger.info(f"[summary] AI summary generated successfully for job {job.id}")
                    return (f"✨ *AI-Generated Professional Summary:*\n\n"
                            f"{summary}\n\n"
                            f"━━━━━━━━━━━━━━━━\n\n"
                            f"✅ Happy with this? Type *yes* to continue.\n"
                            f"📝 Or send your own summary to replace it.\n"
                            f"🔄 Type *continue* to see it again.")
                except Exception as e:
                    logger.error(f"[summary] AI generation failed: {e}")
                    return ("⚠️ AI summary generation unavailable.\n\n"
                            "Please write a 2-3 sentence professional summary:\n\n"
                            "*Example:* Data Analyst with 5+ years building dashboards.")

            if t and t_lower not in WAKE_WORDS:
                answers["summary"] = t
                job.answers = answers
                flag_modified(job, "answers")
                db.commit()
                _advance(db, job, answers, "preview")
                preview_text = _format_preview(answers)
                return f"{preview_text}\n\n✅ Reply *yes* to generate your document or */reset* to start over!"

            return ("⏳ *Ready to generate your AI summary!*\n\n"
                    "Type *continue* to start AI generation, or *skip* to write your own.")

        if t_lower in WAKE_WORDS and t_lower not in {"yes", "y", "ok", "okay", "good", "done"}:
            return (f"✨ *Your AI-Generated Professional Summary:*\n\n"
                    f"{answers['summary']}\n\n"
                    f"━━━━━━━━━━━━━━━━\n\n"
                    f"✅ Happy with this? Type *yes* to continue.\n"
                    f"📝 Or send your own summary to replace it.")

        if t_lower in {"yes", "y", "ok", "okay", "good", "done"}:
            pass
        elif t:
            answers["summary"] = t
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()
        else:
            return (f"✨ *Your Professional Summary:*\n\n"
                    f"{answers['summary']}\n\n"
                    f"━━━━━━━━━━━━━━━━\n\n"
                    f"Type *yes* to accept, or send your own summary.\n"
                    f"Or type *continue* to see it again.")

        _advance(db, job, answers, "preview")
        preview_text = _format_preview(answers)
        return f"{preview_text}\n\n✅ Reply *yes* to generate your document or */reset* to start over!"

    # ---- PERSONAL INFO (BEFORE SUMMARY) ----
    if step == "personal_info":
        if not t:
            return resume_flow.QUESTIONS["personal_info"]
        if t_lower not in {"skip"}:
            answers["personal_traits"] = t
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()
        _advance(db, job, answers, "summary")
        return ("🤖 *AI Summary Generation Ready*\n\n"
                "I'm about to craft your professional summary using AI based on:\n"
                "• Your target role\n"
                "• Your work experience\n"
                "• Your skills\n"
                "• Your personal info\n\n"
                "⏱️ *This will take approximately 30-60 seconds*\n\n"
                "📝 *What to do:*\n"
                "Type *continue* when you're ready for me to generate it!\n\n"
                "💡 Or you can type *skip* to write your own summary.")

    # ---- PREVIEW ----
    if step == "preview":
        if not t or t.lower() in {"done", "skip"}:
            preview_text = _format_preview(answers)
            return f"{preview_text}\n\nLooks good? Reply *yes* to generate your document, or */reset* to start over."
        if t.lower() in {"yes", "y", "confirm", "ok", "okay"}:
            answers["template"] = answers.get("template", "template_1")
            _advance(db, job, answers, "finalize")
            step = "finalize"
        else:
            return ("To make changes, please type */reset* to start over.\n\n"
                    "Or reply *yes* to proceed with generating your document.")

    # ---- TEMPLATE SELECTION (handled via callback, but add safety) ----
    if step == "template_selection":
        return ("Please click one of the template buttons above to continue.\n\n"
                "Or type */reset* to start over.")

    # ---- FINALIZE ----
    if step == "finalize":
        doc_type = "cv" if job.type == "cv" else "resume"

        # Gate: check credit availability
        if not payments.can_generate(user, doc_type):
            return payments.get_purchase_prompt(doc_type)

        # Consume credit
        try:
            credit_type = payments.consume_credit(user, doc_type, db)
        except ValueError:
            return payments.get_purchase_prompt(doc_type)

        answers["_credit_type"] = credit_type

        logger.info(f"[handle_resume] Finalizing job.id={job.id} credit_type={credit_type}")

        try:
            logger.info(f"[handle_resume] Rendering document for job.id={job.id}")
            if job.type == "cv":
                doc_bytes = renderer.render_cv(job)
            else:
                doc_bytes = renderer.render_resume(job)

            filename = _generate_filename(job)
            file_path = storage.save_file_locally(job.id, doc_bytes, filename)

            job.draft_text = file_path
            job.status = "preview_ready"
            db.commit()
            logger.info(f"[handle_resume] Document rendered successfully: {file_path}")

        except Exception as e:
            logger.error(f"[handle_resume] Document rendering failed: {e}")
            job.status = "render_failed"
            job.draft_text = f"Error: {str(e)}"
            db.commit()
            _advance(db, job, job.answers, "done")
            telegram_id = user.telegram_user_id
            if telegram_id:
                await handle_error(
                    ErrorType.RENDER_FAILURE,
                    telegram_id,
                    "docx_render_failed",
                    context={"doc_type": job.type or "document"},
                    exception=e,
                )
            return ""

        _advance(db, job, job.answers, "done")
        return f"__SEND_DOCUMENT__|{job.id}|{filename}"

    # ---- DONE ----
    if step == "done":
        return "Your document has been sent! Reply */reset* to create another document, or *menu* to see options."

    return resume_flow.QUESTIONS.get(step, resume_flow.QUESTIONS["basics"])


async def handle_revamp(db: Session, job: Job, text: str) -> str:
    user = db.query(User).filter(User.id == job.user_id).first()
    answers = job.answers or {"_step": "upload"}
    step = FORCE_LOWER(answers.get("_step") or "upload")
    t = (text or "").strip()
    logger.info(f"[revamp] step={step} text_len={len(t)}")

    # ---- UPLOAD ----
    if step == "upload":
        if not t or t.lower() in {"revamp", "revamp existing", "revamp existing (soon)"}:
            upload_msg = "📄 *Resume/CV Revamp*\n\n"
            upload_msg += "I'll help improve your existing resume or CV with AI-powered enhancements!\n\n"
            upload_msg += "*📤 Upload Your Resume:*\n"
            upload_msg += "✅ Supported format: .docx\n"
            upload_msg += "\n*How It Works:*\n"
            upload_msg += "1. Tap the 📎 attachment icon\n"
            upload_msg += "2. Select your resume file\n"
            upload_msg += "3. Send it to me\n"
            upload_msg += "4. I'll analyze and improve it with AI\n"
            upload_msg += "5. You'll get a professionally revamped version!\n\n"
            upload_msg += "_Maximum file size: 10MB_"
            return upload_msg

        return ("📎 *Please upload your resume file*\n\n"
                "I need you to upload your existing resume as a file (not paste text).\n\n"
                "*Steps:*\n"
                "1. Tap the 📎 attachment button\n"
                "2. Choose your resume file (.docx format)\n"
                "3. Send it to me\n\n"
                "Or type */reset* to cancel.")

    # ---- REVAMP PROCESSING ----
    if step == "revamp_processing":
        original = answers.get("original_content", "")
        try:
            revamped_content = ai.revamp_resume(original)
            answers["revamped_content"] = revamped_content
            _advance(db, job, answers, "preview")
            preview = f"""🎯 *AI-Enhanced Resume*

{revamped_content[:500]}{'...' if len(revamped_content) > 500 else ''}

---
Reply *yes* to generate your improved document, or */reset* to start over."""
            return preview
        except Exception as e:
            logger.error(f"[revamp] AI revamp failed: {e}")
            return ("❌ Sorry, we couldn't process your resume. Please try again or contact support.\n\n"
                    "Support: 07063011079")

    # ---- PREVIEW ----
    if step == "preview":
        if t.lower() in {"yes", "y", "confirm", "ok"}:
            doc_type = "resume"
            if not payments.can_generate(user, doc_type):
                return payments.get_purchase_prompt(doc_type)
            try:
                credit_type = payments.consume_credit(user, doc_type, db)
            except ValueError:
                return payments.get_purchase_prompt(doc_type)
            answers["_credit_type"] = credit_type

            try:
                logger.info(f"[revamp] Rendering revamped document for job.id={job.id}")
                doc_bytes = renderer.render_revamp(job)
                filename = _generate_filename(job)
                file_path = storage.save_file_locally(job.id, doc_bytes, filename)
                job.draft_text = file_path
                job.status = "preview_ready"
                db.commit()
                _advance(db, job, answers, "done")
                return f"__SEND_DOCUMENT__|{job.id}|{filename}"
            except Exception as e:
                logger.error(f"[revamp] Rendering failed: {e}")
                _advance(db, job, answers, "done")
                return f"❌ Sorry, document generation failed: {str(e)}"
        return "Reply *yes* to generate your document, or */reset* to start over."

    return resume_flow.QUESTIONS.get(step, resume_flow.QUESTIONS["basics"])


async def handle_cover(db: Session, job: Job, text: str) -> str:
    user = db.query(User).filter(User.id == job.user_id).first()
    answers = job.answers or {"_step": "basics"}
    step = FORCE_LOWER(answers.get("_step") or "basics")
    t = (text or "").strip()
    logger.info(f"[cover] step={step} text_len={len(t)}")

    # BASICS
    if step == "basics":
        if "," not in t:
            return resume_flow.QUESTIONS["basics"]
        answers["basics"] = resume_flow.parse_basics(t)
        _advance(db, job, answers, "role_company")
        return ("Great! Now tell me the role and company you're applying to.\n"
                "Format: Position Title, Company Name\n\n"
                "Example: Senior HR Manager, Google")

    # ROLE + COMPANY
    if step == "role_company":
        parts = [p.strip() for p in t.split(",")]
        if len(parts) < 2:
            return "Please send: Position Title, Company Name\n\nExample: Senior HR Manager, Google"
        answers["cover_role"] = parts[0]
        answers["cover_company"] = parts[1]
        answers["target_role"] = parts[0]
        _advance(db, job, answers, "experience_overview")
        return ("How many years of experience do you have in this field, and which industries?\n\n"
                "Format: [Years], [Industry/Industries]\n\n"
                "Example: 15 years, HR and Talent Management")

    # EXPERIENCE OVERVIEW
    if step == "experience_overview":
        parts = [p.strip() for p in t.split(",", 1)]
        if len(parts) < 2:
            return "Please send: Years of experience, Industry\n\nExample: 15 years, HR and Talent Management"
        answers["years_experience"] = parts[0]
        answers["industries"] = parts[1]
        _advance(db, job, answers, "interest_reason")
        return ("Why are you interested in this specific role or company?\n\n"
                "Example: I'm excited about your company's commitment to employee development and innovative HR practices")

    # INTEREST REASON
    if step == "interest_reason":
        if not t:
            return "Please share why you're interested in this role or company."
        answers["interest_reason"] = t
        _advance(db, job, answers, "current_role")
        return ("What is your current (or most recent) job title and employer?\n\n"
                "Format: Job Title, Employer\n\n"
                "Example: HR Director, Microsoft")

    # CURRENT ROLE
    if step == "current_role":
        parts = [p.strip() for p in t.split(",", 1)]
        if len(parts) < 2:
            return "Please send: Job Title, Employer\n\nExample: HR Director, Microsoft"
        answers["current_title"] = parts[0]
        answers["current_employer"] = parts[1]
        _advance(db, job, answers, "achievement_1")
        return ("Describe a key achievement or responsibility with quantified results.\n\n"
                "Include:\n"
                "• What you did\n"
                "• The measurable outcome\n\n"
                "Example: Redesigned the recruitment process to shorten time to hire by 35% while improving first-year retention by 20%")

    # ACHIEVEMENT 1
    if step == "achievement_1":
        if not t:
            return "Please share a key achievement with quantified results."
        answers["achievement_1"] = t
        _advance(db, job, answers, "achievement_2")
        return ("Share another key achievement (optional).\n\n"
                "Example: Partnered with leadership on workforce planning during company expansion, delivering 40% cost savings\n\n"
                "Or type *skip* to continue")

    # ACHIEVEMENT 2
    if step == "achievement_2":
        if t.lower() not in {"skip", "done"}:
            answers["achievement_2"] = t
        _advance(db, job, answers, "key_skills")
        return ("List 3-5 key skills most relevant to this role (separated by commas).\n\n"
                "Example: HRIS implementation, performance management, compensation benchmarking, employee relations, DEI initiatives")

    # KEY SKILLS
    if step == "key_skills":
        if not t:
            return "Please list 3-5 key skills separated by commas."
        skills_list = [s.strip() for s in t.split(",")]
        answers["cover_key_skills"] = skills_list
        _advance(db, job, answers, "company_goal")
        return (f"What specific goal or objective at {answers.get('cover_company', 'the company')} do you want to support?\n\n"
                "Example: Building a more diverse and inclusive workplace culture")

    # COMPANY GOAL
    if step == "company_goal":
        if not t:
            return "Please share what company goal you want to support."
        answers["company_goal"] = t
        _advance(db, job, answers, "preview")
        preview_text = _format_cover_preview(answers)
        return f"{preview_text}\n\nLooks good? Reply *yes* to generate your cover letter, or */reset* to start over."

    # PREVIEW
    if step == "preview":
        if t.lower() in {"yes", "y", "confirm", "ok"}:
            doc_type = "cover"
            if not payments.can_generate(user, doc_type):
                return payments.get_purchase_prompt(doc_type)
            try:
                credit_type = payments.consume_credit(user, doc_type, db)
            except ValueError:
                return payments.get_purchase_prompt(doc_type)
            answers["_credit_type"] = credit_type

            try:
                logger.info(f"[cover] Rendering cover letter for job.id={job.id}")
                doc_bytes = renderer.render_cover_letter(job)
                filename = _generate_filename(job)
                file_path = storage.save_file_locally(job.id, doc_bytes, filename)
                job.draft_text = file_path
                job.status = "preview_ready"
                db.commit()
                _advance(db, job, answers, "done")
                return f"__SEND_DOCUMENT__|{job.id}|{filename}"
            except Exception as e:
                logger.error(f"[cover] Rendering failed: {e}")
                job.status = "render_failed"
                job.draft_text = f"Error: {str(e)}"
                db.commit()
                _advance(db, job, answers, "done")
                if user and user.telegram_user_id:
                    await handle_error(
                        ErrorType.RENDER_FAILURE,
                        user.telegram_user_id,
                        "docx_render_failed",
                        context={"doc_type": "cover letter"},
                        exception=e,
                    )
                return ""

        preview_text = _format_cover_preview(answers)
        return f"{preview_text}\n\nLooks good? Reply *yes* to generate your cover letter, or */reset* to start over."

    return resume_flow.QUESTIONS.get(step, resume_flow.QUESTIONS["basics"])


async def get_admin_stats(db: Session) -> str:
    from app.services import analytics
    from datetime import datetime

    stats = analytics.get_system_analytics(db, days=7)
    if 'error' in stats:
        return f"❌ Error generating stats: {stats['error']}"

    users = stats['users']
    docs = stats['documents']
    pay = stats['payments']
    engagement = stats['engagement']

    stats_msg = f"""📊 *Career Buddy - Analytics Dashboard*
_Last 7 days overview_

*👥 USER METRICS*
• Total Users: {users['total']}
• New Users: {users['new']}
• Active Users: {users['active']}
• With Credits: {users.get('paid', 0)}

*📄 DOCUMENT METRICS*
• Total Generated: {docs['total']}
• Recent (7d): {docs['recent']}
• Avg per User: {docs['avg_per_user']}

_By Type:_
• 📄 Resumes: {docs['resumes']}
• 📋 CVs: {docs['cvs']}
• 📝 Cover Letters: {docs['cover_letters']}
• ✨ Revamps: {docs['revamps']}

*💰 REVENUE METRICS*
• Transactions: {pay['total_transactions']}
• Revenue: ₦{pay['total_revenue']:,.0f}
• Avg Transaction: ₦{pay['avg_transaction']:,.0f}

*💬 ENGAGEMENT*
• Total Messages: {engagement['total_messages']}
• Recent (7d): {engagement['recent_messages']}
• Avg per User: {engagement['avg_messages_per_user']}

"""

    if stats.get('top_users'):
        stats_msg += "*🏆 TOP USERS*\n"
        for u in stats['top_users'][:3]:
            stats_msg += f"• {u['username']}: {u['documents']} docs\n"
        stats_msg += "\n"

    stats_msg += f"_Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC_"
    return stats_msg


async def broadcast_message(db: Session, message: str, sender_id: str) -> str:
    from app.services import telegram
    all_users = db.query(User).all()
    success_count = 0
    fail_count = 0
    broadcast_text = f"""📢 *Announcement from Career Buddy*

{message}"""
    for u in all_users:
        try:
            await telegram.reply_text(u.telegram_user_id, broadcast_text)
            success_count += 1
        except Exception as e:
            logger.error(f"[broadcast] Failed to send to {u.telegram_user_id}: {e}")
            fail_count += 1
    return (f"✅ *Broadcast Complete!*\n\n"
            f"• Sent: {success_count}\n"
            f"• Failed: {fail_count}\n"
            f"• Total: {len(all_users)}")


async def admin_set_user_pro(db: Session, telegram_user_id: str, admin_id: str) -> str:
    """Admin command to manually grant credits to a user."""
    user = db.query(User).filter(User.telegram_user_id == telegram_user_id).first()
    if not user:
        return f"❌ *User Not Found*\n\nNo user found with Telegram ID: `{telegram_user_id}`"

    user.document_credits = (user.document_credits or 0) + 2
    user.cover_letter_credits = (user.cover_letter_credits or 0) + 1
    payments.record_waived_payment(db, user.id, "admin_grant", reference=f"admin-{admin_id}-{telegram_user_id}")
    db.commit()
    logger.info(f"[admin] Credits granted to user {user.id} by admin {admin_id}")

    from app.services import telegram
    try:
        await telegram.reply_text(
            telegram_user_id,
            "🎉 *Credits Added!*\n\n"
            "You've been granted:\n"
            "• 📄 2 document credits\n"
            "• ✉️ 1 cover letter credit\n\n"
            f"Your balance:\n{payments.get_credit_summary(user)}\n\n"
            "Type /status to see your credits!",
        )
    except Exception as e:
        logger.error(f"[admin] Failed to notify user {telegram_user_id}: {e}")

    return (f"✅ *Credits Granted*\n\n"
            f"@{user.telegram_username or telegram_user_id} received 2 doc + 1 CL credits.\n"
            f"Current: {payments.get_credit_summary(user)}")


async def generate_sample_document(db: Session, user_id: int, template_choice: str = "template_1", doc_type: str = "resume") -> tuple[str, str]:
    import json
    from pathlib import Path

    sample_file = Path(__file__).parent.parent.parent / "sample_resume_data.json"
    try:
        with open(sample_file, 'r', encoding='utf-8') as f:
            sample_data = json.load(f)
    except Exception as e:
        logger.error(f"[generate_sample] Failed to load sample data: {e}")
        raise Exception("Failed to load sample data file")

    sample_data["template"] = template_choice
    sample_data["_step"] = "done"

    job = Job(
        user_id=user_id,
        type=doc_type,
        status="preview_ready",
        answers=sample_data
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info(f"[generate_sample] Created sample job.id={job.id} with template={template_choice}")

    try:
        if doc_type == "cv":
            doc_bytes = renderer.render_cv(job)
        elif doc_type == "cover":
            doc_bytes = renderer.render_cover_letter(job)
        else:
            doc_bytes = renderer.render_resume(job)
        filename = _generate_filename(job)
        file_path = storage.save_file_locally(job.id, doc_bytes, filename)
        job.status = "completed"
        job.file_path = file_path
        db.commit()
        logger.info(f"[generate_sample] Generated sample document: {filename}")
        return (job.id, filename)
    except Exception as e:
        logger.error(f"[generate_sample] Document generation failed: {e}")
        job.status = "failed"
        db.commit()
        raise Exception(f"Document generation failed: {str(e)}")


async def handle_inbound(db: Session, telegram_user_id: str, text: str, msg_id: str | None = None, telegram_username: str | None = None, first_name: str = "there") -> str:
    # 0) Ensure user
    user = db.query(User).filter(User.telegram_user_id == telegram_user_id).first()
    if not user:
        user = User(
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            telegram_first_name=first_name if first_name != "there" else None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"[handle_inbound] Created new user telegram_user_id={telegram_user_id}")
    else:
        if first_name and first_name != "there" and not getattr(user, "telegram_first_name", None):
            user.telegram_first_name = first_name
            db.commit()
        db.refresh(user)
        logger.info(f"[handle_inbound] User {telegram_user_id}")

    incoming = (text or "").strip()
    if "@" in incoming and incoming.startswith("/"):
        incoming = incoming.split("@")[0].strip()
    t_lower = incoming.lower()

    # 1) Log inbound message
    db.add(Message(user_id=user.id, direction="inbound", content=incoming))
    db.commit()

    # 1.4) Onboarding: user awaiting intent response
    onboarding_step = getattr(user, "onboarding_step", None)
    if onboarding_step == "awaiting_intent_response":
        if t_lower in HELP_COMMANDS:
            return HELP_MESSAGE + "\n\n_What brings you here today? Tell me what you're looking for._"
        if t_lower in STATUS_COMMANDS:
            summary = payments.get_credit_summary(user)
            return f"📊 *Your credits:*\n{summary}\n\n_What brings you here today? Tell me what you're looking for._"
        reply = onboarding_flow.handle_onboarding_intent_response(db, user, incoming, telegram_user_id, first_name)
        if reply:
            return reply

    # 1.44) /start with referral code
    if incoming.startswith("/start ") and len(incoming.split()) > 1:
        parts = incoming.split()
        if len(parts) > 1 and parts[1].startswith("ref_"):
            ref_code = parts[1].replace("ref_", "").strip()
            if ref_code and not getattr(user, "referred_by_code", None):
                from app.services import referral as referral_svc
                referral_svc.handle_referral_signup(user, ref_code, db)

    # 1.45) /start and greetings
    is_start = t_lower in GREETINGS or t_lower.startswith("/start")
    if is_start:
        if hasattr(user, "onboarding_step") and user.onboarding_step:
            user.onboarding_step = None
            db.commit()
        is_onboarded = getattr(user, "onboarding_complete", True) or True
        job_count = db.query(Job).filter(Job.user_id == user.id).count()
        active_job = _active_collecting_job(db, user.id)
        if not is_onboarded and job_count == 0:
            return onboarding_flow.handle_new_user_welcome(db, user, first_name)
        if active_job:
            doc_label = {"resume": "resume", "cv": "CV", "cover": "cover letter"}.get(active_job.type, active_job.type)
            msg = onboarding_flow.ACTIVE_JOB_PROMPT.format(first_name=first_name, doc_type=doc_label)
            return f"__SHOW_ONBOARDING_CONTINUE_MENU__|{msg}"
        msg = onboarding_flow.RETURNING_USER_MENU.format(first_name=first_name)
        return f"__SHOW_DOCUMENT_MENU__|credits|{msg}"

    # 1.5) Admin commands
    is_admin_command = any(t_lower.startswith(cmd) for cmd in ADMIN_COMMANDS)
    if is_admin_command:
        if not is_admin(telegram_user_id):
            logger.warning(f"[handle_inbound] Non-admin {telegram_user_id} tried admin command: {t_lower}")
            return "⚠️ This command is only available to administrators."

        logger.info(f"[handle_inbound] Admin {telegram_user_id} using command: {t_lower}")
        if t_lower in {"/stats", "/admin"}:
            return await get_admin_stats(db)
        elif t_lower.startswith("/broadcast "):
            broadcast_msg = incoming[len("/broadcast "):].strip()
            if broadcast_msg:
                return await broadcast_message(db, broadcast_msg, telegram_user_id)
            return ("📢 *Broadcast Command*\n\n"
                    "*Usage:* /broadcast <message>\n\n"
                    "*Example:* /broadcast Hello everyone! New features coming soon!")
        elif t_lower.startswith("/setpro ") or t_lower.startswith("/makeadmin "):
            target_user_id = incoming.split(maxsplit=1)[1].strip() if len(incoming.split()) > 1 else ""
            if target_user_id:
                return await admin_set_user_pro(db, target_user_id, telegram_user_id)
            return ("👤 *Grant Credits to User*\n\n"
                    "*Usage:* /setpro <telegram\\_user\\_id>\n\n"
                    "*Example:* /setpro 123456789\n\n"
                    "_Grants 2 doc + 1 CL credits and notifies the user._")
        elif t_lower.startswith("/sample"):
            parts = incoming.split()
            if len(parts) < 2:
                return ("📄 *Generate Sample Document*\n\n"
                        "Type the complete command in ONE message:\n\n"
                        "✅ `/sample resume` - Generate sample resume\n"
                        "✅ `/sample cv` - Generate sample CV\n"
                        "✅ `/sample cover` - Generate sample cover letter\n\n"
                        "Optional: Add template number (1-3):\n"
                        "✅ `/sample resume 2` - Resume with template 2\n\n"
                        "_Note: Type the full command at once, not separately!_")
            doc_type = parts[1].lower()
            if doc_type not in {"resume", "cv", "cover"}:
                return "❌ Invalid document type!\n\nUse: `/sample resume`, `/sample cv`, or `/sample cover`"
            template_num = "1"
            if len(parts) > 2 and parts[2] in {"1", "2", "3"}:
                template_num = parts[2]
            template_choice = f"template_{template_num}"
            try:
                logger.info(f"[handle_inbound] Admin generating sample {doc_type} with {template_choice}")
                job_id, filename = await generate_sample_document(db, user.id, template_choice, doc_type)
                return f"__SEND_DOCUMENT__|{job_id}|{filename}"
            except Exception as e:
                logger.error(f"[handle_inbound] Sample generation failed: {e}")
                error_msg = str(e).replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
                return (f"❌ *Sample Generation Failed*\n\n"
                        f"Error: `{error_msg}`\n\n"
                        f"Please check the logs for details.")

    # 1.6) Help command
    if t_lower in HELP_COMMANDS:
        active_for_help = _active_collecting_job(db, user.id)
        if active_for_help:
            step = (active_for_help.answers or {}).get("_step", "basics")
            step_label = STEP_LABELS.get(step, step)
            step_prompt = STEP_REPROMPTS.get(step, "Let's continue from where we left off.")
            doc_label = {"resume": "resume", "cv": "CV", "cover": "cover letter"}.get(active_for_help.type, active_for_help.type)
            return f"{HELP_MESSAGE}\n\n━━━━━━━━━━━━━━━━━━━━\n📄 *Back to your {doc_label}*\n\nWe're on: *{step_label}*\n\n{step_prompt}"
        return HELP_MESSAGE

    # 1.7) Status command
    if t_lower in STATUS_COMMANDS:
        logger.info(f"[handle_inbound] Processing /status for user {telegram_user_id}")
        summary = payments.get_credit_summary(user)
        status_msg = f"""📊 *Your Account Status*

👤 User: {user.name or user.telegram_username or 'User'}

*Your Credits:*
{summary}

*Pricing:*
• Resume/CV — {payments.PRICE_DISPLAY['resume']}
• Cover Letter — {payments.PRICE_DISPLAY['cover_letter']}
• Bundle (2 docs + 1 CL) — {payments.PRICE_DISPLAY['bundle']} _save ₦3,000_

Type /buy\\_resume, /buy\\_cv, /buy\\_cover\\_letter, or /buy\\_bundle to purchase.
Type /referral to earn free credits!

Ready to create? Type /start!"""
        return status_msg

    # 1.7.4) Render retry
    if t_lower in {"retry", "try again", "retry again"}:
        render_failed_job = (
            db.query(Job)
            .filter(Job.user_id == user.id, Job.status == "render_failed")
            .order_by(Job.created_at.desc())
            .first()
        )
        if render_failed_job:
            answers = render_failed_job.answers or {}
            answers["_step"] = "draft_ready" if render_failed_job.type in {"resume", "cv"} else "preview"
            render_failed_job.answers = answers
            render_failed_job.status = "collecting"
            flag_modified(render_failed_job, "answers")
            db.commit()
            db.refresh(render_failed_job)
            if render_failed_job.type in {"resume", "cv"}:
                reply = await handle_resume(db, render_failed_job, "retry")
            elif render_failed_job.type == "cover":
                reply = await handle_cover(db, render_failed_job, "yes")
            else:
                reply = ""
            db.add(Message(user_id=user.id, job_id=render_failed_job.id, direction="outbound", content=reply or ""))
            db.commit()
            return reply

    # 1.7.5) History command
    if t_lower in HISTORY_COMMANDS:
        logger.info(f"[handle_inbound] Processing /history for user {telegram_user_id}")
        from app.services import document_history
        counts = document_history.count_user_documents(db, user.id)
        history = document_history.get_user_document_history(db, user.id, limit=5)
        history_msg = f"""📚 *Your Document History*

📊 Total Documents: {counts['total']}
• 📄 Resumes: {counts['resumes']}
• 📋 CVs: {counts['cvs']}
• 📝 Cover Letters: {counts['cover_letters']}
• ✨ Revamps: {counts['revamps']}

"""
        if history:
            history_msg += "*Recent Documents:*\n\n"
            for idx, doc in enumerate(history, 1):
                history_msg += f"{idx}. *{doc['type']}* - {doc['name']}\n"
                history_msg += f"   Role: {doc['target_role']}\n"
                history_msg += f"   Created: {doc['created_at']}\n\n"
        else:
            history_msg += "_You haven't created any documents yet._\n\n"
        history_msg += "Ready to create more? Type /start!"
        return history_msg

    # 1.8) Buy commands
    if t_lower in BUY_COMMANDS:
        product_map = {
            "/buy_resume": "resume",
            "/buy_cv": "cv",
            "/buy_cover_letter": "cover_letter",
            "/buy_bundle": "bundle",
        }
        product_type = product_map.get(t_lower)
        if not product_type:
            return "Invalid command. Try /buy\\_resume, /buy\\_cv, /buy\\_cover\\_letter, or /buy\\_bundle."
        logger.info(f"[handle_inbound] Buy command: {product_type} for user {telegram_user_id}")
        result = await payments.initiate_payment(user, product_type, db)
        if "error" in result:
            return ("❌ Sorry, we couldn't create your payment link. Please try again later.\n\n"
                    "Support: 07063011079")
        price = payments.PRICE_DISPLAY.get(product_type, "")
        awards = payments.CREDIT_AWARDS.get(product_type, {})
        award_lines = []
        if awards.get("document_credits"):
            award_lines.append(f"📄 {awards['document_credits']} document credit{'s' if awards['document_credits'] > 1 else ''}")
        if awards.get("cover_letter_credits"):
            award_lines.append(f"✉️ {awards['cover_letter_credits']} cover letter credit{'s' if awards['cover_letter_credits'] > 1 else ''}")
        award_text = "\n".join(award_lines)
        return (f"💳 *Payment Link Created*\n\n"
                f"Product: *{product_type.replace('_', ' ').title()}*\n"
                f"Price: *{price}*\n\n"
                f"You'll receive:\n{award_text}\n\n"
                f"Click here to pay:\n{result['payment_url']}\n\n"
                f"_Credits will be added automatically after payment._")

    # 1.9) PDF conversion command
    if t_lower in PDF_COMMANDS or ("convert" in t_lower and "pdf" in t_lower):
        logger.info(f"[handle_inbound] Processing /pdf for user {telegram_user_id}")
        return await convert_to_pdf(db, user, telegram_user_id)

    # 1.9.5) Revision flow — check BEFORE other routing
    revising_job = _active_revising_job(db, user.id)
    if revising_job:
        from app.flows import revision
        return revision.handle_revision_step(db, revising_job, incoming, telegram_user_id)

    # 1.9.6) /revise command
    if t_lower in REVISE_COMMANDS:
        from app.flows.revision import start_revision, _get_latest_done_job
        latest_done = _get_latest_done_job(db, user.id)
        if not latest_done:
            return "You don't have any completed documents to revise yet. Create one first with /start!"
        latest_done.status = "revising"
        db.commit()
        return start_revision(db, latest_done, telegram_user_id)

    # 1.9.7) /referral command
    if t_lower in REFERRAL_COMMANDS:
        from app.services import referral as referral_svc
        from app.config import settings as app_settings
        code = referral_svc.get_or_create_referral_code(user, db)
        bot_username = app_settings.telegram_bot_username
        link = f"https://t.me/{bot_username}?start=ref_{code}"
        credits = getattr(user, "referral_credits", 0) or 0
        return (
            f"Share your link and earn a *free document credit* every time "
            f"someone you refer makes their first purchase!\n\n"
            f"Your link:\n{link}\n\n"
            f"*Your credits:* {credits}\n\n"
            f"Credits apply automatically on your next document — no code needed."
        )

    # 2) Reset/menu
    if t_lower in RESETS:
        j = _active_collecting_job(db, user.id)
        if j:
            j.status = "closed"
            db.commit()
            logger.info(f"[handle_inbound] Reset triggered, closed job.id={j.id}")
        return "__SHOW_MENU__"

    # 3) Get/create active job (based on intent if present)
    active_job = _active_collecting_job(db, user.id)
    doc_type = infer_type(incoming) if not active_job else None
    logger.info(f"[handle_inbound] doc_type={doc_type}, active_job={'Yes' if active_job else 'No'}, user.id={user.id}")

    # Gate: check credit at flow entry for new jobs
    if doc_type and not active_job:
        if not payments.can_generate(user, doc_type):
            return payments.get_purchase_prompt(doc_type)

    # Block revamp feature
    if doc_type == "revamp":
        logger.info(f"[handle_inbound] Blocking revamp feature for user {user.id} - coming soon")
        return ("✨ *Revamp Feature - Coming Soon!*\n\n"
                "We're working on an exciting new feature to revamp and enhance your existing resumes!\n\n"
                "In the meantime, you can:\n"
                "• 📄 Create a new Resume\n"
                "• 📋 Generate a CV\n"
                "• 📝 Write a Cover Letter\n\n"
                "Type /start to see all available options!")

    job = get_active_job(db, user.id, doc_type)
    _log_state("after get_active_job", job)

    if not job and not doc_type:
        return "__SHOW_MENU__"

    # 4) Job-level deduplication
    if _dedupe(db, job, msg_id):
        return ""

    # 5) Ensure answers dict + step
    ans = job.answers if isinstance(job.answers, dict) else {}
    if not ans or not ans.get("_step"):
        ans = resume_flow.start_context()
        ans["_step"] = "basics"
        job.answers = ans
        flag_modified(job, "answers")
        db.commit()
        logger.info(f"[handle_inbound] Initialized job.id={job.id} with step=basics")

    logger.info(f"[router] before step-check, step={ans.get('_step')}")

    # 6) Route to the correct flow
    if job.type in {"resume", "cv"}:
        reply = await handle_resume(db, job, incoming)
        _log_state("after handle_resume", job)
    elif job.type == "revamp":
        reply = await handle_revamp(db, job, incoming)
        _log_state("after handle_revamp", job)
    elif job.type == "cover":
        reply = await handle_cover(db, job, incoming)
        _log_state("after handle_cover", job)
    else:
        reply = "Unsupported document type. Please reply *Resume*, *CV*, *Cover Letter*, or *Revamp* to begin."

    # 7) Log outbound message
    db.add(Message(user_id=user.id, job_id=job.id, direction="outbound", content=reply or ""))
    db.commit()

    return reply
