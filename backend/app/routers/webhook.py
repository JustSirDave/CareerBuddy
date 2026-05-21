# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Xenaptis Technologies
"""
CareerBuddy - Webhook Router
Handles Telegram webhooks and document delivery.
"""
import asyncio
from pathlib import Path
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.services.idempotency import seen_or_mark
from app.db import get_db
from app.models.user import User
from app.models.job import Job
from app.services.telegram import reply_text, send_choice_menu, send_welcome_menu, send_document, send_document_type_menu, send_typing_action, send_template_selection, send_onboarding_continue_menu, send_feedback_prompt, forward_bad_feedback, send_confirm_menu, send_revision_confirm_menu
from app.services.conversation_router import handle_inbound

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def verify_telegram_webhook_secret(request: Request) -> None:
    """SEC-001: reject requests when a secret is configured but header is missing or wrong."""
    secret = settings.telegram_webhook_secret
    if secret:
        token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if token != secret:
            raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/telegram", dependencies=[Depends(verify_telegram_webhook_secret)])
async def telegram_webhook(request: Request, db=Depends(get_db)):
    """
    Telegram Bot webhook endpoint.
    Always returns 200 to stop Telegram retries; logs errors internally.
    """
    try:
        payload = await request.json()
        logger.debug(f"[telegram_webhook] Received update: {payload}")
    except Exception as e:
        logger.error(f"[telegram_webhook] Failed to parse JSON: {e}")
        return JSONResponse(status_code=200, content={"ok": True})

    try:
        await _process_telegram_update(payload, db)
    except Exception as e:
        logger.exception(f"[telegram_webhook] Unhandled error processing update {payload.get('update_id')}: {e}")
    return JSONResponse(status_code=200, content={"ok": True})


async def _process_telegram_update(payload: dict, db):
    """Process Telegram update. Exceptions are caught by caller."""
    if "callback_query" in payload:
        await handle_callback_query(payload["callback_query"], db)
        return

    # Check for document uploads FIRST (before text extraction)
    message = payload.get("message") or payload.get("edited_message") or {}
    document = message.get("document")
    supported_mimes = [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "application/msword",  # .doc (old Word)
        "application/pdf"  # .pdf
    ]
    if document and document.get("mime_type") in supported_mimes:
        # Extract chat info for document upload
        chat = message.get("chat", {})
        if chat.get("type") != "private":
            logger.debug(f"[telegram_webhook] Ignoring document from non-private chat: {chat.get('type')}")
            return
        chat_id = chat.get("id")
        from_user = message.get("from", {})
        username = from_user.get("username")
        msg_id = message.get("message_id")
        
        if msg_id and await seen_or_mark(str(msg_id)):
            logger.warning(f"[telegram_webhook] Duplicate document upload msg_id={msg_id}, skipping")
            return
        if chat_id:
            await handle_document_upload(chat_id, document, db, username)
        return

    # Extract message from Telegram update
    chat_id, text, msg_id, username, first_name = extract_telegram_message(payload)
    if not chat_id:
        logger.debug("[telegram_webhook] No valid message found, ignoring")
        return

    if msg_id and await seen_or_mark(str(msg_id)):
        logger.warning(f"[telegram_webhook] Duplicate msg_id={msg_id} from chat_id={chat_id}, skipping")
        return

    await send_typing_action(chat_id)
    reply = await handle_inbound(db, str(chat_id), text or "", msg_id=str(msg_id), telegram_username=username, first_name=first_name)

    if reply == "__SHOW_MENU__":
        await send_choice_menu(chat_id)
        return
    if reply and reply.startswith("__SEND_WELCOME__|"):
        first_name_part = reply.split("|", 1)[1]
        await send_welcome_menu(chat_id, first_name_part)
        return
    if reply and reply.startswith("__SHOW_ONBOARDING_CONTINUE_MENU__|"):
        parts = reply.split("|", 1)
        if len(parts) == 2:
            await send_onboarding_continue_menu(chat_id, parts[1])
        return
    if reply and reply.startswith("__SHOW_DOCUMENT_MENU__|"):
        parts = reply.split("|", 2)
        if len(parts) >= 2:
            tier = parts[1]
            if len(parts) == 3:
                await reply_text(chat_id, parts[2])
            await send_document_type_menu(chat_id, tier)
        return
    if reply and reply.startswith("__SEND_DOCUMENT__|"):
        parts = reply.split("|")
        if len(parts) == 3:
            _, job_id, filename = parts
            await send_document_to_user(chat_id, job_id, filename, db)
        return
    if reply and reply.startswith("__SEND_PDF__|"):
        parts = reply.split("|")
        if len(parts) >= 2:
            user_id = parts[1]
            await send_pdf_to_user(chat_id, user_id, db)
        return
    if reply and reply.startswith("__CONFIRM_REVISION__|"):
        question = reply[len("__CONFIRM_REVISION__|"):]
        await send_revision_confirm_menu(chat_id, question)
        return
    if reply and reply.startswith("__CONFIRM__|"):
        question = reply[len("__CONFIRM__|"):]
        await send_confirm_menu(chat_id, question)
        return
    if reply:
        await reply_text(chat_id, reply)


