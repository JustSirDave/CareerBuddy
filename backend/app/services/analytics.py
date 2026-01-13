"""
Analytics service for admin dashboard
Track system-wide statistics and metrics
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta
from typing import Dict, List
from loguru import logger

# Import models - Payment may not exist yet
try:
    from app.models import Job, User, Payment, Message
except ImportError:
    from app.models import Job, User, Message
    Payment = None


def get_system_analytics(db: Session, days: int = 7) -> Dict:
    """
    Get system-wide analytics for admin dashboard
    
    Args:
        db: Database session
        days: Number of days to look back
    
    Returns:
        Dictionary with comprehensive system statistics
    """
    try:
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # User statistics
        total_users = db.query(User).count()
        new_users = db.query(User).filter(User.created_at >= cutoff_date).count()
        premium_users = db.query(User).filter(User.tier == "pro").count()
        free_users = total_users - premium_users
        
        # Document statistics
        total_documents = db.query(Job).filter(
            Job.status.in_(["completed", "preview_ready"])
        ).count()
        recent_documents = db.query(Job).filter(
            Job.status.in_(["completed", "preview_ready"]),
            Job.created_at >= cutoff_date
        ).count()
        
        # Documents by type
        resumes = db.query(Job).filter(
            Job.type == "resume",
            Job.status.in_(["completed", "preview_ready"])
        ).count()
        
        cvs = db.query(Job).filter(
            Job.type == "cv",
            Job.status.in_(["completed", "preview_ready"])
        ).count()
        
        cover_letters = db.query(Job).filter(
            Job.type == "cover",
            Job.status.in_(["completed", "preview_ready"])
        ).count()
        
        revamps = db.query(Job).filter(
            Job.type == "revamp",
            Job.status.in_(["completed", "preview_ready"])
        ).count()
        
        # Payment statistics (optional - table may not exist)
        if Payment is not None:
            try:
                total_payments = db.query(Payment).filter(
                    Payment.status.in_(["successful", "waived"])
                ).count()
                
                total_revenue = db.query(func.sum(Payment.amount)).filter(
                    Payment.status == "successful"
                ).scalar() or 0
            except Exception as e:
                logger.warning(f"[ANALYTICS] Payment table query failed: {e}")
                db.rollback()  # Rollback the failed transaction
                total_payments = 0
                total_revenue = 0
        else:
            logger.info("[ANALYTICS] Payment model not available, skipping payment stats")
            total_payments = 0
            total_revenue = 0
        
        # Message statistics
        total_messages = db.query(Message).count()
        recent_messages = db.query(Message).filter(
            Message.created_at >= cutoff_date
        ).count()
        
        # Top users by document count
        top_users = db.query(
            User.telegram_username,
            User.name,
            User.tier,
            func.count(Job.id).label('doc_count')
        ).join(Job, User.id == Job.user_id).filter(
            Job.status.in_(["completed", "preview_ready"])
        ).group_by(User.id).order_by(desc('doc_count')).limit(5).all()
        
        # Active users (users who created documents recently)
        active_users = db.query(func.count(func.distinct(Job.user_id))).filter(
            Job.created_at >= cutoff_date,
            Job.status.in_(["completed", "preview_ready"])
        ).scalar() or 0
        
        analytics = {
            'period_days': days,
            'users': {
                'total': total_users,
                'new': new_users,
                'premium': premium_users,
                'free': free_users,
                'active': active_users,
                'premium_percentage': round((premium_users / total_users * 100) if total_users > 0 else 0, 2)
            },
            'documents': {
                'total': total_documents,
                'recent': recent_documents,
                'resumes': resumes,
                'cvs': cvs,
                'cover_letters': cover_letters,
                'revamps': revamps,
                'avg_per_user': round(total_documents / total_users, 2) if total_users > 0 else 0
            },
            'payments': {
                'total_transactions': total_payments,
                'total_revenue': total_revenue,
                'avg_transaction': round(total_revenue / total_payments, 2) if total_payments > 0 else 0
            },
            'engagement': {
                'total_messages': total_messages,
                'recent_messages': recent_messages,
                'avg_messages_per_user': round(total_messages / total_users, 2) if total_users > 0 else 0
            },
            'top_users': [
                {
                    'username': user.telegram_username or user.name or 'Unknown',
                    'tier': user.tier,
                    'documents': user.doc_count
                }
                for user in top_users
            ]
        }
        
        logger.info(f"[ANALYTICS] Generated system analytics for last {days} days")
        return analytics
    
    except Exception as e:
        logger.error(f"[ANALYTICS] Error generating analytics: {e}")
        return {
            'error': str(e),
            'users': {'total': 0},
            'documents': {'total': 0},
            'payments': {'total_transactions': 0},
            'engagement': {'total_messages': 0}
        }


def get_growth_metrics(db: Session, days: int = 30) -> Dict:
    """
    Get growth metrics over time
    
    Args:
        db: Database session
        days: Number of days to analyze
    
    Returns:
        Daily growth metrics
    """
    try:
        metrics = []
        for day_offset in range(days, -1, -1):
            date = datetime.now() - timedelta(days=day_offset)
            date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            date_end = date_start + timedelta(days=1)
            
            new_users = db.query(User).filter(
                User.created_at >= date_start,
                User.created_at < date_end
            ).count()
            
            new_documents = db.query(Job).filter(
                Job.created_at >= date_start,
                Job.created_at < date_end,
                Job.status.in_(["completed", "preview_ready"])
            ).count()
            
            metrics.append({
                'date': date_start.strftime('%Y-%m-%d'),
                'new_users': new_users,
                'new_documents': new_documents
            })
        
        return {
            'period_days': days,
            'daily_metrics': metrics
        }
    
    except Exception as e:
        logger.error(f"[ANALYTICS] Error generating growth metrics: {e}")
        return {'error': str(e), 'daily_metrics': []}
