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
from app.services.idempotency import seen_or_mark
from app.services import renderer, storage, ai, payments

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
HISTORY_COMMANDS = {"/history", "history", "my documents", "documents"}
UPGRADE_COMMANDS = {"/upgrade", "upgrade"}
PAYMENT_BYPASS_PHRASES = {"payment made", "paid", "payment done", "payment complete"}
ADMIN_COMMANDS = {"/admin", "/stats", "/broadcast", "/sample", "/makeadmin", "/setpro"}
PDF_COMMANDS = {"/pdf", "pdf", "convert to pdf", "convert pdf"}
FORCE_LOWER = lambda s: (s or "").strip().lower()


def is_admin(telegram_user_id: str) -> bool:
    """Check if user is an admin."""
    from app.config import settings
    return telegram_user_id in settings.admin_telegram_ids


def _progress_bar(current_step: int, total_steps: int) -> str:
    """Generate a visual progress bar."""
    filled = "●" * current_step
    empty = "○" * (total_steps - current_step)
    percentage = int((current_step / total_steps) * 100)
    return f"{filled}{empty} {percentage}% ({current_step}/{total_steps})"


def _add_progress(message: str, step: str) -> str:
    """Add progress indicator to a message based on current step."""
    # Define step order and total for resume/CV flow
    steps_order = ["basics", "summary", "skills", "experiences", "experience_bullets", 
                   "education", "projects", "target_role", "review"]
    
    if step not in steps_order:
        return message
    
    current = steps_order.index(step) + 1
    total = len(steps_order)
    progress = _progress_bar(current, total)
    
    return f"📊 *Progress:* {progress}\n\n{message}"


# Help message
HELP_MESSAGE = """🤖 *Career Buddy - Help Guide*

I help you create professional resumes, CVs, and cover letters tailored to your dream role!

*📝 Available Documents:*
• *Resume* - 1-2 page professional resume
• *CV* - Detailed curriculum vitae
• *Revamp* - Coming Soon!
• *Cover Letter* - Premium feature

*🎯 How It Works:*
1. Choose your document type
2. Answer my questions step by step
3. I'll enhance your content with AI
4. Receive your professional document!

*💡 Commands:*
/start - Start creating a document
/status - Check your plan & remaining documents
/upgrade - Upgrade to Premium
/pdf - Convert document to PDF (Premium)
/reset - Cancel and start over
/help - Show this help message

*💳 Pricing:*
• *Free Plan*: 2 free documents
• *Pay-Per-Generation*: ₦7,500 per document
• *Premium Plan*: ₦7,500 (one-time, all features)

*⭐ Premium Features:*
• Multiple professional templates
• Unlimited PDF conversions
• Priority AI enhancements
• All document types

*🆘 Need Support?*
Contact: @your_support_username

Ready to begin? Just type /start!"""


def _advance(db: Session, job: Job, answers: dict, next_step: str):
    """
    Advance to the next step AND commit immediately to prevent loops.
    """
    answers["_step"] = next_step
    job.answers = answers
    # CRITICAL: Tell SQLAlchemy the JSON field was modified
    flag_modified(job, "answers")
    db.commit()
    db.refresh(job)
    logger.info(f"[_advance] job.id={job.id} advanced to step={next_step}")


def _dedupe(db: Session, job: Job, msg_id: str | None) -> bool:
    """
    Return True if this is a duplicate and should be ignored.
    Commit immediately to prevent race conditions.
    """
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
    """
    Generate a user-friendly filename: "Name - Document Type.docx"
    Example: "John Doe - Resume.docx", "Jane Smith - CV.docx"
    """
    answers = job.answers or {}
    basics = answers.get('basics', {})
    name = basics.get('name', 'Document')
    
    # Clean name for filename (remove special characters)
    import re
    clean_name = re.sub(r'[<>:"/\\|?*]', '', name)
    
    # Map job types to display names
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
    """Format a preview of all collected information for user review."""
    basics = answers.get("basics", {})
    target_role = answers.get("target_role", "")
    summary = answers.get("summary", "")
    skills = answers.get("skills", [])
    experiences = answers.get("experiences", [])
    education = answers.get("education", [])
    projects = answers.get("projects", [])

    lines = ["📋 *Preview of Your Information*\n"]

    # Basics
    lines.append("*Contact Details:*")
    lines.append(f"Name: {basics.get('name', 'N/A')}")
    if target_role:
        lines.append(f"Target Role: {target_role}")
    lines.append(f"Email: {basics.get('email', 'N/A')}")
    lines.append(f"Phone: {basics.get('phone', 'N/A')}")
    lines.append(f"Location: {basics.get('location', 'N/A')}")
    lines.append("")

    # Summary (AI-generated)
    if summary:
        lines.append("*Professional Summary:* 🤖")
        lines.append(summary)
        lines.append("")

    # Skills (AI-assisted)
    if skills:
        lines.append("*Skills:* 🤖")
        lines.append(", ".join(skills))
        lines.append("")

    # Experiences
    if experiences:
        lines.append(f"*Work Experience:* ({len(experiences)} position{'s' if len(experiences) != 1 else ''})")
        for i, exp in enumerate(experiences, 1):
            lines.append(f"{i}. {exp.get('role', 'N/A')} at {exp.get('company', 'N/A')}")
            bullets = exp.get("bullets", [])
            lines.append(f"   ({len(bullets)} achievement{'s' if len(bullets) != 1 else ''})")
        lines.append("")

    # Education
    if education:
        lines.append(f"*Education:* ({len(education)} entr{'ies' if len(education) != 1 else 'y'})")
        lines.append("")

    # Projects
    if projects:
        lines.append(f"*Projects/Certifications:* ({len(projects)} item{'s' if len(projects) != 1 else ''})")
        lines.append("")

    return "\n".join(lines)


async def convert_to_pdf(db: Session, user: User, telegram_user_id: str) -> str:
    """
    Trigger PDF conversion for the most recent .docx document.
    The actual conversion is handled by send_pdf_to_user in webhook.py
    
    Args:
        db: Database session
        user: User object
        telegram_user_id: Telegram user ID
    
    Returns:
        Marker string to trigger PDF conversion and sending
    """
    # Check if user has PDF permission
    if not payments.can_use_pdf(user):
        return (f"🔒 *PDF Format is a Premium Feature*\n\n"
                f"Upgrade to Premium to unlock:\n"
                f"• Unlimited PDF conversions\n"
                f"• 2 Resume + 2 CV per month\n"
                f"• 1 Cover Letter\n"
                f"• All premium features\n\n"
                f"Type */upgrade* for just ₦{payments.PREMIUM_PACKAGE_PRICE:,}/month!")
    
    # Return marker with telegram_user_id for send_pdf_to_user
    return f"__SEND_PDF__|{telegram_user_id}|placeholder"


