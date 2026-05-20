# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Xenaptis Technologies
"""
Monthly document usage tracking and enforcement.
"""
from datetime import date

from sqlalchemy.orm import Session

from app.config import settings
from app.models import User


def check_and_increment(user: User, db: Session) -> str | None:
    """
    Check monthly document limit and increment the counter if under limit.

    Resets the counter at the start of each calendar month.
    Returns None when the user is allowed to proceed, or an error message
    string when the limit has been reached.
    """
    today = date.today()
    reset_date = getattr(user, "monthly_reset_date", None)

    if reset_date is None or reset_date.month != today.month or reset_date.year != today.year:
        user.monthly_doc_count = 0
        user.monthly_reset_date = today

    doc_count = user.monthly_doc_count or 0
    limit = settings.monthly_doc_limit

    if doc_count >= limit:
        return (
            f"📊 *Monthly limit reached*\n\n"
            f"You've created {doc_count} document{'s' if doc_count != 1 else ''} this month "
            f"(limit: {limit}).\n\n"
            f"Your limit resets on the 1st of next month.\n\n"
            f"🙏 *Enjoying CareerBuddy?*\n"
            f"If this tool has been useful, consider supporting the project on Ko-fi — "
            f"it helps keep CareerBuddy free for everyone:\n"
            f"https://ko-fi.com/careerbuddy"
        )

    user.monthly_doc_count = doc_count + 1
    db.commit()
    return None
