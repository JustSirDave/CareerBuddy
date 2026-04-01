"""
CareerBuddy - Telegram Bot Service
Handles sending messages and documents via Telegram Bot API
Author: Sir Dave
"""
import asyncio
import httpx
from io import BytesIO
from loguru import logger
from app.config import settings

MAX_SEND_RETRIES = 3
RETRY_BASE_DELAY = 1  # seconds


async def reply_text(chat_id: int | str, text: str, parse_mode: str = "Markdown"):
    """
    Send a text message via Telegram Bot API with retry on transient failures.
    Falls back to plain text if Markdown parsing fails (400).
    Returns dict with response or {"error": str}. Never raises.
    """
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    last_error = None
    for attempt in range(MAX_SEND_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(url, json=payload)
            if r.status_code == 200:
                logger.info(f"[telegram] Message sent successfully to {chat_id}")
                return r.json() if r.content else {}
            if r.status_code == 403:
                logger.warning(f"Bot blocked by user {chat_id}")
                return {"error": "blocked"}
            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 5))
                await asyncio.sleep(retry_after)
                continue
            if r.status_code == 400 and "can't parse entities" in (r.text or ""):
                logger.warning(f"[telegram] Markdown parse failed for {chat_id}, retrying as plain text")
                plain_payload = {"chat_id": chat_id, "text": text}
                async with httpx.AsyncClient(timeout=60.0) as client:
                    r2 = await client.post(url, json=plain_payload)
                if r2.status_code == 200:
                    logger.info(f"[telegram] Message sent as plain text to {chat_id}")
                    return r2.json() if r2.content else {}
                last_error = f"{r2.status_code} {r2.text}"
                break
            last_error = f"{r.status_code} {r.text}"
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_error = e
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            await asyncio.sleep(delay)
        except Exception as e:
            last_error = e
            break
    logger.error(f"Failed to send message to {chat_id} after {MAX_SEND_RETRIES} attempts: {last_error}")
    return {"error": str(last_error)}


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


async def send_onboarding_continue_menu(chat_id: int | str, message: str):
    """Send message with Continue / Start Fresh buttons for returning users with active job."""
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    keyboard = {
        "inline_keyboard": [
            [{"text": "▶️ Continue", "callback_data": "onboarding_continue"}],
            [{"text": "🔄 Start Fresh", "callback_data": "onboarding_start_fresh"}]
        ]
    }
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown", "reply_markup": keyboard}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.error(f"Telegram send onboarding menu failed: {r.status_code} {r.text}")
            return r.json() if r.content else {}
    except Exception as e:
        logger.error(f"Telegram send onboarding menu exception: {e}")
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
                {"text": "✨ Revamp Existing (Soon)", "callback_data": "doc_revamp"}
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
    Send a document file to a Telegram user with retry on transient failures.
    """
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendDocument"
    files = {"document": (filename, BytesIO(file_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    last_error = None
    for attempt in range(MAX_SEND_RETRIES):
        try:
            logger.info(f"[telegram] Sending document: {filename} ({len(file_bytes)} bytes)")
            async with httpx.AsyncClient(timeout=90) as client:
                r = await client.post(url, files=files, data=data)
            if r.status_code == 200:
                logger.info(f"[telegram] Document sent successfully to {chat_id}: {filename}")
                return r.json() if r.content else {}
            if r.status_code == 403:
                logger.warning(f"Bot blocked by user {chat_id}")
                return {"error": "blocked"}
            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 10))
                await asyncio.sleep(retry_after)
                continue
            last_error = f"{r.status_code} {r.text}"
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_error = e
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            await asyncio.sleep(delay)
        except Exception as e:
            last_error = e
            break
    logger.error(f"Failed to send document to {chat_id} after {MAX_SEND_RETRIES} attempts: {last_error}")
    return {"error": str(last_error)}


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