def _format_cover_preview(answers: dict) -> str:
    """Format preview for cover letter data."""
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


def _new_job(db: Session, user_id, doc_type: str) -> Job:
    # Set initial step based on doc type
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


def maybe_finalize(db: Session, job: Job) -> bool:
    ans = job.answers if isinstance(job.answers, dict) else {}
    basics_ok = bool(ans.get("basics", {}).get("name"))
    has_exp = len(ans.get("experiences", [])) >= 1
    last_has_bullets = has_exp and len(ans["experiences"][-1].get("bullets", [])) >= 1

    if basics_ok and last_has_bullets:
        job.status = "draft_ready"
        db.commit()
        logger.info(f"[finalize] job.id={job.id} → draft_ready")
        return True
    return False


async def handle_resume(db: Session, job: Job, text: str, user_tier: str = "free") -> str:
    # Check quota reset and premium expiry FIRST
    user = db.query(User).filter(User.id == job.user_id).first()
    payments.check_and_reset_quota(db, user)
    payments.check_premium_expiry(db, user)
    db.refresh(user)  # Refresh to get updated values
    
    answers = job.answers or resume_flow.start_context()
    step = FORCE_LOWER(answers.get("_step") or "basics")
    t = (text or "").strip()
    t_lower = t.lower()
    logger.info(f"[resume] step={step} text='{t[:80]}' tier={user.tier}")

    # ---- BASICS ----
    if step == "basics":
        if answers.get("basics", {}).get("name"):
            _advance(db, job, answers, "target_role")
            return resume_flow.QUESTIONS["target_role"]
        if "," not in t:
            return resume_flow.QUESTIONS["basics"]

        answers["basics"] = resume_flow.parse_basics(t)
        _advance(db, job, answers, "target_role")
        return resume_flow.QUESTIONS["target_role"]

    # ---- TARGET ROLE ----
    if step == "target_role":
        if not t:
            return resume_flow.QUESTIONS["target_role"]

        answers["target_role"] = t.strip()

        # Store target role in basics for document rendering
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
            # Advance to skills
            _advance(db, job, answers, "skills")
            step = "skills"
            # Fall through to skills below
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
        # Check if AI skills were already generated
        ai_skills = answers.get("ai_suggested_skills", [])
        
        if not ai_skills:
            # Generate AI skills on first entry
            try:
                target_role = answers.get("target_role", "")
                experiences = answers.get("experiences", [])
                basics = answers.get("basics", {})

                # Generate 5-8 skill suggestions
                suggested_skills = ai.generate_skills(target_role, basics, experiences, tier=user_tier)
                suggested_skills = suggested_skills[:8]  # Limit to 8

                # Store in answers
                answers["ai_suggested_skills"] = suggested_skills
                job.answers = answers
                flag_modified(job, "answers")
                db.commit()

                # Return formatted selection menu
                return resume_flow.format_skills_selection(suggested_skills)
                
            except Exception as e:
                logger.error(f"[skills] AI generation failed: {e}")
                # Fallback to manual entry
                return ("⚠️ AI skills generation unavailable.\n\n"
                        "💡 *List your top 5-8 skills* (comma-separated)\n\n"
                        "*Example:* Python, Data Analysis, SQL, Communication")
        
        # User is selecting from AI skills
        if not t:
            # Show the skills again
            return resume_flow.format_skills_selection(ai_skills)
        
        # Parse user selection (numbers or custom skills)
        selected_skills = resume_flow.parse_skill_selection(t, ai_skills)
        
        if not selected_skills or len(selected_skills) < 3:
            return ("❌ *Invalid selection!*\n\n"
                    "Please enter skill numbers (comma-separated):\n"
                    "*Example:* 1,3,5,7\n\n"
                    "Or type your own skills (comma-separated).\n"
                    "Need at least 3 skills.")
        
        answers["skills"] = selected_skills
        _advance(db, job, answers, "personal_info")
        
        # Move to personal_info before generating summary
        return resume_flow.QUESTIONS["personal_info"]

    # ---- SUMMARY (AI-GENERATED, REQUIRED) ----
    if step == "summary":
        # Check if summary was already generated
        if not answers.get("summary"):
            # Generate AI summary
            try:
                summary = ai.generate_summary(answers, tier=user_tier)
                answers["summary"] = summary
                job.answers = answers
                flag_modified(job, "answers")
                db.commit()

                return (f"✨ *AI-Generated Professional Summary:*\n\n"
                        f"{summary}\n\n"
                        f"━━━━━━━━━━━━━━━━\n\n"
                        f"✅ Happy with this? Type *yes* to continue.\n"
                        f"Or send your own summary to replace it.")
                
            except Exception as e:
                logger.error(f"[summary] AI generation failed: {e}")
                return ("⚠️ AI summary generation unavailable.\n\n"
                        "Please write a 2-3 sentence professional summary:\n\n"
                        "*Example:* Data Analyst with 5+ years building dashboards.")
        
        # User can edit the summary or accept it
        if t_lower in {"yes", "y", "ok", "okay", "good", "done"}:
            # Accept the AI-generated summary
            pass
        elif t:
            # User provided their own summary
            answers["summary"] = t
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()
        else:
            # Show the generated summary again
            return (f"✨ *Your Professional Summary:*\n\n"
                    f"{answers['summary']}\n\n"
                    f"Type *yes* to accept, or send your own summary.")

        # Move to preview/review
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
        
        # Move to summary generation (using personal_info)
        _advance(db, job, answers, "summary")
        step = "summary"
        # Fall through to summary generation

    # ---- PREVIEW ----
    if step == "preview":
        # If user just arrived at preview, show summary
        if not t or t.lower() in {"done", "skip"}:
            preview_text = _format_preview(answers)
            return f"{preview_text}\n\nLooks good? Reply *yes* to generate your document, or */reset* to start over."

        # User confirmed
        if t.lower() in {"yes", "y", "confirm", "ok", "okay"}:
            # Check if premium user - offer template selection
            user = db.query(User).filter(User.id == job.user_id).first()
            if user and user.tier != "free":
                # Premium users get to choose template
                _advance(db, job, answers, "template_selection")
                return "__SHOW_TEMPLATE_MENU__"
            else:
                # Free users get default template 1
                answers["template"] = "template_1"
            _advance(db, job, answers, "finalize")
            step = "finalize"
            # Fall through to finalization
        else:
            # User wants to make changes
            return ("To make changes, please type */reset* to start over.\n\n"
                    "Or reply *yes* to proceed with generating your document.")

    # ---- TEMPLATE SELECTION (handled via callback, but add safety) ----
    if step == "template_selection":
        # This step is handled via inline keyboard callback
        # If user somehow sends a text message, guide them
        return ("Please click one of the template buttons above to continue.\n\n"
                "Or type */reset* to start over.")

    # ---- PAYMENT REQUIRED ----
    if step == "payment_required":
        # User needs to pay before generating
        if t.lower() == "pay":
            user = db.query(User).filter(User.id == job.user_id).first()
            target_role = answers.get("target_role", "Unknown Role")

            # Create payment link
            payment_result = await payments.create_payment_link(user, target_role)

            if "error" in payment_result:
                return ("❌ Sorry, we couldn't create your payment link. Please try again later or contact support.\n\n"
                        "Support: 07063011079")

            # Store payment reference in job for tracking
            answers["payment_reference"] = payment_result.get("reference")
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()

            return (f"💳 *Payment Link Created*\n\n"
                    f"Amount: ₦{payments.PAID_GENERATION_PRICE:,}\n\n"
                    f"Click here to pay: {payment_result.get('authorization_url')}\n\n"
                    "After payment, return here and type *paid* to continue.")

        if t.lower() == "paid":
            # Gateway waived: mark as paid and continue
            user = db.query(User).filter(User.id == job.user_id).first()
            payments.record_waived_payment(db, user.id, answers.get("target_role", "Unknown Role"))

            answers.pop("payment_reference", None)
            answers["paid_generation"] = True
            _advance(db, job, answers, "finalize")

            step = "finalize"
            t = ""  # Reset text to proceed with finalization

        else:
            return (f"🎯 *Payment Required*\n\n"
                    f"Each document costs ₦{payments.PAID_GENERATION_PRICE:,}.\n\n"
                    "Reply *pay* to get your payment link, or type */reset* to cancel.")

    # ---- FINALIZE ----
    if step == "finalize":
        # Check if user wants to pay
        if t.lower() == "pay":
            user = db.query(User).filter(User.id == job.user_id).first()
            target_role = answers.get("target_role", "Unknown Role")

            # Create payment link
            payment_result = await payments.create_payment_link(user, target_role)

            if "error" in payment_result:
                return ("❌ Sorry, we couldn't create your payment link. Please try again later or contact support.\n\n"
                        "Support: 07063011079")

            # Store payment reference in job for tracking
            answers["payment_reference"] = payment_result.get("reference")
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()

            return (f"💳 *Payment Link Created*\n\n"
                    f"Amount: ₦{payments.PAID_GENERATION_PRICE:,}\n\n"
                    f"Click here to pay: {payment_result.get('authorization_url')}\n\n"
                    "After payment, return here and type *paid* to continue.")

        # Check if user claims to have paid
        if t.lower() == "paid":
            # Gateway waived: mark as paid and continue
            user = db.query(User).filter(User.id == job.user_id).first()
            payments.record_waived_payment(db, user.id, target_role)

            answers.pop("payment_reference", None)
            answers["paid_generation"] = True
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()

            t = ""

        # Check generation limits before proceeding
        user = db.query(User).filter(User.id == job.user_id).first()
        doc_type = "cv" if job.type == "cv" else "resume"

        can_gen, reason = payments.can_generate_document(user, doc_type)

        if not can_gen:
            if reason.startswith("quota_exceeded"):
                _, doc_name, limit = reason.split("|")
                
                # Show upgrade message
                return (f"📊 *{doc_name.upper()} Quota Reached*\n\n"
                        f"You've used all {limit} {doc_name}{'s' if int(limit) > 1 else ''} in your {user.tier} plan.\n\n"
                        f"💡 *Upgrade to Premium for:*\n"
                        f"• More documents (2 Resume + 2 CV)\n"
                        f"• 1 Cover Letter\n"
                        f"• PDF format\n"
                        f"• All features unlocked\n\n"
                        f"Type */upgrade* to get Premium for just ₦{payments.PREMIUM_PACKAGE_PRICE:,}/month!")
            
            elif reason.startswith("document_not_allowed"):
                return (f"❌ *This document type requires Premium*\n\n"
                        f"Type */upgrade* to unlock all document types!")

        # Track the generation
        payments.update_document_count(db, user, doc_type)

        # Note: AI enhancement already applied during flow (skills and summary generation)
        logger.info(f"[handle_resume] Finalizing job.id={job.id}")

        # Render document
        try:
            logger.info(f"[handle_resume] Rendering document for job.id={job.id}")
            if job.type == "cv":
                doc_bytes = renderer.render_cv(job)
            else:
                doc_bytes = renderer.render_resume(job)

            # Save file locally with user-friendly name
            filename = _generate_filename(job)
            file_path = storage.save_file_locally(job.id, doc_bytes, filename)

            # Store document temporarily for sending via Telegram
            # We'll use draft_text to store the file path
            job.draft_text = file_path
            job.status = "preview_ready"
            db.commit()
            logger.info(f"[handle_resume] Document rendered successfully: {file_path}")

        except Exception as e:
            logger.error(f"[handle_resume] Document rendering failed: {e}")
            job.status = "draft_ready"
            job.draft_text = f"Error: {str(e)}"
            db.commit()
            _advance(db, job, job.answers, "done")
            return f"❌ Sorry, document generation failed: {str(e)}"

        _advance(db, job, job.answers, "done")
        # Return special marker to trigger document sending
        return f"__SEND_DOCUMENT__|{job.id}|{filename}"

    # ---- DONE ----
    if step == "done":
        # Job is complete, prompt user to start a new one
        return "Your document has been sent! Reply */reset* to create another document, or *menu* to see options."

    # Safety: never fall back; re-ask current step
    return resume_flow.QUESTIONS.get(step, resume_flow.QUESTIONS["basics"])