async def handle_document_upload(chat_id: int | str, document: dict, db: Session, username: str | None = None):
    """
    Handle uploaded document from user.
    Routes to either:
    - Revamp processing (if user has active revamp job)
    - PDF conversion storage (for edited documents)

    Args:
        chat_id: Telegram chat ID
        document: Telegram document object
        db: Database session
        username: Telegram username
    """
    try:
        import httpx
        from pathlib import Path
        from app.config import settings
        from app.models import User, Job
        from app.services import document_parser

        # Get user
        user = db.query(User).filter(User.telegram_user_id == str(chat_id)).first()
        if not user:
            await reply_text(chat_id, "❌ User not found. Please type /start to begin.")
            return

        # Get file info
        file_id = document.get("file_id")
        file_name = document.get("file_name", "document")
        mime_type = document.get("mime_type", "")
        file_size = document.get("file_size", 0)

        logger.info(f"[handle_document_upload] User {user.id} uploaded: {file_name} ({mime_type}, {file_size} bytes)")

        # Check if user has an active revamp job
        revamp_job = db.query(Job).filter(
            Job.user_id == user.id,
            Job.type == "revamp",
            Job.status == "collecting"
        ).order_by(Job.created_at.desc()).first()

        # Validate file format
        is_valid, file_type, error_msg = document_parser.validate_file_format(
            file_name, mime_type, "pro"
        )

        if not is_valid:
            await reply_text(chat_id, error_msg)
            return

        # Check file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB in bytes
        if file_size > max_size:
            await reply_text(chat_id, 
                           f"❌ *File too large!*\n\n"
                           f"File size: {file_size / (1024*1024):.1f}MB\n"
                           f"Maximum: 10MB\n\n"
                           f"Please upload a smaller file.")
            return

        # Download file from Telegram
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get file path
            file_info_resp = await client.get(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/getFile",
                params={"file_id": file_id}
            )
            file_info = file_info_resp.json()

            if not file_info.get("ok"):
                await reply_text(chat_id, "❌ Failed to download your document. Please try again.")
                return

            file_path = file_info["result"]["file_path"]

            # Download the file
            file_resp = await client.get(
                f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
            )
            file_bytes = file_resp.content

        # Save the uploaded document
        upload_dir = Path("output") / "uploads" / str(user.id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        upload_path = upload_dir / file_name
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, upload_path.write_bytes, file_bytes)

        logger.info(f"[handle_document_upload] Saved: {upload_path}")

        # Route based on context
        if revamp_job:
            # REVAMP FLOW: Process the uploaded resume
            await handle_revamp_upload(chat_id, upload_path, file_type, revamp_job, db, user)
        else:
            # PDF CONVERSION FLOW: Store for later conversion
            await reply_text(chat_id, 
                           f"✅ *Document Received!*\n\n"
                           f"📄 File: {file_name}\n\n"
                           f"Ready to convert to PDF?\n"
                           f"Type */pdf* or *convert to pdf* to get your final PDF!")

    except Exception as e:
        logger.error(f"[handle_document_upload] Error: {e}")
        await reply_text(chat_id, "❌ Sorry, there was an error processing your document. Please try again.")


