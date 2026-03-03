"""
Delivery confirmation task.
Sends a 24hr follow-up message after document delivery.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models import Job, User
from app.services.telegram import reply_text

logger = logging.getLogger(__name__)

CONFIRMATION_MESSAGES = {
    "resume": (
        "Hey {first_name}! 👋\n\n"
        "How did your resume land? Hope it's helping with your applications.\n\n"
        "Need any tweaks? Send /revise and I'll guide you through it.\n"
        "Ready for a cover letter? Send /start 🚀"
    ),
    "cv": (
        "Hey {first_name}! 👋\n\n"
        "Hope your CV is opening doors! How's the job search going?\n\n"
        "Need any tweaks? Send /revise and I'll guide you through it.\n"
        "Want a cover letter to go with it? Send /start 🚀"
    ),
    "cover": (
        "Hey {first_name}! 👋\n\n"
        "Hope that cover letter made a great impression!\n\n"
        "Need any tweaks? Send /revise and I'll guide you through it.\n"
        "Ready to create another document? Send /start 🚀"
    ),
    "cover_letter": (
        "Hey {first_name}! 👋\n\n"
        "Hope that cover letter made a great impression!\n\n"
        "Need any tweaks? Send /revise and I'll guide you through it.\n"
        "Ready to create another document? Send /start 🚀"
    ),
}


def send_pending_delivery_confirmations(db: Session) -> None:
    """
    Called by scheduler every 30 minutes.
    Finds jobs completed 23–25 hours ago with no follow-up sent yet.
    """
    cutoff_start = datetime.utcnow() - timedelta(hours=25)
    cutoff_end = datetime.utcnow() - timedelta(hours=23)

    jobs = (
        db.query(Job)
        .filter(
            Job.status.in_(["preview_ready", "done", "completed"]),
            Job.completed_at >= cutoff_start,
            Job.completed_at <= cutoff_end,
            Job.delivery_confirmation_sent.is_(False),
        )
        .all()
    )

    for job in jobs:
        try:
            user = db.query(User).filter(User.id == job.user_id).first()
            if not user or not user.telegram_user_id:
                continue

            message_template = CONFIRMATION_MESSAGES.get(
                job.type, CONFIRMATION_MESSAGES["resume"]
            )
            first_name = (
                getattr(user, "telegram_first_name", None)
                or user.name
                or "there"
            )
            if not first_name:
                first_name = "there"

            asyncio.run(
                reply_text(
                    user.telegram_user_id,
                    message_template.format(first_name=first_name),
                )
            )

            job.delivery_confirmation_sent = True
            db.commit()
            logger.info(f"Delivery confirmation sent: job_id={job.id}")

        except Exception as e:
            logger.error(f"Delivery confirmation failed for job {job.id}: {e}")
            db.rollback()