async def handle_revamp(db: Session, job: Job, text: str, user_tier: str = "free") -> str:
    """
    Handle resume/CV revamp flow.
    User uploads their existing resume file (DOCX/PDF) and AI improves it.
    """
    # Check quota reset and premium expiry FIRST
    user = db.query(User).filter(User.id == job.user_id).first()
    payments.check_and_reset_quota(db, user)
    payments.check_premium_expiry(db, user)
    db.refresh(user)  # Refresh to get updated values
    
    answers = job.answers or {"_step": "upload"}
    step = FORCE_LOWER(answers.get("_step") or "upload")
    t = (text or "").strip()
    logger.info(f"[revamp] step={step} text_len={len(t)} tier={user.tier}")

    # ---- UPLOAD ----
    if step == "upload":
        # Show upload instructions
        if not t or t.lower() in {"revamp", "revamp existing", "revamp existing (soon)"}:
            upload_msg = "📄 *Resume/CV Revamp*\n\n"
            upload_msg += "I'll help improve your existing resume or CV with AI-powered enhancements!\n\n"
            upload_msg += "*📤 Upload Your Resume:*\n"
            
            if user_tier == "pro":
                upload_msg += "✅ Supported formats: .docx, .pdf\n"
            else:
                upload_msg += "✅ Supported format: .docx\n"
                upload_msg += "💡 Upgrade to Premium for PDF support\n"
            
            upload_msg += "\n*How It Works:*\n"
            upload_msg += "1. Tap the 📎 attachment icon\n"
            upload_msg += "2. Select your resume file\n"
            upload_msg += "3. Send it to me\n"
            upload_msg += "4. I'll analyze and improve it with AI\n"
            upload_msg += "5. You'll get a professionally revamped version!\n\n"
            upload_msg += "_Maximum file size: 10MB_"
            
            return upload_msg

        # User sent text instead of uploading
        return ("📎 *Please upload your resume file*\n\n"
                "I need you to upload your existing resume as a file (not paste text).\n\n"
                "*Steps:*\n"
                "1. Tap the 📎 attachment button\n"
                "2. Choose your resume file (.docx format)\n"
                "3. Send it to me\n\n"
                "Or type */reset* to cancel.")

    # ---- REVAMP PROCESSING ----
    if step == "revamp_processing":
        # Call AI to revamp the content
        original = answers.get("original_content", "")

        try:
            from app.services import ai
            revamped_content = ai.revamp_resume(original, tier=user_tier)

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
            # Check generation limits
            user = db.query(User).filter(User.id == job.user_id).first()
            can_gen, reason = payments.can_generate_document(user, "revamp")
            if not can_gen:
                if reason.startswith("quota_exceeded"):
                    _, doc_name, limit = reason.split("|")
                    
                    return (f"📊 *Revamp Quota Reached*\n\n"
                            f"You've used all {limit} revamp{'s' if int(limit) > 1 else ''} in your {user.tier} plan.\n\n"
                            f"💡 *Upgrade to Premium for:*\n"
                            f"• More documents\n"
                            f"• PDF format\n"
                            f"• All features unlocked\n\n"
                            f"Type */upgrade* to get Premium for just ₦{payments.PREMIUM_PACKAGE_PRICE:,}/month!")
                
                elif reason.startswith("document_not_allowed"):
                    return (f"❌ *Revamp requires Premium*\n\n"
                            f"Type */upgrade* to unlock all features!")

            # Track generation
            payments.update_document_count(db, user, "revamp")

            try:
                # Render revamped document
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

    # ---- PAYMENT REQUIRED (REVAMP) ----
    if step == "payment_required":
        # Check if user is now premium (may have upgraded since reaching this step)
        user = db.query(User).filter(User.id == job.user_id).first()
        
        if user and user.tier == "pro":
            # User is premium now - bypass payment and proceed to generation
            logger.info(f"[revamp] User {user.id} is premium, bypassing payment for revamp")
            answers.pop("payment_reference", None)
            answers["paid_generation"] = True
            
            # Track generation
            target_role = answers.get("target_role", "Revamp")
            payments.update_generation_count(db, user, target_role)
            
            try:
                # Render revamped document
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
        
        # User is still free tier - handle payment
        if t.lower() == "pay":
            target_role = answers.get("target_role", "Revamp")

            payment_result = await payments.create_payment_link(user, target_role)
            if "error" in payment_result:
                return ("❌ Sorry, we couldn't create your payment link. Please try again later or contact support.\n\n"
                        "Support: 07063011079")

            answers["payment_reference"] = payment_result.get("reference")
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()

            return (f"💳 *Payment Link Created*\n\n"
                    f"Amount: ₦{payments.PAID_GENERATION_PRICE:,}\n\n"
                    f"Click here to pay: {payment_result.get('authorization_url')}\n\n"
                    "After payment, return here and type *paid* to continue.")

        if t.lower() == "paid":
            # Waive payment for now
            payments.record_waived_payment(db, user.id, answers.get("target_role", "Revamp"))

            answers.pop("payment_reference", None)
            answers["paid_generation"] = True
            _advance(db, job, answers, "preview")
            return "✅ Payment waived! Reply *yes* to generate your improved document."

        return (f"🎯 *Payment Required*\n\nEach document costs ₦{payments.PAID_GENERATION_PRICE:,}.\n"
                "Reply *pay* to get your payment link, or */reset* to cancel.")


