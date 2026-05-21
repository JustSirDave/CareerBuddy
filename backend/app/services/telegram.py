# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Xenaptis Technologies
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


async def send_welcome_menu(chat_id: int | str, first_name: str) -> dict:
    """Send the new-user welcome message with document-type inline keyboard."""
    text = (
        f"Hey {first_name}! 👋\n\n"
        "Welcome to CareerBuddy — your free AI assistant for creating professional "
        "Resumes, CVs, and Cover Letters through a simple conversation.\n\n"
        "Everything is completely free. What are you working on today?"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📄 Build my Resume / CV", "callback_data": "plan_free"},
                {"text": "✉️ Write a Cover Letter", "callback_data": "doc_cover"},
            ],
            [
                {"text": "✨ Revamp my existing doc", "callback_data": "doc_revamp"},
            ],
        ]
    }
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "reply_markup": keyboard}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.error(f"[telegram] send_welcome_menu failed: {r.status_code} {r.text}")
            return r.json() if r.content else {}
    except Exception as e:
        logger.error(f"[telegram] send_welcome_menu exception: {e}")
        return {"error": str(e)}


async def send_choice_menu(chat_id: int | str):
    """
    Send initial welcome message with inline keyboard.

    Args:
        chat_id: Telegram chat ID

    Returns:
        Response JSON from Telegram API
    """
    welcome_msg = (
        "👋 *Welcome to CareerBuddy!*\n\n"
        "Your free AI assistant for creating professional resumes, CVs, and cover letters.\n\n"
        "*🎯 What I can do:*\n"
        "• Build your Resume or CV from scratch\n"
        "• Write a tailored Cover Letter\n"
        "• Revamp your existing document\n\n"
        "Everything is completely free. No plans, no payments.\n\n"
        "Ready? Let's build something great. 👇"
    )

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"

    keyboard = {
        "inline_keyboard": [
            [{"text": "🚀 Get Started", "callback_data": "plan_free"}]
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


async def send_feedback_prompt(chat_id: int | str) -> dict:
    """Send post-delivery feedback prompt with inline keyboard."""
    text = "🙏 How was your experience with CareerBuddy?"
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "👍 Loved it!", "callback_data": "feedback_good"},
                {"text": "👎 Needs work", "callback_data": "feedback_bad"},
            ],
            [
                {"text": "🙈 Skip", "callback_data": "feedback_skip"},
            ],
        ]
    }
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "reply_markup": keyboard}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.error(f"[telegram] send_feedback_prompt failed: {r.status_code} {r.text}")
            return r.json() if r.content else {}
    except Exception as e:
        logger.error(f"[telegram] send_feedback_prompt exception: {e}")
        return {"error": str(e)}


async def send_confirm_menu(chat_id: int | str, text: str) -> dict:
    """Send a message with ✅ Yes / ❌ No inline keyboard buttons."""
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Yes", "callback_data": "confirm_yes"},
            {"text": "❌ No", "callback_data": "confirm_no"},
        ]]
    }
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": keyboard}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.error(f"[telegram] send_confirm_menu failed: {r.status_code} {r.text}")
            return r.json() if r.content else {}
    except Exception as e:
        logger.error(f"[telegram] send_confirm_menu exception: {e}")
        return {"error": str(e)}


async def send_revision_confirm_menu(chat_id: int | str, text: str) -> dict:
    """Send a message with ✅ Regenerate / ◀️ Back inline keyboard buttons."""
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Regenerate", "callback_data": "confirm_yes"},
            {"text": "◀️ Back to sections", "callback_data": "confirm_back"},
        ]]
    }
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": keyboard}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.error(f"[telegram] send_revision_confirm_menu failed: {r.status_code} {r.text}")
            return r.json() if r.content else {}
    except Exception as e:
        logger.error(f"[telegram] send_revision_confirm_menu exception: {e}")
        return {"error": str(e)}


async def forward_bad_feedback(feedback_text: str, username: str | None, from_chat_id: int | str) -> None:
    """Forward a bad-feedback message to FEEDBACK_CHANNEL_ID."""
    if not settings.feedback_channel_id:
        logger.warning("[feedback] FEEDBACK_CHANNEL_ID not set — feedback not forwarded")
        return

    # Telegram channels need a numeric chat_id; cast when possible
    channel_id: int | str = settings.feedback_channel_id
    try:
        channel_id = int(channel_id)
    except (ValueError, TypeError):
        pass  # keep as string (e.g. @channelname)

    sender = f"@{username}" if username else f"chat_id:{from_chat_id}"
    logger.info(f"[feedback] Forwarding bad feedback to channel={channel_id} from={sender}")
    text = f"📨 *Bad feedback from {sender}:*\n\n{feedback_text}"
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": channel_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.error(f"[feedback] Forward failed: status={r.status_code} body={r.text}")
            else:
                logger.info(f"[feedback] Forwarded bad feedback from {sender} — ok")
    except Exception as e:
        logger.error(f"[feedback] Forward exception: {e}")


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


