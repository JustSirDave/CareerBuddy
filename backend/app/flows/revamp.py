# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Xenaptis Technologies
"""
Revamp flow: upload → parse → AI enhance → render → deliver.
Owns all revamp-specific business logic; conversation_router and webhook delegate here.
"""
import asyncio
from pathlib import Path
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import User, Job
from app.services import renderer, storage, ai
from app.flows import resume as resume_flow
from app.services.telegram import reply_text


async def handle_revamp_step(db: Session, job: Job, text: str) -> str:
    """Step router for an active revamp job. Replaces handle_revamp() in conversation_router."""
    user = db.query(User).filter(User.id == job.user_id).first()
    answers = job.answers or {"_step": "upload"}
    step = (answers.get("_step") or "upload").strip().lower()
    t = (text or "").strip()
    logger.info(f"[revamp] step={step} text_len={len(t)}")

    # ---- UPLOAD ----
    if step == "upload":
        if not t or t.lower() in {"revamp", "revamp existing", "revamp existing (soon)"}:
            return (
                "📄 *Resume/CV Revamp*\n\n"
                "I'll help improve your existing resume or CV with AI-powered enhancements!\n\n"
                "*📤 Upload Your Resume:*\n"
                "✅ Supported format: .docx\n\n"
                "*How It Works:*\n"
                "1. Tap the 📎 attachment icon\n"
                "2. Select your resume file\n"
                "3. Send it to me\n"
                "4. I'll analyze and improve it with AI\n"
                "5. You'll get a professionally revamped version!\n\n"
                "_Maximum file size: 10MB_"
            )
        return (
            "📎 *Please upload your resume file*\n\n"
            "I need you to upload your existing resume as a file (not paste text).\n\n"
            "*Steps:*\n"
            "1. Tap the 📎 attachment button\n"
            "2. Choose your resume file (.docx format)\n"
            "3. Send it to me\n\n"
            "Or type */reset* to cancel."
        )

    # ---- REVAMP PROCESSING ----
    if step == "revamp_processing":
        original = answers.get("original_content", "")
        try:
            revamped_content = await ai.revamp_resume(original)
            answers["revamped_content"] = revamped_content
            answers["_step"] = "preview"
            job.answers = answers
            flag_modified(job, "answers")
            db.commit()
            preview = (
                f"🎯 *AI-Enhanced Resume*\n\n"
                f"{revamped_content[:500]}{'...' if len(revamped_content) > 500 else ''}\n\n"
                "---\n"
                "Reply *yes* to generate your improved document, or */reset* to start over."
            )
            return preview
        except Exception as e:
            logger.error(f"[revamp] AI revamp failed: {e}")
            return (
                "❌ Sorry, we couldn't process your resume. Please try again or contact support.\n\n"
                "Support: 07063011079"
            )

    # ---- PREVIEW ----
    if step == "preview":
        if t.lower() in {"yes", "y", "confirm", "ok"}:
            from app.services.usage import check_and_increment
            limit_msg = check_and_increment(user, db)
            if limit_msg:
                return limit_msg
            try:
                logger.info(f"[revamp] Rendering revamped document for job.id={job.id}")
                loop = asyncio.get_event_loop()
                doc_bytes = await loop.run_in_executor(None, renderer.render_revamp, job)
                from app.utils import generate_filename
                filename = generate_filename(job)
                job.draft_text = await storage.save_document(job.id, doc_bytes, filename)
                job.status = "preview_ready"
                answers["_step"] = "done"
                job.answers = answers
                flag_modified(job, "answers")
                db.commit()
                return f"__SEND_DOCUMENT__|{job.id}|{filename}"
            except Exception as e:
                logger.error(f"[revamp] Rendering failed: {e}")
                answers["_step"] = "done"
                job.answers = answers
                flag_modified(job, "answers")
                db.commit()
                return f"❌ Sorry, document generation failed: {str(e)}"

        return "Reply *yes* to generate your document, or */reset* to start over."

    return resume_flow.QUESTIONS.get(step, resume_flow.QUESTIONS["basics"])


async def process_revamp_upload(
    chat_id: int | str,
    file_path: Path,
    file_type: str,
    job: Job,
    db: Session,
    user: User,
) -> None:
    """Handle an uploaded file for an active revamp job. Replaces handle_revamp_upload() in webhook."""
    from app.services import document_parser

    await reply_text(
        chat_id,
        f"⏳ *Analyzing your resume...*\n\n"
        f"📄 Extracting content from {file_type.upper()} file\n"
        f"🤖 This may take 30-60 seconds\n\n"
        f"_Please wait..._",
    )

    try:
        parsed_data = document_parser.parse_document(file_path, file_type)
        logger.info(
            f"[revamp] Parsed {file_path.name}: "
            f"{parsed_data['word_count']} words, {len(parsed_data['sections'])} sections"
        )

        answers = job.answers if isinstance(job.answers, dict) else {}
        answers["original_content"] = parsed_data["content"]
        answers["file_type"] = file_type
        answers["file_name"] = parsed_data["file_name"]
        answers["word_count"] = parsed_data["word_count"]
        answers["sections_detected"] = list(parsed_data["sections"].keys())
        answers["_step"] = "revamp_processing"
        job.answers = answers
        flag_modified(job, "answers")
        db.commit()

        logger.info(f"[revamp] Stored content in job.id={job.id}, advancing to processing")
        reply = await handle_revamp_step(db, job, "")
        if reply:
            await reply_text(chat_id, reply)

    except ValueError as ve:
        logger.warning(f"[revamp] Validation error: {ve}")
        await reply_text(chat_id, f"❌ *Document Error*\n\n{str(ve)}")
    except Exception as e:
        logger.error(f"[revamp] Upload processing error: {e}")
        await reply_text(
            chat_id,
            f"❌ *Processing Error*\n\n"
            f"Sorry, we couldn't process your resume.\n\n"
            f"Please try:\n"
            f"• Uploading a different file\n"
            f"• Saving your resume in .docx format\n"
            f"• Typing /reset to start over\n\n"
            f"_Error: {str(e)}_",
        )