async def handle_cover(db: Session, job: Job, text: str, user_tier: str = "free") -> str:
    """
    Professional cover letter flow matching HR template.
    Steps: basics -> role_company -> experience_overview -> interest_reason -> 
           current_role -> achievement_1 -> achievement_2 -> key_skills -> 
           company_goal -> preview -> finalize
    """
    # Check quota reset and premium expiry FIRST
    user = db.query(User).filter(User.id == job.user_id).first()
    payments.check_and_reset_quota(db, user)
    payments.check_premium_expiry(db, user)
    db.refresh(user)  # Refresh to get updated values
    
    answers = job.answers or {"_step": "basics"}
    step = FORCE_LOWER(answers.get("_step") or "basics")
    t = (text or "").strip()
    logger.info(f"[cover] step={step} text_len={len(t)} tier={user.tier}")

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
            user = db.query(User).filter(User.id == job.user_id).first()
            can_gen, reason = payments.can_generate_document(user, "cover_letter")
            if not can_gen:
                if reason.startswith("quota_exceeded"):
                    return (f"📊 *Cover Letter Quota Reached*\n\n"
                            f"You've used all cover letters in your {user.tier} plan.\n\n"
                            f"💡 *Upgrade to Premium for:*\n"
                            f"• 1 Cover Letter per month\n"
                            f"• More documents\n"
                            f"• PDF format\n\n"
                            f"Type */upgrade* to get Premium for just ₦{payments.PREMIUM_PACKAGE_PRICE:,}/month!")
                
                elif reason.startswith("document_not_allowed"):
                    return (f"❌ *Cover Letters require Premium*\n\n"
                            f"Upgrade to Premium and get:\n"
                            f"• 1 Cover Letter per month\n"
                            f"• 2 Resume + 2 CV\n"
                            f"• PDF format\n\n"
                            f"Type */upgrade* for just ₦{payments.PREMIUM_PACKAGE_PRICE:,}/month!")

            payments.update_document_count(db, user, "cover_letter")

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
                _advance(db, job, answers, "done")
                return f"❌ Sorry, cover letter generation failed: {str(e)}"

        preview_text = _format_cover_preview(answers)
        return f"{preview_text}\n\nLooks good? Reply *yes* to generate your cover letter, or */reset* to start over."

    # PAYMENT REQUIRED
    if step == "payment_required":
        # Check if user is now premium (may have upgraded since reaching this step)
        user = db.query(User).filter(User.id == job.user_id).first()
        
        if user and user.tier == "pro":
            # User is premium now - bypass payment and proceed to generation
            logger.info(f"[cover] User {user.id} is premium, bypassing payment for cover letter")
            answers.pop("payment_reference", None)
            answers["paid_generation"] = True
            
            # Track generation
            target_role = answers.get("cover_role", "Cover Letter")
            payments.update_generation_count(db, user, target_role)
            
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
                _advance(db, job, answers, "done")
                return f"❌ Sorry, cover letter generation failed: {str(e)}"
        
        # User is still free tier - handle payment
        if t.lower() == "pay":
            target_role = answers.get("cover_role", "Cover Letter")

            payment_result = await payments.create_payment_link(user, target_role)
            if "error" in payment_result:
                return ("❌ Sorry, we couldn't create your payment link. Please try again later or contact support.\n\n"
                        "Support: 07063011079")

            answers["payment_reference"] = payment_result.get("reference")
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()

            return (f"💳 *Payment Link Created*\n\n"
                    f"Amount: ₦{payments.PAID_GENERATION_PRICE:,}\n\n"
                    f"Click here to pay: {payment_result.get('authorization_url')}\n\n"
                    "After payment, return here and type *paid* to continue.")

        if t.lower() == "paid":
            # Waive payment for now
            payments.record_waived_payment(db, user.id, answers.get("cover_role", "Cover Letter"))

            answers.pop("payment_reference", None)
            answers["paid_generation"] = True
            _advance(db, job, answers, "preview")
            preview_text = _format_cover_preview(answers)
            return f"✅ Payment waived!\n\n{preview_text}\n\nReply *yes* to generate your cover letter."

        return (f"🎯 *Payment Required*\n\nEach document costs ₦{payments.PAID_GENERATION_PRICE:,}.\n"
                "Reply *pay* to get your payment link, or */reset* to cancel.")

    return resume_flow.QUESTIONS.get(step, resume_flow.QUESTIONS["basics"])

    return "Something went wrong. Please type */reset* to start over."


