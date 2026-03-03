"""
CareerBuddy Error Handler
Centralised error recovery, messaging, and logging.
Author: Sir Dave
"""
from enum import Enum
from loguru import logger

from app.services.telegram import reply_text


class ErrorType(str, Enum):
    INVALID_INPUT = "invalid_input"
    AI_FAILURE = "ai_failure"
    RENDER_FAILURE = "render_failure"
    SEND_FAILURE = "send_failure"
    DB_FAILURE = "db_failure"
    UNEXPECTED = "unexpected"


ERROR_MESSAGES = {
    "invalid_email": "That doesn't look like a valid email address. Could you double-check it? _(e.g. yourname@gmail.com)_",
    "invalid_phone": "I need a valid phone number here. Try something like _08012345678_ or _+2348012345678_.",
    "invalid_date_range": "I need dates in this format: *Month Year – Month Year* _(e.g. Jan 2022 – Mar 2024)_. Give it another try.",
    "too_few_bullets": "Add at least 2 achievement bullets for this role. What did you accomplish there?",
    "invalid_skills_selection": "Just type the numbers of the skills you want, separated by commas _(e.g. 1, 3, 5)_. Or type your own skills.",
    "basics_format": "Please share your details like this:\n*Full Name, email@example.com, 08012345678, Lagos*",
    "ai_skills_failed": "I couldn't generate skill suggestions right now — no worries, just type your skills directly and I'll include them.",
    "ai_summary_failed": "I had trouble generating your summary. You can write one yourself, or type *skip* and I'll use a standard format.",
    "ai_generic_failed": "My AI brain had a hiccup there 😅 Let's keep going — I'll do my best without it.",
    "docx_render_failed": "I hit a snag generating your document. Your information is safe — type *retry* to try again.",
    "pdf_render_failed": "I couldn't convert to PDF right now. Your DOCX is ready though — type */pdf* again in a moment to retry.",
    "job_in_progress": "Hey, you're in the middle of creating your {doc_type}! Want to continue where you left off, or start fresh?",
    "step_reminder": "We're on: *{step_label}*\n\n{step_prompt}",
    "session_expired_graceful": "It's been a while! Your {doc_type} is still saved. Want to pick up where you left off?",
    "generic_fallback": "Something unexpected happened on my end. Your progress is saved — just send any message and I'll get us back on track.",
}


async def handle_error(
    error_type: ErrorType,
    telegram_id: int | str,
    error_key: str,
    context: dict | None = None,
    exception: Exception | None = None,
) -> None:
    """
    Central error handler. Logs the error, sends appropriate recovery message.
    context: dict of template variables for message formatting (e.g. doc_type, step_label)
    """
    logger.error(
        f"[{error_type.value}] key={error_key} telegram_id={telegram_id} "
        f"context={context} exception={exception}",
        exc_info=exception is not None,
    )
    message = ERROR_MESSAGES.get(error_key, ERROR_MESSAGES["generic_fallback"])
    if context:
        try:
            message = message.format(**context)
        except KeyError:
            pass
    try:
        await reply_text(telegram_id, message)
    except Exception as send_exc:
        logger.critical(f"Failed to send error message to {telegram_id}: {send_exc}")