async def handle_revamp_upload(chat_id: int | str, file_path: Path, file_type: str, job: Job, db: Session, user: User):
    """Delegate to flows/revamp.py."""
    from app.flows import revamp as revamp_flow
    await revamp_flow.process_revamp_upload(chat_id, file_path, file_type, job, db, user)


async def send_document_to_user(chat_id: int | str, job_id: str, filename: str, db=None):
    """
    Send the generated document to the user via Telegram.
    Passes the public Cloudinary URL directly to Telegram — no local download.
    """
    try:
        from app.services.telegram import send_document_url

        job = db.query(Job).filter(Job.id == job_id).first() if db else None
        doc_url = (
            job.draft_text
            if job and job.draft_text and job.draft_text.startswith("http")
            else None
        )

        if not doc_url:
            logger.error(f"[telegram_webhook] No Cloudinary URL for job {job_id}")
            await reply_text(chat_id, "❌ Sorry, your document could not be found. Please try again.")
            return

        filename = doc_url.split("/")[-1] or filename
        logger.info(f"[telegram_webhook] Sending document by URL for job {job_id}: {filename}")
        send_resp = await send_document_url(chat_id, doc_url, filename, caption="📄 *Your Document is Ready!*")

        if send_resp and not send_resp.get("error"):
            logger.info(f"[telegram_webhook] Document sent to {chat_id}: {filename}")
            if db and job:
                from datetime import datetime
                job.status = "done"
                job.completed_at = datetime.utcnow()
                db.commit()
            success_msg = (
                "✅ *Your document is ready!*\n\n"
                "📄 Your PDF is ready to send to recruiters and upload to job boards.\n\n"
                "🔄 Type /reset to create another document.\n\n"
                "Good luck with your job search! 🚀"
            )
            await reply_text(chat_id, success_msg)
            await send_feedback_prompt(chat_id)
            return

        logger.error(f"[telegram_webhook] send_document_url failed for job {job_id}: {send_resp}")
        await reply_text(chat_id, "❌ Sorry, something went wrong delivering your document. Please try again.")

    except Exception as e:
        logger.error(f"[telegram_webhook] Error sending document: {e}")
        await reply_text(chat_id, "❌ Sorry, something went wrong. Please try again.")