async def get_admin_stats(db: Session) -> str:
    """Get comprehensive bot statistics for admin using analytics service."""
    from app.services import analytics
    from datetime import datetime
    
    # Get comprehensive analytics
    stats = analytics.get_system_analytics(db, days=7)
    
    if 'error' in stats:
        return f"❌ Error generating stats: {stats['error']}"
    
    users = stats['users']
    docs = stats['documents']
    payments = stats['payments']
    engagement = stats['engagement']
    
    stats_msg = f"""📊 *Career Buddy - Analytics Dashboard*
_Last 7 days overview_

*👥 USER METRICS*
• Total Users: {users['total']}
• New Users: {users['new']}
• Active Users: {users['active']}
• Premium: {users['premium']} ({users['premium_percentage']}%)
• Free: {users['free']}

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
• Transactions: {payments['total_transactions']}
• Revenue: ₦{payments['total_revenue']:,.0f}
• Avg Transaction: ₦{payments['avg_transaction']:,.0f}

*💬 ENGAGEMENT*
• Total Messages: {engagement['total_messages']}
• Recent (7d): {engagement['recent_messages']}
• Avg per User: {engagement['avg_messages_per_user']}

"""
    
    # Add top users
    if stats.get('top_users'):
        stats_msg += "*🏆 TOP USERS*\n"
        for user in stats['top_users'][:3]:
            tier_emoji = "⭐" if user['tier'] == "pro" else "🆓"
            stats_msg += f"{tier_emoji} {user['username']}: {user['documents']} docs\n"
        stats_msg += "\n"
    
    stats_msg += f"_Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC_"
    
    return stats_msg


async def broadcast_message(db: Session, message: str, sender_id: str) -> str:
    """Broadcast a message to all users."""
    from app.services import telegram
    
    all_users = db.query(User).all()
    success_count = 0
    fail_count = 0
    
    broadcast_text = f"""📢 *Announcement from Career Buddy*

{message}"""
    
    for user in all_users:
        try:
            await telegram.reply_text(user.telegram_user_id, broadcast_text)
            success_count += 1
        except Exception as e:
            logger.error(f"[broadcast] Failed to send to {user.telegram_user_id}: {e}")
            fail_count += 1
    
    return (f"✅ *Broadcast Complete!*\n\n"
           f"• Sent: {success_count}\n"
           f"• Failed: {fail_count}\n"
           f"• Total: {len(all_users)}")


