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
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.error(f"Telegram send text failed: {r.status_code} {r.text}")
            else:
                logger.info(f"[telegram] Message sent successfully to {chat_id}")
            return r.json() if r.content else {}
    except httpx.TimeoutException as e:
        logger.error(f"Telegram send text timeout after 60s: {e}")
        return {"error": "timeout"}
    except Exception as e:
        logger.error(f"Telegram send text exception: {type(e).__name__}: {e}")
        return {"error": str(e)}


async def send_choice_menu(chat_id: int | str):
    """
    Send initial welcome message with inline keyboard for plan selection.

    Args:
        chat_id: Telegram chat ID

    Returns:
        Response JSON from Telegram API
    """
    welcome_msg = """👋 *Welcome to Career Buddy!*

Your personal AI assistant for creating professional resumes, CVs, and cover letters tailored to your dream role.

*🎯 What I offer:*

*🆓 Free Plan*
• 2 free documents (Resume or CV)
• AI-powered generation
• Professional summaries
• Smart skill suggestions

*💳 Pay-Per-Generation*
• ₦7,500 per document
• Enhanced AI features
• Business impact analysis
• Priority support

_Need help? Use /help command_"""

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    
    # Inline keyboard with buttons
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🆓 Start with Free Plan", "callback_data": "plan_free"}
            ],
            [
                {"text": "⭐ Start with Premium Plan", "callback_data": "plan_premium"}
            ],
            [
                {"text": "💡 Learn More", "callback_data": "learn_more"}
            ]
        ]
    }
    
    payload = {
        "chat_id": chat_id,
        "text": welcome_msg,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.error(f"Telegram send menu failed: {r.status_code} {r.text}")
            return r.json() if r.content else {}
    except Exception as e:
        logger.error(f"Telegram send menu exception: {e}")
        return {"error": str(e)}


async def send_document_type_menu(chat_id: int | str, user_tier: str = "free"):
    """
    Send document type selection menu with inline keyboard.

    Args:
        chat_id: Telegram chat ID
        user_tier: User's subscription tier (free or pro)

    Returns:
        Response JSON from Telegram API
    """
    menu_text = """✨ *Let's Create Your Document!*

Choose what you'd like to create:"""

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    
    # Inline keyboard for document types
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📄 Resume", "callback_data": "doc_resume"},
                {"text": "📋 CV", "callback_data": "doc_cv"}
            ],
            [
                {"text": "✨ Revamp Existing", "callback_data": "doc_revamp"}
            ],
            [
                {"text": "📝 Cover Letter", "callback_data": "doc_cover"}
            ],
            [
                {"text": "❌ Cancel", "callback_data": "cancel"}
            ]
        ]
    }
    
    payload = {
        "chat_id": chat_id,
        "text": menu_text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.error(f"Telegram send doc menu failed: {r.status_code} {r.text}")
            return r.json() if r.content else {}
    except Exception as e:
        logger.error(f"Telegram send doc menu exception: {e}")
        return {"error": str(e)}


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
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(url, json=payload)
    except Exception as e:
        logger.warning(f"[telegram] Send typing action failed (non-critical): {type(e).__name__}")


async def send_template_selection(chat_id: int | str, user_tier: str) -> dict:
    """
    Send template selection menu with inline keyboard (premium users only).
    
    Args:
        chat_id: Telegram chat ID
        user_tier: User's tier (free or pro)
    
    Returns:
        Response JSON from Telegram API
    """
    message = """🎨 *Choose Your Template*

Select a professional template for your document:

*Template 1* - Classic Professional
Clean, traditional layout

*Template 2* - Modern Minimal
Contemporary design with side sections

*Template 3* - Executive Bold  
Stand-out format for leadership roles

_All templates are ATS-compliant and professionally formatted._"""

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📄 Template 1 (Classic)", "callback_data": "template_1"}
            ],
            [
                {"text": "📋 Template 2 (Modern)", "callback_data": "template_2"}
            ],
            [
                {"text": "✨ Template 3 (Executive)", "callback_data": "template_3"}
            ]
        ]
    }
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.error(f"Telegram send template selection failed: {r.status_code} {r.text}")
            return r.json() if r.content else {}
    except Exception as e:
        logger.error(f"Telegram send template selection exception: {e}")
        return {"error": str(e)}


async def send_payment_request(chat_id: int | str, payment_url: str, amount: int) -> dict:
    """
    Send payment request with inline keyboard button.
    
    Args:
        chat_id: Telegram chat ID
        payment_url: Paystack payment URL
        amount: Amount in Naira
    
    Returns:
        Response JSON from Telegram API
    """
    message = f"""💳 *Payment Required*

To continue creating your document, please complete your payment:

*Amount:* ₦{amount:,}
*What you get:*
• Professional AI-enhanced document
• ATS-compliant formatting
• Instant delivery
• Priority support

Click the button below to pay securely with Paystack:"""

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "💳 Pay ₦{:,}".format(amount), "url": payment_url}
            ],
            [
                {"text": "✅ I've Paid", "callback_data": "payment_completed"},
                {"text": "❌ Cancel", "callback_data": "cancel"}
            ]
        ]
    }
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.error(f"Telegram send payment failed: {r.status_code} {r.text}")
            return r.json() if r.content else {}
    except Exception as e:
        logger.error(f"Telegram send payment exception: {e}")
        return {"error": str(e)}


# Legacy function names for backward compatibility during refactoring
upload_media = None  # Not needed for Telegram

