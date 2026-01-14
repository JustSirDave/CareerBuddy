"""
CareerBuddy - Webhook Router
Handles Telegram and Paystack webhooks
Author: Sir Dave
"""
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Depends
from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.services.idempotency import seen_or_mark
from app.db import get_db
from app.models.user import User
from app.models.job import Job
from app.services.telegram import reply_text, send_choice_menu, send_document, send_document_type_menu, send_typing_action, send_payment_request, send_template_selection
from app.services.router import handle_inbound

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/telegram")
async def telegram_webhook(request: Request, db=Depends(get_db)):
    """
    Telegram Bot webhook endpoint.
    Receives updates from Telegram and processes them.
    """
    try:
        payload = await request.json()
        logger.debug(f"[telegram_webhook] Received update: {payload}")
    except Exception as e:
        logger.error(f"[telegram_webhook] Failed to parse JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Handle callback queries (inline keyboard buttons)
    if "callback_query" in payload:
        return await handle_callback_query(payload["callback_query"], db)

    # Check for document uploads FIRST (before text extraction)
    message = payload.get("message", {})
    document = message.get("document")
    supported_mimes = [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "application/msword",  # .doc (old Word)
        "application/pdf"  # .pdf
    ]
    if document and document.get("mime_type") in supported_mimes:
        # Extract chat info for document upload
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        from_user = message.get("from", {})
        username = from_user.get("username")
        msg_id = message.get("message_id")
        
        # Deduplication for document uploads
        if msg_id and seen_or_mark(str(msg_id)):
            logger.warning(f"[telegram_webhook] Duplicate document upload msg_id={msg_id}, skipping")
            return {"ok": True}
        
        if chat_id:
            # User uploaded a document - route to appropriate handler
            await handle_document_upload(chat_id, document, db, username)
            return {"ok": True}

    # Extract message from Telegram update
    chat_id, text, msg_id, username = extract_telegram_message(payload)
    if not chat_id:
        logger.debug("[telegram_webhook] No valid message found, ignoring")
        return {"ok": True}

    # EARLY DEDUPLICATION: Check BEFORE calling handle_inbound
    if msg_id and seen_or_mark(str(msg_id)):
        logger.warning(f"[telegram_webhook] Duplicate msg_id={msg_id} from chat_id={chat_id}, skipping")
        return {"ok": True}

    # Show typing indicator while processing
    await send_typing_action(chat_id)

    # Process the message (using str(chat_id) as user identifier)
    reply = await handle_inbound(db, str(chat_id), text or "", msg_id=str(msg_id), telegram_username=username)

    if reply == "__SHOW_MENU__":
        await send_choice_menu(chat_id)
        return {"ok": True}

    # Check if document type menu should be shown (with confirmation message)
    if reply and reply.startswith("__SHOW_DOCUMENT_MENU__|"):
        parts = reply.split("|")
        if len(parts) >= 2:
            tier = parts[1]
            # If there's a confirmation message, send it first
            if len(parts) == 3:
                confirmation_msg = parts[2]
                await reply_text(chat_id, confirmation_msg)
            # Then show document type menu
            await send_document_type_menu(chat_id, tier)
        return {"ok": True}

    # Check if document should be sent
    if reply and reply.startswith("__SEND_DOCUMENT__|"):
        parts = reply.split("|")
        if len(parts) == 3:
            _, job_id, filename = parts
            await send_document_to_user(chat_id, job_id, filename)
        return {"ok": True}

    # Check if PDF should be sent
    if reply and reply.startswith("__SEND_PDF__|"):
        parts = reply.split("|")
        if len(parts) >= 2:
            user_id = parts[1]
            await send_pdf_to_user(chat_id, user_id, db)
        return {"ok": True}

    # Check if template selection menu should be shown
    if reply == "__SHOW_TEMPLATE_MENU__":
        from app.models import User
        user = db.query(User).filter(User.telegram_user_id == str(chat_id)).first()
        if user:
            await send_template_selection(chat_id, user.tier)
        return {"ok": True}

    # Check if payment is required
    if reply and reply.startswith("__PAYMENT_REQUIRED__|"):
        parts = reply.split("|")
        if len(parts) == 3:
            _, role, amount_str = parts
            from app.services import payments
            from app.models import User

            # Get user
            user = db.query(User).filter(User.telegram_user_id == str(chat_id)).first()
            if user:
                # Create payment link
                payment_result = await payments.create_payment_link(user, role, int(amount_str))

                if payment_result.get("authorization_url"):
                    await send_payment_request(chat_id, payment_result["authorization_url"], int(amount_str))
                else:
                    await reply_text(chat_id, "❌ *Payment Error*\n\nSorry, we couldn't generate your payment link. Please contact support or try again later.")
        return {"ok": True}

    if reply:
        await reply_text(chat_id, reply)
    return {"ok": True}


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
            file_name, mime_type, user.tier
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
        upload_path.write_bytes(file_bytes)

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
    """
    Process uploaded resume for revamp feature.

    Args:
        chat_id: Telegram chat ID
        file_path: Path to uploaded file
        file_type: File type (docx, pdf)
        job: Active revamp job
        db: Database session
        user: User object
    """
    try:
        from app.services import document_parser, router
        from sqlalchemy.orm.attributes import flag_modified

        # Show processing message
        await reply_text(chat_id, 
                       f"⏳ *Analyzing your resume...*\n\n"
                       f"📄 Extracting content from {file_type.upper()} file\n"
                       f"🤖 This may take 30-60 seconds\n\n"
                       f"_Please wait..._")

        # Parse the document
        parsed_data = document_parser.parse_document(file_path, file_type)

        logger.info(f"[handle_revamp_upload] Parsed {file_path.name}: "
                   f"{parsed_data['word_count']} words, "
                   f"{len(parsed_data['sections'])} sections")

        # Store parsed content in job
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

        logger.info(f"[handle_revamp_upload] Stored content in job.id={job.id}, advancing to processing")

        # Trigger revamp processing through router
        reply = await router.handle_revamp(db, job, "", user_tier=user.tier)

        if reply:
            await reply_text(chat_id, reply)

    except ValueError as ve:
        # Validation error (e.g., empty document)
        logger.warning(f"[handle_revamp_upload] Validation error: {ve}")
        await reply_text(chat_id, f"❌ *Document Error*\n\n{str(ve)}")

    except Exception as e:
        logger.error(f"[handle_revamp_upload] Error processing revamp upload: {e}")
        await reply_text(chat_id, 
                       f"❌ *Processing Error*\n\n"
                       f"Sorry, we couldn't process your resume.\n\n"
                       f"Please try:\n"
                       f"• Uploading a different file\n"
                       f"• Saving your resume in .docx format\n"
                       f"• Typing /reset to start over\n\n"
                       f"_Error: {str(e)}_")


async def send_document_to_user(chat_id: int | str, job_id: str, filename: str):
    """
    Send the generated document to the user via Telegram.

    Args:
        chat_id: Telegram chat ID
        job_id: Job ID
        filename: Document filename
    """
    try:
        # Find the file on disk
        file_path = Path("output") / "jobs" / job_id / filename

        if not file_path.exists():
            logger.error(f"[telegram_webhook] Document file not found: {file_path}")
            await reply_text(chat_id, "❌ Sorry, your document could not be found. Please try again.")
            return

        # Send document as .docx for review
        file_bytes = file_path.read_bytes()
        send_resp = await send_document(chat_id, file_bytes, filename, caption="📄 *Your Document is Ready!*")

        if send_resp and not send_resp.get("error"):
            logger.info(f"[telegram_webhook] Document sent to {chat_id}: {filename}")
            success_msg = """✅ *Document Delivered as .docx for Review!*

📝 *Review & Edit:*
• Download the document
• Open in Microsoft Word or Google Docs
• Make any changes you want
• Save your edits

📤 *Convert to PDF (Final Format):*
When you're happy with your edits:
1. Send the edited .docx file back to me
2. Type *convert to pdf* or */pdf*
3. I'll convert it to PDF for you!

Or if you're happy with it as is:
• Type */pdf* to convert the current version to PDF

*🔄 Need Another Document?*
Type /reset to create a new one
Type /status to check your plan

Good luck with your job search! 🚀"""
            await reply_text(chat_id, success_msg)
            return

        # Fallback to download link
        file_size_kb = file_path.stat().st_size // 1024
        download_url = f"{settings.public_url}/download/{job_id}/{filename}"
        doc_type = filename.split("_")[0].capitalize()

        message = f"""✅ Your {doc_type} is ready!

📄 *{filename}*
📦 Size: {file_size_kb}KB

Download here:
{download_url}

Reply /reset to create another document."""

        await reply_text(chat_id, message)
        logger.info(f"[telegram_webhook] Fallback download link sent to {chat_id}: {download_url}")

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

        # Check if user has premium access
        if user.tier != "pro":
            await reply_text(chat_id, """🔒 *PDF Export is a Premium Feature*

To convert your documents to PDF, you need premium access.

*Premium Benefits:*
• PDF export for all document types
• Priority support
• Unlimited document generations
• Advanced templates

Type /upgrade to get premium access now!""")
            return

        # Find the latest job
        latest_job = db.query(Job).filter(
            Job.user_id == user.id, 
            Job.status == "completed"
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
            pdf_bytes, pdf_filename = storage.convert_docx_to_pdf(latest_uploaded_docx)
        else:
            # No upload - generate PDF directly from data (all templates use ReportLab now)
            logger.info(f"[send_pdf] No edited DOCX, generating PDF directly from data")
            template = latest_job.answers.get('template', 'template_1')
            
            # All templates now have direct PDF generation
            try:
                pdf_bytes = pdf_renderer.render_pdf_from_data(latest_job.answers, template)
                # Generate filename
                doc_type = latest_job.type or 'document'
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                pdf_filename = f"{doc_type}_{template}_{timestamp}.pdf"
                logger.info(f"[send_pdf] Successfully generated PDF using ReportLab for {template}")
            except Exception as e:
                logger.error(f"[send_pdf] Direct PDF generation failed: {e}")
                # Fallback to LibreOffice conversion as last resort
                job_output_dir = Path("output") / "jobs" / latest_job.id
                if job_output_dir.exists():
                    docx_files = list(job_output_dir.glob("*.docx"))
                    if docx_files:
                        latest_docx_path = max(docx_files, key=lambda p: p.stat().st_mtime)
                        logger.info(f"[send_pdf] Falling back to LibreOffice for {template}")
                        pdf_bytes, pdf_filename = storage.convert_docx_to_pdf(latest_docx_path)

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
            # User clicked "Start with Free Plan"
            reply = await handle_inbound(db, str(chat_id), "free", telegram_username=username)
            if reply and reply.startswith("__SHOW_DOCUMENT_MENU__|"):
                parts = reply.split("|")
                if len(parts) >= 2:
                    tier = parts[1]
                    if len(parts) == 3:
                        await reply_text(chat_id, parts[2])
                    await send_document_type_menu(chat_id, tier)
            elif reply:
                await reply_text(chat_id, reply)

        elif data == "plan_premium":
            # User clicked "Start with Premium Plan"
            reply = await handle_inbound(db, str(chat_id), "/upgrade", telegram_username=username)
            if reply:
                await reply_text(chat_id, reply)

        elif data == "learn_more":
            # Show more info about the service
            info_msg = """📚 *About Career Buddy*

I'm an AI-powered assistant that helps you create professional career documents that stand out!

*🎯 What I create:*
• Professional Resumes (1-2 pages)
• Detailed CVs
• Professional Cover Letters
• Revamped/improved existing documents

*✨ Features:*
• AI-enhanced content
• ATS-friendly formatting
• Professional summaries
• Smart skill suggestions
• Instant delivery

*💰 Pricing:*
• Free: 2 documents
• Paid: ₦7,500 per document

Ready to create? Type /start!"""
            await reply_text(chat_id, info_msg)

        elif data.startswith("doc_"):
            # Document type selected
            doc_type = data.replace("doc_", "")
            reply = await handle_inbound(db, str(chat_id), doc_type, telegram_username=username)
            if reply:
                await reply_text(chat_id, reply)

        elif data.startswith("template_"):
            # Template selected
            template_num = data.replace("template_", "")
            logger.info(f"[callback_query] User {chat_id} selected {data}")

            # Update job with template choice
            from app.models import Job
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
                        await send_document_to_user(chat_id, parts[1], parts[2])
                elif reply:
                    await reply_text(chat_id, reply)
            else:
                await reply_text(chat_id, "❌ Session expired. Please type /reset to start over.")

        elif data == "payment_completed":
            # User claims they've paid - check their payment status
            await reply_text(chat_id, """✅ *Checking Payment Status...*

Please wait while we verify your payment.

If payment is confirmed, you'll be able to continue creating your document.

_This may take a few moments._""")
            # The actual payment verification happens via webhook

        elif data == "cancel":
            await reply_text(chat_id, "❌ *Cancelled*\n\nNo problem! Type /start when you're ready to create a document.")

        return {"ok": True}

    except Exception as e:
        logger.error(f"[callback_query] Error handling callback: {e}")
        return {"ok": False, "error": str(e)}


def extract_telegram_message(payload: dict) -> tuple[int | None, str | None, int | None, str | None]:
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
        Tuple of (chat_id, text, msg_id, username)
    """
    try:
        # Check if it's a message update
        message = payload.get("message")

        if not message:
            # Could be edited_message, callback_query, etc.
            logger.debug(f"[telegram_webhook] Non-message update type, ignoring")
            return None, None, None, None

        # Extract chat ID
        chat = message.get("chat", {})
        chat_id = chat.get("id")

        if not chat_id:
            logger.debug("[telegram_webhook] No chat_id found")
            return None, None, None, None

        # Only process private chats (ignore groups)
        if chat.get("type") != "private":
            logger.debug(f"[telegram_webhook] Ignoring non-private chat: {chat.get('type')}")
            return None, None, None, None

        # Extract message ID
        msg_id = message.get("message_id")

        # Extract username
        from_user = message.get("from", {})
        username = from_user.get("username")

        # Extract message text
        text = message.get("text")

        # Handle commands (convert to lowercase for consistency)
        if text and text.startswith("/"):
            # Keep commands like /start, /reset
            pass

        # Ignore messages without text (media, stickers, etc. for now)
        if not text:
            logger.debug("[telegram_webhook] Message without text, ignoring")
            return None, None, None, None

        return chat_id, text, msg_id, username

    except Exception as e:
        logger.error(f"[telegram_webhook] Failed to extract message from Telegram payload: {e}")
        logger.error(f"[telegram_webhook] Payload was: {payload}")
        return None, None, None, None


@router.post("/paystack")
async def paystack_webhook(request: Request, db=Depends(get_db)):
    """
    Paystack webhook endpoint for payment notifications.

    Paystack sends webhooks for various payment events.
    We primarily care about 'charge.success' events.
    """
    try:
        payload = await request.json()
        logger.info(f"[paystack_webhook] Received webhook: {payload.get('event')}")

        event = payload.get("event")
        data = payload.get("data", {})

        # Only process successful charges
        if event == "charge.success":
            reference = data.get("reference")
            amount = data.get("amount")  # in kobo
            status = data.get("status")
            metadata = data.get("metadata", {})

            if status == "success":
                user_id = metadata.get("user_id")
                telegram_user_id = metadata.get("telegram_user_id")
                purpose = metadata.get("role")  # Can be "premium_upgrade" or a target role

                if user_id:
                    from app.services import payments
                    from app.services.telegram import reply_text
                    from app.models import User

                    # Record payment
                    payments.record_payment(db, user_id, reference, amount, metadata, raw_payload=payload)

                    # Check if this is a premium upgrade payment
                    if purpose == "premium_upgrade":
                        # Upgrade user to pro tier
                        user = db.query(User).filter(User.id == user_id).first()
                        if user:
                            user.tier = "pro"
                            db.commit()
                            logger.info(f"[paystack_webhook] User {user_id} upgraded to pro tier")

                            # Notify user of upgrade
                            if telegram_user_id:
                                await reply_text(
                                    telegram_user_id,
                                    """🎉 *Payment Confirmed - You're Now Premium!*

✅ Account upgraded successfully

You now have access to:
• 🎨 Multiple professional templates
• 📄 Unlimited PDF conversions
• 🚀 Priority AI enhancements
• 💼 All document types (Resume, CV, Cover Letter, Revamp)

*🚀 Ready to create?*
Type /start to see the menu, then choose:
• *Resume* - Professional 1-2 page resume
• *CV* - Detailed curriculum vitae
• *Cover Letter* - Tailored application letter
• *Revamp* - Improve an existing document

Or simply type what you want to create!"""
                                )
                    else:
                        # Regular document generation payment
                        if telegram_user_id:
                            await reply_text(
                                telegram_user_id,
                                "✅ *Payment confirmed!*\n\n"
                                "Your document generation is now unlocked. "
                                "Return to your conversation and type *paid* to continue."
                            )

                    logger.info(f"[paystack_webhook] Payment processed: {reference} for user {user_id}")
                else:
                    logger.warning(f"[paystack_webhook] No user_id in metadata for reference {reference}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"[paystack_webhook] Error processing webhook: {e}")
        return {"status": "error", "message": str(e)}