async def send_pdf_to_user(chat_id: int | str, user_id: str, db: Session):
    """
    Generate PDF for the user. Premium feature only.
    - If user uploaded edited DOCX: Convert it using LibreOffice
    - If no upload: Generate PDF directly from data (bypasses LibreOffice issues)
    
    Args:
        chat_id: Telegram chat ID
        user_id: User ID (from telegram_user_id)
        db: Database session
    """
    try:
        from pathlib import Path
        from app.services import storage
        from app.services import pdf_renderer
        from app.models import User, Job
        
        user = db.query(User).filter(User.telegram_user_id == str(user_id)).first()
        if not user:
            await reply_text(chat_id, "❌ User not found. Please start with /start.")
            return

        # Find the latest completed job
        latest_job = db.query(Job).filter(
            Job.user_id == user.id,
            Job.status.in_(["done", "completed", "preview_ready"]),
        ).order_by(Job.created_at.desc()).first()
        
        if not latest_job:
            await reply_text(chat_id, "❌ No document found to convert. Please generate a document first.")
            return

        # Check for uploaded (edited) documents
        latest_uploaded_docx = None
        upload_dir = Path("output") / "uploads" / str(user.id)
        if upload_dir.exists():
            docx_files = sorted(upload_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
            if docx_files:
                latest_uploaded_docx = docx_files[0]
                logger.info(f"[send_pdf] Found latest uploaded docx: {latest_uploaded_docx}")

        await send_typing_action(chat_id)
        await reply_text(chat_id, "⚙️ *Generating PDF...*\n\nThis may take a moment.")

        pdf_bytes = None
        pdf_filename = None

        # If user uploaded edited DOCX, convert it with LibreOffice
        if latest_uploaded_docx:
            logger.info(f"[send_pdf] User uploaded edited DOCX, using LibreOffice conversion")
            pdf_bytes, pdf_filename = await storage.convert_docx_to_pdf(latest_uploaded_docx)
        else:
            # No upload - generate PDF directly from data (all templates use ReportLab now)
            logger.info(f"[send_pdf] No edited DOCX, generating PDF directly from data")
            template = latest_job.answers.get('template', 'template_1')
            
            # All templates now have direct PDF generation
            try:
                pdf_bytes = await asyncio.get_event_loop().run_in_executor(
                    None, pdf_renderer.render_pdf_from_data, latest_job.answers, template
                )
                # Generate filename
                doc_type = latest_job.type or 'document'
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                pdf_filename = f"{doc_type}_{template}_{timestamp}.pdf"
                logger.info(f"[send_pdf] Successfully generated PDF using ReportLab for {template}")
            except Exception as e:
                logger.error(f"[send_pdf] Direct PDF generation failed: {e}")
                # Fallback: fetch DOCX from Cloudinary and convert with LibreOffice
                if latest_job.draft_text and latest_job.draft_text.startswith("http"):
                    try:
                        import tempfile as _tempfile
                        docx_bytes = await storage.fetch_document_bytes(latest_job.draft_text)
                        with _tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as _tmp:
                            _tmp.write(docx_bytes)
                            _tmp_path = Path(_tmp.name)
                        logger.info(f"[send_pdf] Falling back to LibreOffice conversion")
                        pdf_bytes, pdf_filename = await storage.convert_docx_to_pdf(_tmp_path)
                        _tmp_path.unlink(missing_ok=True)
                    except Exception as _fe:
                        logger.error(f"[send_pdf] LibreOffice fallback failed: {_fe}")

        if not pdf_bytes:
            await reply_text(chat_id, "❌ Sorry, I couldn't convert your document to PDF. This feature requires LibreOffice to be installed on the server. Please try converting it manually or contact support.")
            return
        
        # Send PDF
        send_resp = await send_document(chat_id, pdf_bytes, pdf_filename, caption="📄 *Your Final PDF is Ready!*")
        
        if send_resp and not send_resp.get("error"):
            logger.info(f"[send_pdf] PDF sent to {chat_id}: {pdf_filename}")
            success_msg = """✅ *PDF Conversion Complete!*

Your professional document is now in PDF format - ready to use!

*📋 What's Next?*
• Download and save your PDF
• Print for physical copies
• Email to recruiters and employers
• Upload to job boards

*🔄 Need Another Document?*
Type /reset to create a new one
Type /status to check your plan

Good luck with your applications! 🚀"""
            await reply_text(chat_id, success_msg)
        else:
            logger.error(f"[send_pdf] Failed to send PDF: {send_resp}")
            await reply_text(chat_id, "❌ Sorry, there was an error sending your PDF. Please try again.")
            
    except Exception as e:
        logger.error(f"[send_pdf] Error: {e}")
        await reply_text(chat_id, "❌ Sorry, there was an error processing your PDF. Please try again.")


async def handle_callback_query(callback_query: dict, db):
    """
    Handle inline keyboard button clicks (callback queries).

    Args:
        callback_query: Callback query data from Telegram
        db: Database session

    Returns:
        Response dict
    """
    try:
        callback_id = callback_query.get("id")
        data = callback_query.get("data")
        message = callback_query.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        from_user = callback_query.get("from", {})
        username = from_user.get("username")

        logger.info(f"[callback_query] chat_id={chat_id}, data={data}")

        # Answer callback query to stop loading indicator
        from app.services import telegram
        answer_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/answerCallbackQuery"
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(answer_url, json={"callback_query_id": callback_id})

        # Handle different callback actions
        if data == "plan_free":
            # User clicked "Get Started" (or tapped a doc-type shortcut)
            reply = await handle_inbound(db, str(chat_id), "free", telegram_username=username)
            if reply and reply.startswith("__SHOW_DOCUMENT_MENU__|"):
                parts = reply.split("|")
                if len(parts) >= 2:
                    tier = parts[1]
                    if len(parts) == 3:
                        await reply_text(chat_id, parts[2])
                    await send_document_type_menu(chat_id, "free")
            elif reply and reply.startswith("__"):
                await reply_text(
                    chat_id,
                    "⏳ Still working on that... or something may have gone wrong.\n\n"
                    "Type /reset to start fresh or /help to see options.",
                )
            elif reply:
                await reply_text(chat_id, reply)

        elif data == "plan_premium":
            # Legacy callback from old "Start with Premium Plan" button — treat same as get-started
            await send_document_type_menu(chat_id, "free")

        elif data == "onboarding_continue":
            first_name = (from_user.get("first_name") or "").strip() or "there"
            reply = await handle_inbound(db, str(chat_id), "continue", telegram_username=username, first_name=first_name)
            if reply and reply.startswith("__"):
                await reply_text(
                    chat_id,
                    "⏳ Still working on that... or something may have gone wrong.\n\n"
                    "Type /reset to start fresh or /help to see options.",
                )
            elif reply:
                await reply_text(chat_id, reply)

        elif data == "onboarding_start_fresh":
            user = db.query(User).filter(User.telegram_user_id == str(chat_id)).first()
            if user:
                j = db.query(Job).filter(Job.user_id == user.id, Job.status == "collecting").order_by(Job.created_at.desc()).first()
                if j:
                    j.status = "closed"
                    db.commit()
            await send_document_type_menu(chat_id, "free")

        elif data == "learn_more":
            info_msg = (
                "📚 *About CareerBuddy*\n\n"
                "I'm a free, open-source AI assistant that helps you create "
                "professional career documents through a simple conversation.\n\n"
                "*🎯 What I create:*\n"
                "• Professional Resumes (1-2 pages)\n"
                "• Detailed CVs\n"
                "• Professional Cover Letters\n"
                "• Revamped/improved existing documents\n\n"
                "*✨ Features:*\n"
                "• AI-enhanced content\n"
                "• ATS-friendly formatting\n"
                "• Professional summaries\n"
                "• Smart skill suggestions\n"
                "• Instant delivery\n\n"
                "Everything is completely free. Ready to create? Type /start!"
            )
            await reply_text(chat_id, info_msg)

        elif data.startswith("doc_"):
            # Document type selected
            doc_type = data.replace("doc_", "")
            reply = await handle_inbound(db, str(chat_id), doc_type, telegram_username=username)
            if reply and reply.startswith("__"):
                await reply_text(
                    chat_id,
                    "⏳ Still working on that... or something may have gone wrong.\n\n"
                    "Type /reset to start fresh or /help to see options.",
                )
            elif reply:
                await reply_text(chat_id, reply)

        elif data.startswith("template_"):
            # Template selected
            template_num = data.replace("template_", "")
            logger.info(f"[callback_query] User {chat_id} selected {data}")

            # Update job with template choice
            job = db.query(Job).filter(
                Job.user_id.in_(
                    db.query(User.id).filter(User.telegram_user_id == str(chat_id))
                ),
                Job.status.in_(["collecting", "preview_ready"])
            ).order_by(Job.created_at.desc()).first()

            if job:
                answers = job.answers if isinstance(job.answers, dict) else {}
                answers["template"] = data
                job.answers = answers
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(job, "answers")
                db.commit()

                # Proceed to finalization
                reply = await handle_inbound(db, str(chat_id), "yes", telegram_username=username)
                if reply and reply.startswith("__SEND_DOCUMENT__|"):
                    parts = reply.split("|")
                    if len(parts) == 3:
                        await send_document_to_user(chat_id, parts[1], parts[2], db)
                elif reply and reply.startswith("__"):
                    await reply_text(
                        chat_id,
                        "⏳ Still working on that... or something may have gone wrong.\n\n"
                        "Type /reset to start fresh or /help to see options.",
                    )
                elif reply:
                    await reply_text(chat_id, reply)
            else:
                await reply_text(chat_id, "❌ Session expired. Please type /reset to start over.")

        elif data == "feedback_good":
            logger.info(f"[feedback] feedback_good: chat_id={chat_id}")
            user = db.query(User).filter(User.telegram_user_id == str(chat_id)).first()
            if not user:
                logger.warning(f"[feedback] feedback_good: user not found for chat_id={chat_id}")
            if user:
                recent_done = (
                    db.query(Job)
                    .filter(Job.user_id == user.id, Job.status == "done")
                    .order_by(Job.created_at.desc())
                    .first()
                )
                from app.models.feedback import Feedback
                fb = Feedback(
                    user_id=user.id,
                    job_id=recent_done.id if recent_done else None,
                    rating="good",
                )
                db.add(fb)
                db.commit()
            await reply_text(
                chat_id,
                "🎉 So glad it helped! Good luck with your job search! 🚀",
            )

        elif data == "feedback_bad":
            logger.info(f"[feedback] feedback_bad: chat_id={chat_id}")
            user = db.query(User).filter(User.telegram_user_id == str(chat_id)).first()
            if not user:
                logger.warning(f"[feedback] feedback_bad: user not found for chat_id={chat_id}")
            if user:
                recent_done = (
                    db.query(Job)
                    .filter(Job.user_id == user.id, Job.status == "done")
                    .order_by(Job.created_at.desc())
                    .first()
                )
                if recent_done:
                    from sqlalchemy.orm.attributes import flag_modified
                    answers = recent_done.answers if isinstance(recent_done.answers, dict) else {}
                    answers["_awaiting_feedback"] = True
                    recent_done.answers = answers
                    flag_modified(recent_done, "answers")
                    db.commit()
            await reply_text(chat_id, "😕 Sorry to hear that! What went wrong? Your feedback helps us improve.\n\n_Just type your message and send it._")

        elif data == "feedback_skip":
            pass  # end silently — callback query already answered above

        elif data == "cancel":
            await reply_text(chat_id, "❌ *Cancelled*\n\nNo problem! Type /start when you're ready to create a document.")

        elif data in ("confirm_yes", "confirm_no", "confirm_back"):
            text_map = {"confirm_yes": "yes", "confirm_no": "no", "confirm_back": "back"}

            if data == "confirm_yes":
                user = db.query(User).filter(User.telegram_user_id == str(chat_id)).first()
                if user:
                    active_collecting = (
                        db.query(Job)
                        .filter(Job.user_id == user.id, Job.status == "collecting")
                        .first()
                    )
                    failed_job = (
                        None
                        if active_collecting
                        else (
                            db.query(Job)
                            .filter(
                                Job.user_id == user.id,
                                Job.status.in_(["render_failed", "failed", "preview_ready", "error"]),
                            )
                            .order_by(Job.updated_at.desc())
                            .first()
                        )
                    )
                    logger.info(
                        f"[confirm_yes] active_collecting={active_collecting.id if active_collecting else None} "
                        f"stuck job={failed_job.id if failed_job else None} "
                        f"status={failed_job.status if failed_job else None}"
                    )
                    if failed_job:
                        from sqlalchemy.orm.attributes import flag_modified
                        from app.services.conversation_router import handle_resume, handle_cover

                        # PDF already generated but delivery failed — re-deliver without re-generating
                        if (
                            failed_job.status == "preview_ready"
                            and failed_job.draft_text
                            and failed_job.draft_text.startswith("http")
                        ):
                            await send_typing_action(chat_id)
                            await reply_text(chat_id, "🔄 Sending your document, please wait...")
                            filename = failed_job.draft_text.split("/")[-1]
                            await send_document_to_user(chat_id, str(failed_job.id), filename, db)
                            return {"ok": True}

                        # PDF not generated — re-trigger generation
                        answers = failed_job.answers if isinstance(failed_job.answers, dict) else {}
                        current_step = answers.get("_step")
                        finalize_step = "finalize" if failed_job.type in {"resume", "cv"} else "preview"
                        logger.info(
                            f"[retry] job_id={failed_job.id} type={failed_job.type!r} "
                            f"current_step={current_step!r} -> setting to {finalize_step!r}"
                        )
                        answers["_step"] = finalize_step
                        failed_job.answers = answers
                        failed_job.status = "collecting"
                        flag_modified(failed_job, "answers")
                        db.commit()
                        db.refresh(failed_job)
                        logger.info(
                            f"[retry] job_id={failed_job.id} step after reset: "
                            f"{failed_job.answers.get('_step')!r}"
                        )
                        await send_typing_action(chat_id)
                        await reply_text(chat_id, "🔄 Regenerating your document, please wait...")
                        if failed_job.type in {"resume", "cv"}:
                            gen_reply = await handle_resume(db, failed_job, "yes")
                        elif failed_job.type == "cover":
                            gen_reply = await handle_cover(db, failed_job, "yes")
                        else:
                            gen_reply = ""
                        db.refresh(failed_job)
                        if gen_reply and gen_reply.startswith("__SEND_DOCUMENT__|"):
                            parts = gen_reply.split("|")
                            if len(parts) == 3:
                                await send_document_to_user(chat_id, parts[1], parts[2], db)
                        elif not gen_reply or gen_reply.startswith("__") or failed_job.status == "render_failed":
                            logger.error(f"[callback_query] Repeated render_failed for chat_id={chat_id} job_id={failed_job.id}")
                            await reply_text(
                                chat_id,
                                "❌ Document generation failed again.\n\n"
                                "This is likely a temporary issue. "
                                "Please type /reset and try again in a moment.\n\n"
                                "If this keeps happening, the team has been notified.",
                            )
                        else:
                            await reply_text(chat_id, gen_reply)
                        return {"ok": True}

            reply = await handle_inbound(db, str(chat_id), text_map[data], telegram_username=username)
            if reply == "__SHOW_MENU__":
                await send_choice_menu(chat_id)
            elif reply and reply.startswith("__CONFIRM_REVISION__|"):
                await send_revision_confirm_menu(chat_id, reply[len("__CONFIRM_REVISION__|"):])
            elif reply and reply.startswith("__CONFIRM__|"):
                await send_confirm_menu(chat_id, reply[len("__CONFIRM__|"):])
            elif reply and reply.startswith("__SEND_DOCUMENT__|"):
                parts = reply.split("|")
                if len(parts) == 3:
                    await send_document_to_user(chat_id, parts[1], parts[2], db)
            elif reply and reply.startswith("__SHOW_DOCUMENT_MENU__|"):
                parts = reply.split("|", 2)
                if len(parts) >= 2:
                    if len(parts) == 3:
                        await reply_text(chat_id, parts[2])
                    await send_document_type_menu(chat_id, parts[1])
            elif reply and reply.startswith("__"):
                await reply_text(
                    chat_id,
                    "⏳ Still working on that... or something may have gone wrong.\n\n"
                    "Type /reset to start fresh or /help to see options.",
                )
            elif reply:
                await reply_text(chat_id, reply)

        return {"ok": True}

    except Exception as e:
        logger.error(f"[callback_query] Error handling callback: {e}")
        return {"ok": False, "error": str(e)}


def extract_telegram_message(payload: dict) -> tuple[int | None, str | None, int | None, str | None, str]:
    """
    Extract message data from Telegram webhook payload.

    Telegram webhook format:
    {
        "update_id": 123456789,
        "message": {
            "message_id": 123,
            "from": {
                "id": 987654321,
                "is_bot": false,
                "first_name": "John",
                "username": "john_doe"
            },
            "chat": {
                "id": 987654321,
                "first_name": "John",
                "username": "john_doe",
                "type": "private"
            },
            "date": 1234567890,
            "text": "Hello bot"
        }
    }

    Args:
        payload: Telegram webhook payload

    Returns:
        Tuple of (chat_id, text, msg_id, username, first_name)
    """
    try:
        # Check for message or edited_message (Telegram sends one or the other)
        message = payload.get("message") or payload.get("edited_message")

        if not message:
            logger.debug(f"[telegram_webhook] Non-message update type, ignoring")
            return None, None, None, None, "there"

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if not chat_id:
            logger.debug("[telegram_webhook] No chat_id found")
            return None, None, None, None, "there"
        if chat.get("type") != "private":
            logger.debug(f"[telegram_webhook] Ignoring non-private chat: {chat.get('type')}")
            return None, None, None, None, "there"

        msg_id = message.get("message_id")
        from_user = message.get("from", {})
        username = from_user.get("username")
        first_name = (from_user.get("first_name") or "").strip() or "there"

        text = message.get("text")
        if text and text.startswith("/"):
            pass
        if not text:
            logger.debug("[telegram_webhook] Message without text, ignoring")
            return None, None, None, None, "there"

        return chat_id, text, msg_id, username, first_name

    except Exception as e:
        logger.error(f"[telegram_webhook] Failed to extract message from Telegram payload: {e}")
        logger.error(f"[telegram_webhook] Payload was: {payload}")
        return None, None, None, None, "there"


