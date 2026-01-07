from __future__ import annotations
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import User, Job, Message
from app.flows import resume as resume_flow
from app.services.idempotency import seen_or_mark
from app.services import orchestrator, renderer, storage, ai, payments

WELCOME = "Hi! What would you like to create first?\nReply with *Resume*, *CV*, or *Cover Letter*."
GREETINGS = {"hi", "hello", "hey", "start", "menu", "/start"}
RESETS = {"reset", "/reset", "restart"}
HELP_COMMANDS = {"/help", "help"}
STATUS_COMMANDS = {"/status", "status"}
FORCE_LOWER = lambda s: (s or "").strip().lower()

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
        return resume_flow.QUESTIONS["experience"]

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
            return resume_flow.QUESTIONS["experience"]

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
            return resume_flow.QUESTIONS["experience"]

        _advance(db, job, answers, "education")
        return resume_flow.QUESTIONS["education"]

    # ---- EDUCATION ----
    if step == "education":
        if not t or t.lower() == "skip":
            _advance(db, job, answers, "extras")
            return resume_flow.QUESTIONS["extras"]

        edus = list(answers.get("education", []))
        edus.append({"details": t})
        answers["education"] = edus
        job.answers = answers
        flag_modified(job, "answers")
        db.commit()
        return "Added. Send another or *skip*."

    # ---- EXTRAS ----
    if step == "extras":
        lt = t.lower()
        if not t or lt in {"done", "skip"}:
            # Advance to AI skills generation
            _advance(db, job, answers, "skills")
            step = "skills"
            # Fall through to skills below
        else:
            projs = list(answers.get("projects", []))
            projs.append({"details": t})
            answers["projects"] = projs
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()
            return "Got it. Add more or type *done*."

    # ---- SKILLS (AI-GENERATED) ----
    if step == "skills":
        # Generate AI skill suggestions on first arrival
        if not answers.get("ai_suggested_skills"):
            logger.info("[handle_resume] Generating AI skill suggestions")
            try:
                target_role = answers.get("target_role", "")
                basics = answers.get("basics", {})
                experiences = answers.get("experiences", [])

                suggested_skills = ai.generate_skills(target_role, basics, experiences, tier=user_tier)
                answers["ai_suggested_skills"] = suggested_skills

                job.answers = answers
                flag_modified(job, "answers")
                db.commit()

                # Show skill options
                return resume_flow.format_skills_selection(suggested_skills)
            except Exception as e:
                logger.error(f"[handle_resume] AI skill generation failed: {e}")
                # Fallback to manual entry
                return ("Please list your skills (comma-separated).\n"
                        "Example: Python, Data Analysis, SQL, Communication")
        else:
            # User is selecting skills
            suggested = answers.get("ai_suggested_skills", [])
            selected_skills = resume_flow.parse_skill_selection(t, suggested)

            if not selected_skills:
                return ("Please select skills by number (e.g., 1,3,5) or enter your own skills.\n"
                        "Max 5 skills.")

            answers["skills"] = selected_skills[:5]  # Enforce max 5
            _advance(db, job, answers, "summary")

            # Generate AI summary immediately
            logger.info("[handle_resume] Generating AI summary after skill selection")
            try:
                ai_summary = ai.generate_summary(answers, tier=user_tier)
                answers["summary"] = ai_summary

                job.answers = answers
                flag_modified(job, "answers")
                db.commit()

                # Show generated summary for approval
                return (f"🤖 *Generated Summary:*\n\n{ai_summary}\n\n"
                        "Reply *yes* to use this, or paste your own summary to replace it.")
            except Exception as e:
                logger.error(f"[handle_resume] AI summary generation failed: {e}")
                return ("Please share a short professional summary (2-3 sentences), or type *skip*.")

    # ---- SUMMARY (AI-GENERATED) ----
    if step == "summary":
        # User is responding to the generated summary
        if t.lower() in {"yes", "y", "ok", "looks good", "good"}:
            # User approved the AI summary, move to preview
            _advance(db, job, answers, "preview")
            preview_text = _format_preview(answers)
            return f"{preview_text}\n\nLooks good? Reply *yes* to generate your document, or */reset* to start over."
        else:
            # User provided custom summary
            answers["summary"] = t
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()

            _advance(db, job, answers, "preview")
            preview_text = _format_preview(answers)
            return f"{preview_text}\n\nLooks good? Reply *yes* to generate your document, or */reset* to start over."

    # ---- PREVIEW ----
    if step == "preview":
        # If user just arrived at preview, show summary
        if not t or t.lower() in {"done", "skip"}:
            preview_text = _format_preview(answers)
            return f"{preview_text}\n\nLooks good? Reply *yes* to generate your document, or */reset* to start over."

        # User confirmed
        if t.lower() in {"yes", "y", "confirm", "ok", "okay"}:
            _advance(db, job, answers, "finalize")
            step = "finalize"
            # Fall through to finalization
        else:
            # User wants to make changes
            return ("To make changes, please type */reset* to start over.\n\n"
                    "Or reply *yes* to proceed with generating your document.")

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
                return (f"🎯 *You've reached your free tier limit ({payments.FREE_TIER_LIMIT} documents)*\n\n"
                        f"Each additional document costs ₦{payments.PAID_GENERATION_PRICE:,}.\n\n"
                        "Ready to generate your document? Reply *pay* to get your payment link, "
                        "or type */reset* to start over.")
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

    # 1.5) Help command
    if t_lower in HELP_COMMANDS:
        return HELP_MESSAGE

    # 1.6) Status command
    if t_lower in STATUS_COMMANDS:
        import json
        generation_counts = json.loads(user.generation_count) if user.generation_count else {}
        total_generated = sum(generation_counts.values())
        
        status_msg = f"""📊 *Your Account Status*

👤 *User:* {user.name or user.telegram_username or 'User'}
🎯 *Plan:* {'Free' if user.tier == 'free' else 'Premium'}
📄 *Documents Created:* {total_generated}

"""
        if user.tier == "free":
            remaining = max(0, 2 - total_generated)
            status_msg += f"""*🆓 Free Plan:*
✅ {remaining} free document{'s' if remaining != 1 else ''} remaining
💡 After that: ₦7,500 per document

"""
        else:
            status_msg += """*💎 Premium Plan:*
✅ Enhanced AI features
✅ Priority support
💰 ₦7,500 per document

"""
        
        if generation_counts:
            status_msg += "*📈 Generation History:*\n"
            for role, count in generation_counts.items():
                status_msg += f"• {role}: {count} document{'s' if count != 1 else ''}\n"
        
        status_msg += "\nReady to create? Type /start!"
        return status_msg

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