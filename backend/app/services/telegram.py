"""
Telegram Bot Service for CareerBuddy
Handles sending messages and documents via Telegram Bot API
"""
import httpx
from io import BytesIO
from loguru import logger
from app.config import settings


async def reply_text(chat_id: int | str, text: str, parse_mode: str = "Markdown"):
    """
    Send a text message via Telegram Bot API.

    Args:
        chat_id: Telegram chat ID (user ID)
        text: Message text (supports Markdown formatting)
        parse_mode: Message formatting (Markdown, HTML, or None)

    Returns:
        Response JSON from Telegram API
    """
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.error(f"Telegram send text failed: {r.status_code} {r.text}")
            return r.json() if r.content else {}
    except Exception as e:
        logger.error(f"Telegram send text exception: {e}")
        return {"error": str(e)}


async def send_choice_menu(chat_id: int | str):
    """
    Send initial welcome message and tier selection.

    Args:
        chat_id: Telegram chat ID

    Returns:
        Response JSON from Telegram API
    """
    welcome_msg = """👋 Hi! I'm Career Buddy, your personal AI assistant for creating professional resumes, CVs, and cover letters tailored to your dream role.

Need help? Contact support: @YourSupportHandle"""

    await reply_text(chat_id, welcome_msg)

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

    return await reply_text(chat_id, tier_msg)


async def send_document_type_menu(chat_id: int | str, user_tier: str = "free"):
    """
    Send document type selection menu based on user tier.

    Args:
        chat_id: Telegram chat ID
        user_tier: User's subscription tier (free or pro)

    Returns:
        Response JSON from Telegram API
    """
    menu_text = """Perfect! What would you like to create today?

Choose one:
• *Resume*
• *CV*
• *Revamp* (improve existing resume/CV)

_💡 Cover Letter generation coming soon!_"""

    return await reply_text(chat_id, menu_text)


async def send_document(chat_id: int | str, file_bytes: bytes, filename: str, caption: str = None) -> dict:
    """
    Send a document file to a Telegram user.

    Args:
        chat_id: Telegram chat ID
        file_bytes: File content as bytes
        filename: Name of the file
        caption: Optional caption text

    Returns:
        Response JSON from Telegram API
    """
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendDocument"

    try:
        logger.info(f"[telegram] Sending document: {filename} ({len(file_bytes)} bytes)")
        
        # Prepare multipart form data
        files = {
            'document': (filename, BytesIO(file_bytes), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        }
        
        data = {
            'chat_id': chat_id
        }
        
        if caption:
            data['caption'] = caption

        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, files=files, data=data)

            if r.status_code >= 400:
                logger.error(f"Telegram send document failed: {r.status_code} {r.text}")
                return {"error": "document_send_failed"}
            else:
                logger.info(f"[telegram] Document sent successfully to {chat_id}: {filename}")

            return r.json() if r.content else {}

    except Exception as e:
        logger.error(f"[telegram] Document send exception: {e}")
        return {"error": str(e)}


async def send_typing_action(chat_id: int | str):
    """
    Send 'typing' action to show bot is processing.

    Args:
        chat_id: Telegram chat ID
    """
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendChatAction"
    payload = {
        "chat_id": chat_id,
        "action": "typing"
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)
    except Exception as e:
        logger.error(f"[telegram] Send typing action exception: {e}")


# Legacy function names for backward compatibility during refactoring
upload_media = None  # Not needed for Telegram