async def handle_upgrade_command(db: Session, user: User) -> str:
    """Handle /upgrade command - shows upgrade info with test bypass."""
    from app.services import payments
    
    # Check quota status
    quota_status = payments.get_quota_status(user)
    
    # Check if already premium
    if user.tier == "pro":
        # Show remaining quota
        expires = quota_status.get("premium_expires_at", "Unknown")
        resets = quota_status.get("quota_resets_at", "Unknown")
        
        return f"""✅ *You're Already Premium!*

📊 *Current Quota:*
• Resume: {quota_status['resume']['remaining']}/{quota_status['resume']['limit']} remaining
• CV: {quota_status['cv']['remaining']}/{quota_status['cv']['limit']} remaining
• Cover Letter: {quota_status['cover_letter']['remaining']}/{quota_status['cover_letter']['limit']} remaining
• Revamp: {quota_status['revamp']['remaining']}/{quota_status['revamp']['limit']} remaining

⏰ *Quota resets:* {resets[:10] if resets != "Unknown" else "Soon"}
⭐ *Premium expires:* {expires[:10] if expires != "Unknown" else "Soon"}

Type /status for full details."""
    
    # For testing - no real payment gateway
    return f"""⭐ *Upgrade to Premium - ₦{payments.PREMIUM_PACKAGE_PRICE:,}/month*

🎯 *What You Get:*
• 📄 *2 Resumes* per month
• 📄 *2 CVs* per month
• 💼 *1 Cover Letter* per month
• ✨ *1 Revamp* per month
• 🎨 *3 Professional Templates*
• 📱 *PDF Format* (instant conversion)
• 🚀 *Priority AI Enhancements*

📊 *Compare Plans:*

*FREE:*
• 1 Resume/month
• 1 CV/month
• 1 Revamp/month
• DOCX only
• ❌ No cover letters

*PREMIUM:*
• 2 Resumes/month
• 2 CVs/month
• 1 Cover Letter/month
• 1 Revamp/month
• PDF + DOCX formats

💳 *Monthly Subscription:* ₦{payments.PREMIUM_PACKAGE_PRICE:,}
✅ *Auto-renews* every 30 days
📅 *Quota resets* monthly

*🧪 TEST MODE - To upgrade, simply type:* `payment made`

_Note: Real payment gateway will be integrated in production_"""


async def admin_set_user_pro(db: Session, telegram_user_id: str, admin_id: str) -> str:
    """Admin command to manually upgrade a user to pro tier."""
    from app.services import payments
    
    # Find the user
    user = db.query(User).filter(User.telegram_user_id == telegram_user_id).first()
    
    if not user:
        return f"❌ *User Not Found*\n\nNo user found with Telegram ID: `{telegram_user_id}`"
    
    # Check if already pro
    if user.tier == "pro":
        return f"""ℹ️ *Already Premium*

User @{user.telegram_username or telegram_user_id} is already on the pro tier.

*Current Status:*
• Tier: Pro
• Total generations: {payments.get_total_generations(user)}"""
    
    # Upgrade user
    user.tier = "pro"
    
    # Record a waived payment for tracking
    payments.record_waived_payment(db, user.id, "admin_upgrade", reference=f"admin-{admin_id}-{telegram_user_id}")
    
    db.commit()
    logger.info(f"[admin] User {user.id} upgraded to pro by admin {admin_id}")
    
    # Notify the user
    from app.services import telegram
    try:
        await telegram.reply_text(
            telegram_user_id,
            """🎉 *Congratulations!*

Your account has been upgraded to Premium!

You now have access to:
• 🎨 Multiple professional templates
• 📄 Unlimited PDF conversions
• 🚀 Priority AI enhancements
• 💼 All document types

Type /status to see your premium features!"""
        )
    except Exception as e:
        logger.error(f"[admin] Failed to notify user {telegram_user_id} of upgrade: {e}")
    
    return f"""✅ *User Upgraded Successfully*

@{user.telegram_username or telegram_user_id} has been upgraded to Pro tier.

*Updated Status:*
• Tier: Pro
• Total generations: {payments.get_total_generations(user)}
• User notified: ✓"""


