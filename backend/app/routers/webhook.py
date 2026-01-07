# backend/app/routers/webhook.py
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Depends
from loguru import logger

from app.config import settings
from app.services.idempotency import seen_or_mark
from app.db import get_db
from app.services.telegram import reply_text, send_choice_menu, send_document, send_document_type_menu, send_typing_action
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

    if reply:
        await reply_text(chat_id, reply)
    return {"ok": True}


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

        # Send document directly
        file_bytes = file_path.read_bytes()
        send_resp = await send_document(chat_id, file_bytes, filename, caption="Here's your document! 📄")

        if send_resp and not send_resp.get("error"):
            logger.info(f"[telegram_webhook] Document sent to {chat_id}: {filename}")
            success_msg = """✅ *Document Delivered!*

Your professional document is ready to use!

*📋 What's Next?*
• Review and customize it
• Download and print  
• Share with recruiters

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
        
        elif data == "learn_more":
            # Show more info about the service
            info_msg = """📚 *About Career Buddy*

I'm an AI-powered assistant that helps you create professional career documents that stand out!

*🎯 What I create:*
• Professional Resumes (1-2 pages)
• Detailed CVs
• Revamped/improved existing documents
• Cover Letters (coming soon!)

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
            if doc_type == "cover":
                await reply_text(chat_id, "📝 *Cover Letter generation is coming soon!*\n\nFor now, try creating a Resume or CV. Type /start to begin!")
            else:
                reply = await handle_inbound(db, str(chat_id), doc_type, telegram_username=username)
                if reply:
                    await reply_text(chat_id, reply)
        
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

                if user_id:
                    from app.services import payments
                    from app.services.telegram import reply_text

                    # Record payment
                    payments.record_payment(db, user_id, reference, amount, metadata, raw_payload=payload)

                    # Notify user
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
