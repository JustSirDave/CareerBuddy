# backend/app/api/whatsapp_webhook.py
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Depends
from loguru import logger

from app.config import settings
from app.services.idempotency import seen_or_mark
from app.db import get_db
from app.services.whatsapp import reply_text, send_choice_menu, send_document, send_document_type_menu
from app.services.router import handle_inbound

router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])


@router.post("")
async def receive(request: Request, db=Depends(get_db)):
    """
    WAHA webhook endpoint.
    Receives messages from WAHA and processes them.
    """
    try:
        payload = await request.json()
        logger.debug(f"[webhook] Received WAHA webhook: {payload}")
    except Exception as e:
        logger.error(f"[webhook] Failed to parse JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Extract message from WAHA payload
    wa_id, text, msg_id = extract_message(payload)
    if not wa_id:
        logger.debug("[webhook] No valid message found, ignoring")
        return {"status": "ignored"}

    # EARLY DEDUPLICATION: Check BEFORE calling handle_inbound
    if msg_id and seen_or_mark(msg_id):
        logger.warning(f"[webhook] Duplicate msg_id={msg_id} from wa_id={wa_id}, skipping")
        return {"status": "duplicate"}

    # Now process the message
    reply = await handle_inbound(db, wa_id, text or "", msg_id=msg_id)

    if reply == "__SHOW_MENU__":
        await send_choice_menu(wa_id)
        return {"status": "ok"}

    # Check if document type menu should be shown (with confirmation message)
    if reply and reply.startswith("__SHOW_DOCUMENT_MENU__|"):
        parts = reply.split("|")
        if len(parts) >= 2:
            tier = parts[1]
            # If there's a confirmation message, send it first
            if len(parts) == 3:
                confirmation_msg = parts[2]
                await reply_text(wa_id, confirmation_msg)
            # Then show document type menu
            await send_document_type_menu(wa_id, tier)
        return {"status": "ok"}

    # Check if document should be sent
    if reply and reply.startswith("__SEND_DOCUMENT__|"):
        parts = reply.split("|")
        if len(parts) == 3:
            _, job_id, filename = parts
            await send_document_to_user(wa_id, job_id, filename)
        return {"status": "ok"}

    if reply:
        await reply_text(wa_id, reply)
    return {"status": "ok"}


async def send_document_to_user(wa_id: str, job_id: str, filename: str):
    """
    Send the generated document to the user via WhatsApp.
    Attempts direct file send via WAHA; falls back to a download link.

    Args:
        wa_id: WhatsApp user ID
        job_id: Job ID
        filename: Document filename
    """
    try:
        # Find the file on disk
        file_path = Path("output") / "jobs" / job_id / filename

        if not file_path.exists():
            logger.error(f"[webhook] Document file not found: {file_path}")
            await reply_text(wa_id, "❌ Sorry, your document could not be found. Please try again.")
            return

        # Send document directly
        file_bytes = file_path.read_bytes()
        send_resp = await send_document(wa_id, file_bytes, filename, caption="Here's your document! 📄")

        if send_resp and not send_resp.get("error"):
            logger.info(f"[webhook] Document sent to {wa_id}: {filename}")
            await reply_text(wa_id, "✅ Delivered! Reply */reset* to create another document.")
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

Reply */reset* to create another document."""

        await reply_text(wa_id, message)
        logger.info(f"[webhook] Fallback download link sent to {wa_id}: {download_url}")

    except Exception as e:
        logger.error(f"[webhook] Error sending download link: {e}")
        await reply_text(wa_id, "❌ Sorry, something went wrong. Please try again.")


def extract_message(payload: dict) -> tuple[str | None, str | None, str | None]:
    """
    Extract message data from WAHA webhook payload.

    WAHA webhook format:
    {
        "event": "message",
        "session": "default",
        "payload": {
            "id": "message_id",
            "timestamp": 1234567890,
            "from": "1234567890@c.us",
            "body": "message text",
            "hasMedia": false
        }
    }

    Args:
        payload: WAHA webhook payload

    Returns:
        Tuple of (wa_id, text, msg_id)
    """
    try:
        event = payload.get("event")

        # Only process 'message' events
        if event != "message":
            logger.debug(f"[webhook] Ignoring non-message event: {event}")
            return None, None, None

        message_payload = payload.get("payload", {})

        # Extract phone number (remove @c.us suffix)
        from_field = message_payload.get("from", "")

        # Ignore group messages (they have @g.us)
        if "@g.us" in from_field:
            logger.debug(f"[webhook] Ignoring group message from: {from_field}")
            return None, None, None

        # Ignore status broadcasts
        if "status@broadcast" in from_field:
            logger.debug(f"[webhook] Ignoring status broadcast")
            return None, None, None

        # Ignore messages from self
        if message_payload.get("fromMe"):
            logger.debug("[webhook] Ignoring message from self")
            return None, None, None

        wa_id = from_field.replace("@c.us", "").replace("@s.whatsapp.net", "")

        # Extract message ID
        msg_id = message_payload.get("id")

        # Extract message text
        text = None

        # Check if it's a button response
        if message_payload.get("_data", {}).get("selectedButtonId"):
            # Handle button responses (from send_choice_menu)
            button_id = message_payload["_data"]["selectedButtonId"]
            text = button_id.replace("choose_", "").capitalize()
            logger.info(f"[webhook] Button response: {button_id} -> {text}")
        elif message_payload.get("body"):
            # Regular text message
            text = message_payload.get("body")

        # Ignore media messages for now
        if message_payload.get("hasMedia") and not text:
            logger.debug("[webhook] Media message without text, ignoring")
            return None, None, None

        return wa_id, text, msg_id

    except Exception as e:
        logger.error(f"[webhook] Failed to extract message from WAHA payload: {e}")
        logger.error(f"[webhook] Payload was: {payload}")
        return None, None, None


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
                wa_id = metadata.get("wa_id")

                if user_id:
                    from app.services import payments
                    from app.services.whatsapp import reply_text

                    # Record payment
                    payments.record_payment(db, user_id, reference, amount, metadata, raw_payload=payload)

                    # Notify user
                    if wa_id:
                        await reply_text(
                            wa_id,
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