async def generate_sample_document(db: Session, user_id: int, template_choice: str = "template_1", doc_type: str = "resume") -> tuple[str, str]:
    """
    Generate a sample document with pre-filled data for admin testing.
    
    Args:
        db: Database session
        user_id: User ID
        template_choice: Template to use (template_1, template_2, or template_3)
        doc_type: Document type (resume, cv, or cover)
    
    Returns:
        Tuple of (job_id, filename)
    """
    import json
    import os
    from pathlib import Path
    
    # Load sample data
    # __file__ is /app/app/services/router.py, so go up 3 levels to /app/
    sample_file = Path(__file__).parent.parent.parent / "sample_resume_data.json"
    
    try:
        with open(sample_file, 'r', encoding='utf-8') as f:
            sample_data = json.load(f)
    except Exception as e:
        logger.error(f"[generate_sample] Failed to load sample data: {e}")
        raise Exception("Failed to load sample data file")
    
    # Add template choice
    sample_data["template"] = template_choice
    sample_data["_step"] = "done"
    
    # Create a job with sample data
    job = Job(
        user_id=user_id,
        type=doc_type,  # Use the specified doc type
        status="preview_ready",
        answers=sample_data
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    logger.info(f"[generate_sample] Created sample job.id={job.id} with template={template_choice}")
    
    # Generate the document
    try:
        # Call appropriate renderer based on doc type
        if doc_type == "cv":
            doc_bytes = renderer.render_cv(job)
        elif doc_type == "cover":
            doc_bytes = renderer.render_cover_letter(job)
        else:  # resume
            doc_bytes = renderer.render_resume(job)
        
        # Generate user-friendly filename for sample
        filename = _generate_filename(job)
        
        # Save to storage
        file_path = storage.save_file_locally(job.id, doc_bytes, filename)
        
        # Update job status
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


async def handle_inbound(db: Session, telegram_user_id: str, text: str, msg_id: str | None = None, telegram_username: str | None = None) -> str:
    # NOTE: Deduplication is handled in webhook.py before calling this function

    # 0) Ensure user
    user = db.query(User).filter(User.telegram_user_id == telegram_user_id).first()
    if not user:
        user = User(
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            tier="free"  # Default to free tier
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"[handle_inbound] Created new user telegram_user_id={telegram_user_id} tier=free")
    else:
        # Refresh user from database to ensure we have the latest tier status
        db.refresh(user)
        logger.info(f"[handle_inbound] User {telegram_user_id} tier={user.tier}")

    incoming = (text or "").strip()
    t_lower = incoming.lower()

    # 1) Log inbound message
    db.add(Message(user_id=user.id, direction="inbound", content=incoming))
    db.commit()

    # 1.5) Admin commands (only for admins)
    # Check if message starts with any admin command
    is_admin_command = any(t_lower.startswith(cmd) for cmd in ADMIN_COMMANDS)
    
    if is_admin_command:
        if not is_admin(telegram_user_id):
            logger.warning(f"[handle_inbound] Non-admin {telegram_user_id} tried to use admin command: {t_lower}")
            return "⚠️ This command is only available to administrators."
        
        logger.info(f"[handle_inbound] Admin {telegram_user_id} using command: {t_lower}")
        if t_lower in {"/stats", "/admin"}:
            return await get_admin_stats(db)
        elif t_lower.startswith("/broadcast "):
            # Extract message after "/broadcast "
            broadcast_msg = incoming[len("/broadcast "):].strip()
            if broadcast_msg:
                return await broadcast_message(db, broadcast_msg, telegram_user_id)
            else:
                return ("📢 *Broadcast Command*\n\n"
                       "*Usage:* /broadcast <message>\n\n"
                       "*Example:* /broadcast Hello everyone! New features coming soon!")
        elif t_lower.startswith("/setpro ") or t_lower.startswith("/makeadmin "):
            # Extract telegram user ID after the command
            target_user_id = incoming.split(maxsplit=1)[1].strip() if len(incoming.split()) > 1 else ""
            if target_user_id:
                return await admin_set_user_pro(db, target_user_id, telegram_user_id)
            else:
                return ("👤 *Upgrade User to Premium*\n\n"
                       "*Usage:* /setpro <telegram_user_id>\n\n"
                       "*Example:* /setpro 123456789\n\n"
                       "_This will upgrade the user to Pro tier and notify them._")
        elif t_lower.startswith("/sample"):
            # Generate sample document for testing
            # Usage: /sample <type> [template]
            # Example: /sample resume 1, /sample cv 2, /sample cover 3
            parts = incoming.split()
            
            # Check if doc type is provided
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
                return ("❌ Invalid document type!\n\n"
                       "Use: `/sample resume`, `/sample cv`, or `/sample cover`")
            
            template_num = "1"  # Default to template 1
            if len(parts) > 2 and parts[2] in {"1", "2", "3"}:
                template_num = parts[2]
            
            template_choice = f"template_{template_num}"
            
            try:
                logger.info(f"[handle_inbound] Admin generating sample {doc_type} with {template_choice}")
                
                job_id, filename = await generate_sample_document(db, user.id, template_choice, doc_type)
                
                # Return marker to send document
                return f"__SEND_DOCUMENT__|{job_id}|{filename}"
            
            except Exception as e:
                logger.error(f"[handle_inbound] Sample generation failed: {e}")
                error_msg = str(e).replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
                return (f"❌ *Sample Generation Failed*\n\n"
                       f"Error: `{error_msg}`\n\n"
                       f"Please check the logs for details.")

    # 1.6) Help command
    if t_lower in HELP_COMMANDS:
        return HELP_MESSAGE

    # 1.7) Status command
    if t_lower in STATUS_COMMANDS:
        logger.info(f"[handle_inbound] Processing /status command for user {telegram_user_id}")
        
        # Get quota status
        quota_status = payments.get_quota_status(user)
        
        # Special status for admin users
        if quota_status['tier'] == 'admin':
            status_msg = f"""👑 *Admin Account Status*

👤 User: {user.name or user.telegram_username or 'Admin'}
🎯 Plan: **ADMIN** (Unlimited Access)

📦 *Quota:*
📄 Resume: ∞ (Unlimited)
📄 CV: ∞ (Unlimited)
💼 Cover Letter: ∞ (Unlimited)
✨ Revamp: ∞ (Unlimited)

📱 PDF Format: ✅ Enabled (Unlimited)

🚀 *Admin Privileges:*
• Unlimited document generation
• All document types unlocked
• PDF conversion always available
• No quota restrictions
• No expiry date

Ready to create? Type /start!"""
            return status_msg
        
        status_msg = f"""📊 *Your Account Status*

👤 User: {user.name or user.telegram_username or 'User'}
🎯 Plan: {'Premium ⭐' if user.tier == 'pro' else 'Free'}

📦 *Monthly Quota:*
📄 Resume: {quota_status['resume']['used']}/{quota_status['resume']['limit']} used ({quota_status['resume']['remaining']} remaining)
📄 CV: {quota_status['cv']['used']}/{quota_status['cv']['limit']} used ({quota_status['cv']['remaining']} remaining)
💼 Cover Letter: {quota_status['cover_letter']['used']}/{quota_status['cover_letter']['limit']} used ({quota_status['cover_letter']['remaining']} remaining)
✨ Revamp: {quota_status['revamp']['used']}/{quota_status['revamp']['limit']} used ({quota_status['revamp']['remaining']} remaining)

📱 PDF Format: {'✅ Enabled' if quota_status['pdf_allowed'] else '❌ Upgrade Required'}

"""
        
        # Show reset/expiry dates
        if quota_status.get('quota_resets_at'):
            from datetime import datetime
            try:
                reset_date = datetime.fromisoformat(quota_status['quota_resets_at'])
                status_msg += f"⏰ Quota resets: {reset_date.strftime('%B %d, %Y')}\n"
            except:
                pass
        
        if user.tier == 'pro' and quota_status.get('premium_expires_at'):
            from datetime import datetime
            try:
                expires_date = datetime.fromisoformat(quota_status['premium_expires_at'])
                status_msg += f"⭐ Premium expires: {expires_date.strftime('%B %d, %Y')}\n"
            except:
                pass
        
        if user.tier == "free":
            status_msg += f"""
💡 *Upgrade to Premium?*
For just ₦{payments.PREMIUM_PACKAGE_PRICE:,}/month, get:
• 2 Resumes + 2 CVs
• 1 Cover Letter
• PDF format
• All premium features

Type */upgrade* to get started!
"""
        
        status_msg += "\nReady to create? Type /start!"
        return status_msg

    # 1.7.5) History command
    if t_lower in HISTORY_COMMANDS:
        logger.info(f"[handle_inbound] Processing /history command for user {telegram_user_id}")
        from app.services import document_history
        
        # Get document counts
        counts = document_history.count_user_documents(db, user.id)
        
        # Get recent documents
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

    # 1.8) Upgrade command
    if t_lower in UPGRADE_COMMANDS:
        logger.info(f"[handle_inbound] Processing /upgrade command for user {telegram_user_id}")
        return await handle_upgrade_command(db, user)
    
    # 1.8.5) Payment bypass for testing (no real payment gateway)
    if t_lower in PAYMENT_BYPASS_PHRASES:
        logger.info(f"[handle_inbound] Payment bypass triggered for user {telegram_user_id}")
        
        # Check if already premium
        if user.tier == "pro":
            quota_status = payments.get_quota_status(user)
            return f"""✅ You're already a Premium user!

📊 *Current Quota:*
• Resume: {quota_status['resume']['remaining']}/{quota_status['resume']['limit']} remaining
• CV: {quota_status['cv']['remaining']}/{quota_status['cv']['limit']} remaining
• Cover Letter: {quota_status['cover_letter']['remaining']}/{quota_status['cover_letter']['limit']} remaining
• Revamp: {quota_status['revamp']['remaining']}/{quota_status['revamp']['limit']} remaining

Type /status for full details."""
        
        # Upgrade user to premium using the new system
        success = payments.upgrade_to_premium(db, user)
        
        if not success:
            return "❌ Sorry, there was an error upgrading your account. Please try again or contact support."
        
        # Record waived payment for tracking
        payments.record_waived_payment(db, user.id, "premium_package", reference=f"test-{telegram_user_id}")
        
        # Refresh user to get updated tier
        db.refresh(user)
        logger.info(f"[handle_inbound] User {user.id} upgraded to premium via bypass")
        
        return f"""🎉 *Welcome to Premium!*

✅ Account upgraded successfully

📦 *Your Monthly Package:*
• 📄 2 Resumes
• 📄 2 CVs
• 💼 1 Cover Letter
• ✨ 1 Revamp
• 📱 PDF Format (unlimited conversions)
• 🎨 3 Professional Templates

⏰ *Renews:* Monthly (auto-reset)
💳 *Price:* ₦{payments.PREMIUM_PACKAGE_PRICE:,}/month

*🚀 Ready to create?*
Type /start to see the menu, then choose:
• *Resume* - Professional 1-2 page resume
• *CV* - Detailed curriculum vitae
• *Cover Letter* - Tailored application letter
• *Revamp* - Improve an existing document

Or simply type what you want to create!"""

    # 1.9) PDF conversion command
    if t_lower in PDF_COMMANDS or "convert" in t_lower and "pdf" in t_lower:
        logger.info(f"[handle_inbound] Processing /pdf command for user {telegram_user_id}")
        return await convert_to_pdf(db, user, telegram_user_id)

    # 2) Reset/menu
    if t_lower in RESETS:
        j = _active_collecting_job(db, user.id)
        if j:
            j.status = "closed"
            db.commit()
            logger.info(f"[handle_inbound] Reset triggered, closed job.id={j.id}")
        return "__SHOW_MENU__"

    if t_lower in GREETINGS:
        return "__SHOW_MENU__"

    # 2.5) Handle tier selection (Free/Premium)
    if t_lower in {"free", "premium", "pro"}:
        # Update user tier
        if t_lower == "free":
            user.tier = "free"
            tier_msg = "✅ *Free Plan activated!*\n\nYou get *2 free documents* to create professional resumes and CVs with AI assistance.\n\nAfter that, each additional document costs ₦7,500.\n\nLet's build something great together!"
        else:  # premium or pro
            user.tier = "free"  # Still free tier, but they know about payment
            tier_msg = "✅ *Ready to get started!*\n\nYou get *2 free documents* with AI-powered generation.\n\nAfter that, each document costs ₦7,500 with enhanced AI features:\n• Business impact analysis\n• Senior-level summaries\n• Priority support\n\nLet's create something exceptional!"

        db.commit()
        db.refresh(user)
        logger.info(f"[handle_inbound] Updated user telegram_user_id={telegram_user_id} to tier={user.tier}")

        # Log the tier confirmation message
        db.add(Message(user_id=user.id, direction="outbound", content=tier_msg))
        db.commit()

        # Return marker to show document type menu with confirmation message
        return f"__SHOW_DOCUMENT_MENU__|{user.tier}|{tier_msg}"

    # 3) Get/create active job (based on intent if present)
    doc_type = infer_type(incoming)
    logger.info(f"[handle_inbound] doc_type={doc_type}, user.tier={user.tier}, user.id={user.id}")

    # Check if free user is trying to access cover letter
    if doc_type == "cover" and user.tier == "free":
        logger.warning(f"[handle_inbound] Blocking free user {user.id} from cover letter. Tier: {user.tier}")
        return ("💼 *Cover Letters are a Premium feature*\n\n"
                "Upgrade to Premium and unlock:\n"
                "✨ Professional cover letter generation\n"
                "✨ Enhanced AI with business impact analysis\n"
                "✨ Senior-level summaries\n"
                "✨ Priority support\n\n"
                "Ready to upgrade? Type *Premium* to get started!")
    
    if doc_type == "cover" and user.tier != "free":
        logger.info(f"[handle_inbound] Allowing premium user {user.id} (tier={user.tier}) to access cover letter")
    
    # Block revamp feature - Coming Soon
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

    # 4) Job-level deduplication (prevent double-processing same message)
    if _dedupe(db, job, msg_id):
        return ""  # Already processed

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
        reply = await handle_resume(db, job, incoming, user_tier=user.tier)
        _log_state("after handle_resume", job)
    elif job.type == "revamp":
        reply = await handle_revamp(db, job, incoming, user_tier=user.tier)
        _log_state("after handle_revamp", job)
    elif job.type == "cover":
        reply = await handle_cover(db, job, incoming, user_tier=user.tier)
        _log_state("after handle_cover", job)
    else:
        reply = "Unsupported document type. Please reply *Resume*, *CV*, *Cover Letter*, or *Revamp* to begin."

    # 7) Log outbound message
    db.add(Message(user_id=user.id, job_id=job.id, direction="outbound", content=reply or ""))
    db.commit()

    return reply