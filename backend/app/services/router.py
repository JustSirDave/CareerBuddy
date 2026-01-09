from __future__ import annotations
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import User, Job, Message
from app.flows import resume as resume_flow
from app.services.idempotency import seen_or_mark
from app.services import orchestrator, renderer, storage, ai, payments

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
ADMIN_COMMANDS = {"/admin", "/stats", "/broadcast", "/sample"}
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
• *Revamp* - Improve your existing resume/CV
• *Cover Letter* - Coming soon!

*🎯 How It Works:*
1. Choose your document type
2. Answer my questions step by step
3. I'll enhance your content with AI
4. Receive your professional document!

*💡 Commands:*
/start - Start creating a document
/status - Check your plan & remaining documents
/reset - Cancel and start over
/help - Show this help message

*💳 Pricing:*
• *Free Plan*: 2 free documents
• *Pay-Per-Generation*: ₦7,500 per document

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
    # Return marker with telegram_user_id for send_pdf_to_user
    return f"__SEND_PDF__|{telegram_user_id}|placeholder"


def _format_cover_preview(answers: dict) -> str:
    """Format preview for cover letter data."""
    basics = answers.get("basics", {})
    role = answers.get("cover_role") or answers.get("target_role", "")
    company = answers.get("cover_company", "")
    highlights = answers.get("cover_highlights", [])

    lines = ["📋 *Cover Letter Preview*\n"]
    lines.append(f"Name: {basics.get('name', 'N/A')}")
    lines.append(f"Email: {basics.get('email', 'N/A')}")
    lines.append(f"Phone: {basics.get('phone', 'N/A')}")
    lines.append(f"Location: {basics.get('location', 'N/A')}")
    lines.append("")
    lines.append(f"Role: {role or 'N/A'}")
    lines.append(f"Company: {company or 'N/A'}")
    lines.append("")
    if highlights:
        lines.append("*Highlights:*")
        for h in highlights:
            lines.append(f"- {h}")
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
    job = Job(
        user_id=user_id,
        type=doc_type,
        status="collecting",
        answers=resume_flow.start_context() | {"_step": "basics"},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info(f"[new_job] Created job.id={job.id} type={doc_type}")
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
    answers = job.answers or resume_flow.start_context()
    step = FORCE_LOWER(answers.get("_step") or "basics")
    t = (text or "").strip()
    t_lower = t.lower()
    logger.info(f"[resume] step={step} text='{t[:80]}' tier={user_tier}")

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
        target_role = answers.get("target_role", "Unknown Role")

        can_gen, reason = payments.can_generate(user, target_role)

        if not can_gen:
            # Allow paid users to bypass free-tier limit
            if reason == "free_limit_reached" and answers.get("paid_generation"):
                can_gen = True
            elif reason == "free_limit_reached":
                # Set step to payment_required so user can't skip
                _advance(db, job, answers, "payment_required")
                # Return payment marker to trigger payment UI
                return f"__PAYMENT_REQUIRED__|{target_role}|{payments.PAID_GENERATION_PRICE}"
            elif reason.startswith("max_per_role"):
                _, role_name = reason.split("|")
                return (f"⚠️ *Maximum generations reached for '{role_name}'*\n\n"
                        f"You've already created {payments.MAX_GENERATIONS_PER_ROLE} documents for this role. "
                        "To prevent duplication, we limit generations per role.\n\n"
                        "Please type */reset* to create a document for a different role.")

        # Track the generation
        payments.update_generation_count(db, user, target_role)

        # Enhance content with AI
        logger.info(f"[handle_resume] Finalizing job.id={job.id}, enhancing content...")
        try:
            enhanced_answers = orchestrator.batch_enhance_content(answers)
            job.answers = enhanced_answers
            flag_modified(job, "answers")
        except Exception as e:
            logger.error(f"[handle_resume] AI enhancement failed: {e}, continuing with original")

        # Render document
        try:
            logger.info(f"[handle_resume] Rendering document for job.id={job.id}")
            if job.type == "cv":
                doc_bytes = renderer.render_cv(job)
            else:
                doc_bytes = renderer.render_resume(job)

            # Save file locally for backup
            filename = f"{job.type}_{job.id[:8]}.docx"
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
    User pastes their existing resume and AI improves it.
    """
    answers = job.answers or {"_step": "upload"}
    step = FORCE_LOWER(answers.get("_step") or "upload")
    t = (text or "").strip()
    logger.info(f"[revamp] step={step} text_len={len(t)} tier={user_tier}")

    # ---- UPLOAD ----
    if step == "upload":
        if not t:
            return ("📄 *Resume/CV Revamp*\n\n"
                    "I'll help improve your existing resume or CV with AI-powered enhancements.\n\n"
                    "Please paste your resume content here (or type the main sections).\n\n"
                    "_Tip: Include your contact info, experience, skills, and education._")

        # User has pasted content
        if len(t) < 100:
            return ("That seems quite short for a resume. Please paste more content including:\n"
                    "• Contact information\n"
                    "• Work experience\n"
                    "• Skills\n"
                    "• Education")

        # Store original content
        answers["original_content"] = t
        _advance(db, job, answers, "revamp_processing")

        return "✅ Got it! Analyzing your resume with AI... (This may take a few seconds)"

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
            target_role = answers.get("target_role", "Revamp")

            can_gen, reason = payments.can_generate(user, target_role)
            if not can_gen:
                if reason == "free_limit_reached" and answers.get("paid_generation"):
                    can_gen = True
                elif reason == "free_limit_reached":
                    _advance(db, job, answers, "payment_required")
                    return (f"🎯 *You've reached your free tier limit ({payments.FREE_TIER_LIMIT} documents)*\n\n"
                            f"Each additional document costs ₦{payments.PAID_GENERATION_PRICE:,}.\n\n"
                            "Reply *pay* to get your payment link, or */reset* to cancel.")
                elif reason.startswith("max_per_role"):
                    _, role_name = reason.split("|")
                    return (f"⚠️ *Maximum generations reached for '{role_name}'*\n\n"
                            "Please */reset* to try a different role.")

            # Track generation
            payments.update_generation_count(db, user, target_role)

            try:
                # Render revamped document
                logger.info(f"[revamp] Rendering revamped document for job.id={job.id}")
                doc_bytes = renderer.render_revamp(job)
                filename = f"revamp_{job.id[:8]}.docx"
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
        if t.lower() == "pay":
            user = db.query(User).filter(User.id == job.user_id).first()
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
            user = db.query(User).filter(User.id == job.user_id).first()
            payments.record_waived_payment(db, user.id, answers.get("target_role", "Revamp"))

            answers.pop("payment_reference", None)
            answers["paid_generation"] = True
            _advance(db, job, answers, "preview")
            return "✅ Payment waived! Reply *yes* to generate your improved document."

        return (f"🎯 *Payment Required*\n\nEach document costs ₦{payments.PAID_GENERATION_PRICE:,}.\n"
                "Reply *pay* to get your payment link, or */reset* to cancel.")


async def handle_cover(db: Session, job: Job, text: str, user_tier: str = "free") -> str:
    """
    Simple cover letter flow.
    Steps: basics -> role_company -> highlights -> preview -> finalize
    """
    answers = job.answers or {"_step": "basics"}
    step = FORCE_LOWER(answers.get("_step") or "basics")
    t = (text or "").strip()
    logger.info(f"[cover] step={step} text_len={len(t)} tier={user_tier}")

    # BASICS
    if step == "basics":
        if "," not in t:
            return resume_flow.QUESTIONS["basics"]

        answers["basics"] = resume_flow.parse_basics(t)
        _advance(db, job, answers, "role_company")
        return ("Great! Now tell me the role and company you're applying to.\n"
                "Format: Role, Company\n\nExample: Product Manager, Figma")

    # ROLE + COMPANY
    if step == "role_company":
        parts = [p.strip() for p in t.split(",")]
        if len(parts) < 2:
            return "Please send: Role, Company\n\nExample: Product Manager, Figma"

        answers["cover_role"] = parts[0]
        answers["cover_company"] = parts[1]
        answers["target_role"] = parts[0]

        _advance(db, job, answers, "highlights")
        return ("Share 2–3 bullet highlights to include (one per message).\n"
                "Example: Led redesign that improved activation by 22%\n"
                "Type *done* when finished.")

    # HIGHLIGHTS
    if step == "highlights":
        lt = t.lower()
        highlights = list(answers.get("cover_highlights", []))

        if lt in {"done", "skip"}:
            _advance(db, job, answers, "preview")
            preview_text = _format_cover_preview(answers)
            return f"{preview_text}\n\nLooks good? Reply *yes* to generate your cover letter, or */reset* to start over."

        if t:
            highlights.append(t)
            answers["cover_highlights"] = highlights
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()
            return f"Added. ({len(highlights)} so far) Send another or type *done*."

    # PREVIEW
    if step == "preview":
        if t.lower() in {"yes", "y", "confirm", "ok"}:
            user = db.query(User).filter(User.id == job.user_id).first()
            target_role = answers.get("cover_role", "Cover Letter")

            can_gen, reason = payments.can_generate(user, target_role)
            if not can_gen:
                if reason == "free_limit_reached" and answers.get("paid_generation"):
                    can_gen = True
                elif reason == "free_limit_reached":
                    _advance(db, job, answers, "payment_required")
                    return (f"🎯 *You've reached your free tier limit ({payments.FREE_TIER_LIMIT} documents)*\n\n"
                            f"Each additional document costs ₦{payments.PAID_GENERATION_PRICE:,}.\n\n"
                            "Reply *pay* to get your payment link, or */reset* to cancel.")
                elif reason.startswith("max_per_role"):
                    _, role_name = reason.split("|")
                    return (f"⚠️ *Maximum generations reached for '{role_name}'*\n\n"
                            "Please */reset* to try a different role.")

            payments.update_generation_count(db, user, target_role)

            try:
                logger.info(f"[cover] Rendering cover letter for job.id={job.id}")
                doc_bytes = renderer.render_cover_letter(job)
                filename = f"cover_{job.id[:8]}.docx"
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
        if t.lower() == "pay":
            user = db.query(User).filter(User.id == job.user_id).first()
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
            user = db.query(User).filter(User.id == job.user_id).first()
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
    """Get bot statistics for admin."""
    from sqlalchemy import func
    from datetime import datetime, timedelta
    import json
    
    # Total users
    total_users = db.query(User).count()
    
    # New users (last 7 days)
    seven_days_ago = datetime.now() - timedelta(days=7)
    new_users = db.query(User).filter(User.created_at >= seven_days_ago).count()
    
    # Active jobs
    active_jobs = db.query(Job).filter(Job.status.in_(["collecting", "preview_ready", "finalizing"])).count()
    
    # Completed jobs
    completed_jobs = db.query(Job).filter(Job.status == "completed").count()
    
    # Total messages
    total_messages = db.query(Message).count()
    
    # Documents by type
    resume_count = db.query(Job).filter(Job.type == "resume").count()
    cv_count = db.query(Job).filter(Job.type == "cv").count()
    revamp_count = db.query(Job).filter(Job.type == "revamp").count()
    
    # User tier breakdown
    free_users = db.query(User).filter(User.tier == "free").count()
    pro_users = db.query(User).filter(User.tier == "pro").count()
    
    stats_msg = f"""📊 *Career Buddy - Admin Stats*

*👥 Users*
• Total: {total_users}
• New (7 days): {new_users}
• Free tier: {free_users}
• Pro tier: {pro_users}

*📄 Documents*
• Active jobs: {active_jobs}
• Completed: {completed_jobs}
• Resumes: {resume_count}
• CVs: {cv_count}
• Revamps: {revamp_count}

*💬 Activity*
• Total messages: {total_messages}
• Avg per user: {total_messages / total_users if total_users > 0 else 0:.1f}

_Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC_"""
    
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
        
        # Generate filename
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sample_{doc_type}_{template_choice}_{timestamp}.docx"
        
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
        import json
        try:
            if user.generation_count:
                generation_counts = json.loads(user.generation_count) if isinstance(user.generation_count, str) else user.generation_count
            else:
                generation_counts = {}
        except Exception as e:
            logger.error(f"[handle_inbound] Error parsing generation_count: {e}")
            generation_counts = {}
        total_generated = sum(generation_counts.values())
        
        status_msg = f"""📊 *Your Account Status*

👤 User: {user.name or user.telegram_username or 'User'}
🎯 Plan: {'Free' if user.tier == 'free' else 'Premium'}
📄 Documents Created: {total_generated}

"""
        if user.tier == "free":
            remaining = max(0, 2 - total_generated)
            status_msg += f"""*Free Plan:*
✅ {remaining} free document{'s' if remaining != 1 else ''} remaining
💡 After that: ₦7,500 per document

"""
        else:
            status_msg += """*Premium Plan:*
✅ Enhanced AI features
✅ Priority support
💰 ₦7,500 per document

"""
        
        if generation_counts:
            status_msg += "*Generation History:*\n"
            for role, count in generation_counts.items():
                status_msg += f"• {role}: {count} document{'s' if count != 1 else ''}\n"
        
        status_msg += "\nReady to create? Type /start!"
        return status_msg

    # 1.8) PDF conversion command
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

    # Check if free user is trying to access cover letter
    if doc_type == "cover" and user.tier == "free":
        return ("💼 *Cover Letters are a Premium feature*\n\n"
                "Upgrade to Premium and unlock:\n"
                "✨ Professional cover letter generation\n"
                "✨ Enhanced AI with business impact analysis\n"
                "✨ Senior-level summaries\n"
                "✨ Priority support\n\n"
                "Ready to upgrade? Type *Premium* to get started!")

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