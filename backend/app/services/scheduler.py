"""
Background task scheduler.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db import get_db_context
from app.tasks.delivery_confirmation import send_pending_delivery_confirmations

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


def _run_delivery_confirmations():
    """Run delivery confirmation task."""
    try:
        with get_db_context() as db:
            send_pending_delivery_confirmations(db)
    except Exception as e:
        logger.error(f"Delivery confirmation task failed: {e}")


def start_scheduler():
    """Start the background scheduler."""
    scheduler.add_job(
        _run_delivery_confirmations,
        trigger=IntervalTrigger(minutes=30),
        id="delivery_confirmations",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    """Stop the scheduler."""
    scheduler.shutdown()
    logger.info("Scheduler stopped")
