import httpx
from io import BytesIO
import base64
from loguru import logger
from app.config import settings


def _get_headers():
    """Get headers for WAHA API requests."""
    headers = {"Content-Type": "application/json"}
    if settings.waha_api_key:
        headers["X-Api-Key"] = settings.waha_api_key
    return headers


def _format_phone(wa_id: str) -> str:
    """
    Format phone number for WAHA.
    Handles multiple WhatsApp ID formats:
    - @c.us (regular WhatsApp numbers)
    - @lid (Linked ID / Business accounts)
    - @s.whatsapp.net (alternative format)
    """
    # If already has a WhatsApp suffix, return as-is
    if "@c.us" in wa_id or "@lid" in wa_id or "@s.whatsapp.net" in wa_id:
        return wa_id
    # Otherwise, add standard @c.us suffix
    return f"{wa_id}@c.us"


async def reply_text(wa_id: str, text: str):
    """
    Send a text message via WAHA.

    Args:
        wa_id: WhatsApp user ID
        text: Message text

    Returns:
        Response JSON from WAHA API
    """
    url = f"{settings.waha_url}/api/sendText"
    headers = _get_headers()
    payload = {
        "session": settings.waha_session,
        "chatId": _format_phone(wa_id),
        "text": text
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code >= 400:
                logger.error(f"WAHA send text failed: {r.status_code} {r.text}")
            return r.json() if r.content else {}
    except Exception as e:
        logger.error(f"WAHA send text exception: {e}")
        return {"error": str(e)}


async def send_choice_menu(wa_id: str):
    """
    Send initial welcome message and tier selection.

    Args:
        wa_id: WhatsApp user ID

    Returns:
        Response JSON from WAHA API
    """
    welcome_msg = """👋 Hi! I'm Career Buddy, your personal AI assistant for creating professional resumes, CVs, and cover letters tailored to your dream role.

Need help? Contact support on WhatsApp: 07063011079"""

    await reply_text(wa_id, welcome_msg)

    # Send tier selection as a second message
    tier_msg = """Let's get started! Choose your plan:

*🆓 Free Plan*
• 2 free documents (Resume or CV)
• AI-powered generation with GPT-4o-mini
• Professional summaries
• Smart skill suggestions
• Standard support

*💳 Pay-Per-Generation*
• ₦7,500 per document
• Enhanced AI with business impact analysis
• Senior-level professional summaries
• Advanced skills extraction
• Cover letter generation (coming soon)
• Priority support
• Max 5 documents per role

Ready to begin?
• Type *Free* to start with 2 free documents
• After free limit, pay ₦7,500 per document"""

    return await reply_text(wa_id, tier_msg)


async def send_document_type_menu(wa_id: str, user_tier: str = "free"):
    """
    Send document type selection menu based on user tier.

    Args:
        wa_id: WhatsApp user ID
        user_tier: User's subscription tier (free or pro)

    Returns:
        Response JSON from WAHA API
    """
    menu_text = """Perfect! What would you like to create today?

Choose one:
• *Resume*
• *CV*
• *Revamp* (improve existing resume/CV)

_💡 Cover Letter generation coming soon!_"""

    return await reply_text(wa_id, menu_text)


async def send_document(wa_id: str, file_bytes: bytes, filename: str, caption: str = None) -> dict:
    """
    Send a document file to a WhatsApp user via WAHA.

    Args:
        wa_id: WhatsApp user ID
        file_bytes: File content as bytes
        filename: Name of the file
        caption: Optional caption text

    Returns:
        Response JSON from WAHA API
    """
    url = f"{settings.waha_url}/api/sendFile"
    headers = _get_headers()

    # WAHA expects base64 encoded file
    file_base64 = base64.b64encode(file_bytes).decode('utf-8')

    payload = {
        "session": settings.waha_session,
        "chatId": _format_phone(wa_id),
        "file": {
            "mimetype": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "filename": filename,
            "data": file_base64
        }
    }

    if caption:
        payload["caption"] = caption

    try:
        logger.info(f"[whatsapp] Sending document via WAHA: {filename} ({len(file_bytes)} bytes)")
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json=payload)

            if r.status_code >= 400:
                logger.error(f"WAHA send document failed: {r.status_code} {r.text}")
                return {"error": "document_send_failed"}
            else:
                logger.info(f"[whatsapp] Document sent successfully to {wa_id}: {filename}")

            return r.json() if r.content else {}

    except Exception as e:
        logger.error(f"[whatsapp] Document send exception: {e}")
        return {"error": str(e)}


# Legacy functions for backward compatibility (no longer needed with WAHA)
async def upload_media(file_bytes: bytes, filename: str, mime_type: str = "application/vnd.openxmlformats-officedocument.wordprocessingml.document") -> str | None:
    """
    Legacy function - WAHA doesn't require separate upload step.
    Kept for backward compatibility but does nothing.
    """
    logger.warning("[whatsapp] upload_media called but not needed with WAHA")
    return None
