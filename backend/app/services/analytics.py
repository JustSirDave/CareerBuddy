# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Xenaptis Technologies
"""Analytics service for admin dashboard."""
from datetime import datetime, timedelta
from typing import Dict

from loguru import logger
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.models import Job, User, Message


def get_system_analytics(db: Session, days: int = 7) -> Dict:
    try:
        cutoff_date = datetime.now() - timedelta(days=days)

        total_users = db.query(User).count()
        new_users = db.query(User).filter(User.created_at >= cutoff_date).count()
        active_this_month = db.query(User).filter(User.monthly_doc_count > 0).count()
        active_users = (
            db.query(func.count(func.distinct(Job.user_id)))
            .filter(Job.created_at >= cutoff_date, Job.status.in_(["completed", "preview_ready"]))
            .scalar() or 0
        )

        total_documents = db.query(Job).filter(Job.status.in_(["completed", "preview_ready"])).count()
        recent_documents = db.query(Job).filter(
            Job.status.in_(["completed", "preview_ready"]),
            Job.created_at >= cutoff_date,
        ).count()

        resumes = db.query(Job).filter(Job.type == "resume", Job.status.in_(["completed", "preview_ready"])).count()
        cvs = db.query(Job).filter(Job.type == "cv", Job.status.in_(["completed", "preview_ready"])).count()
        cover_letters = db.query(Job).filter(Job.type == "cover", Job.status.in_(["completed", "preview_ready"])).count()
        revamps = db.query(Job).filter(Job.type == "revamp", Job.status.in_(["completed", "preview_ready"])).count()

        total_messages = db.query(Message).count()
        recent_messages = db.query(Message).filter(Message.created_at >= cutoff_date).count()

        top_users = (
            db.query(User.telegram_username, User.name, func.count(Job.id).label("doc_count"))
            .join(Job, User.id == Job.user_id)
            .filter(Job.status.in_(["completed", "preview_ready"]))
            .group_by(User.id)
            .order_by(desc("doc_count"))
            .limit(5)
            .all()
        )

        logger.info(f"[ANALYTICS] Generated system analytics for last {days} days")
        return {
            "period_days": days,
            "users": {
                "total": total_users,
                "new": new_users,
                "active": active_users,
                "active_this_month": active_this_month,
            },
            "documents": {
                "total": total_documents,
                "recent": recent_documents,
                "resumes": resumes,
                "cvs": cvs,
                "cover_letters": cover_letters,
                "revamps": revamps,
                "avg_per_user": round(total_documents / total_users, 2) if total_users > 0 else 0,
            },
            "engagement": {
                "total_messages": total_messages,
                "recent_messages": recent_messages,
                "avg_messages_per_user": round(total_messages / total_users, 2) if total_users > 0 else 0,
            },
            "top_users": [
                {"username": u.telegram_username or u.name or "Unknown", "documents": u.doc_count}
                for u in top_users
            ],
        }

    except Exception as e:
        logger.error(f"[ANALYTICS] Error generating analytics: {e}")
        return {
            "error": str(e),
            "users": {"total": 0},
            "documents": {"total": 0},
            "engagement": {"total_messages": 0},
        }


def get_growth_metrics(db: Session, days: int = 30) -> Dict:
    try:
        metrics = []
        for day_offset in range(days, -1, -1):
            date = datetime.now() - timedelta(days=day_offset)
            date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            date_end = date_start + timedelta(days=1)

            new_users = db.query(User).filter(
                User.created_at >= date_start, User.created_at < date_end
            ).count()
            new_documents = db.query(Job).filter(
                Job.created_at >= date_start,
                Job.created_at < date_end,
                Job.status.in_(["completed", "preview_ready"]),
            ).count()

            metrics.append({
                "date": date_start.strftime("%Y-%m-%d"),
                "new_users": new_users,
                "new_documents": new_documents,
            })

        return {"period_days": days, "daily_metrics": metrics}

    except Exception as e:
        logger.error(f"[ANALYTICS] Error generating growth metrics: {e}")
        return {"error": str(e), "daily_metrics": []}