async def send_document_url(chat_id: int | str, doc_url: str, filename: str, caption: str = None) -> dict:
    """
    Send a document to a Telegram user by passing a public URL.
    Telegram's servers fetch the file directly — no local download needed.
    """
    api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendDocument"
    payload = {"chat_id": chat_id, "document": doc_url, "filename": filename}
    if caption:
        payload["caption"] = caption
        payload["parse_mode"] = "Markdown"
    last_error = None
    for attempt in range(MAX_SEND_RETRIES):
        try:
            logger.info(f"[telegram] Sending document by URL: {filename} → {doc_url}")
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(api_url, json=payload)
            if r.status_code == 200:
                logger.info(f"[telegram] Document URL sent successfully to {chat_id}: {filename}")
                return r.json() if r.content else {}
            if r.status_code == 403:
                logger.warning(f"Bot blocked by user {chat_id}")
                return {"error": "blocked"}
            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 10))
                await asyncio.sleep(retry_after)
                continue
            last_error = f"{r.status_code} {r.text}"
            logger.error(f"[telegram] send_document_url failed attempt {attempt+1}: {last_error}")
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_error = e
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            await asyncio.sleep(delay)
        except Exception as e:
            last_error = e
            break
    logger.error(f"Failed to send document URL to {chat_id} after {MAX_SEND_RETRIES} attempts: {last_error}")
    return {"error": str(last_error)}


async def _send_with_buttons(chat_id: int | str, text: str, buttons: list) -> dict:
    """Send a Telegram message with an inline keyboard."""
    api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": buttons},
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(api_url, json=payload)
        if r.status_code >= 400:
            logger.error(f"[telegram] _send_with_buttons failed: {r.status_code} {r.text}")
        return r.json() if r.content else {}
    except Exception as e:
        logger.error(f"[telegram] _send_with_buttons exception: {e}")
        return {"error": str(e)}


async def send_step_done_prompt(chat_id: int | str, text: str) -> dict:
    """Send message with [✅ Done] button."""
    return await _send_with_buttons(
        chat_id, text, [[{"text": "✅ Done", "callback_data": "step_done"}]]
    )


async def send_step_done_skip_prompt(chat_id: int | str, text: str) -> dict:
    """Send message with [✅ Done] [⏭️ Skip] buttons."""
    return await _send_with_buttons(chat_id, text, [[
        {"text": "✅ Done", "callback_data": "step_done"},
        {"text": "⏭️ Skip", "callback_data": "step_skip"},
    ]])


async def send_step_continue_skip_prompt(chat_id: int | str, text: str) -> dict:
    """Send message with [➡️ Continue] [⏭️ Skip] buttons."""
    return await _send_with_buttons(chat_id, text, [[
        {"text": "➡️ Continue", "callback_data": "step_continue"},
        {"text": "⏭️ Skip", "callback_data": "step_skip"},
    ]])


async def send_add_another_prompt(chat_id: int | str, text: str) -> dict:
    """Send message with [➕ Add Another] [✅ Done Adding] buttons."""
    return await _send_with_buttons(chat_id, text, [[
        {"text": "➕ Add Another", "callback_data": "add_another"},
        {"text": "✅ Done Adding", "callback_data": "step_done"},
    ]])


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


async def send_format_menu(chat_id: int | str, job_id: str) -> dict:
    """Ask the user to choose DOCX or PDF delivery format."""
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📄 Word (.docx)", "callback_data": f"format_docx|{job_id}"},
                {"text": "📕 PDF", "callback_data": f"format_pdf|{job_id}"},
            ]
        ]
    }
    payload = {
        "chat_id": chat_id,
        "text": "🎉 *Almost done!* Which format would you like your document in?",
        "parse_mode": "Markdown",
        "reply_markup": keyboard,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                logger.error(f"Telegram send format menu failed: {r.status_code} {r.text}")
            return r.json() if r.content else {}
    except Exception as e:
        logger.error(f"Telegram send format menu exception: {e}")
        return {"error": str(e)}





