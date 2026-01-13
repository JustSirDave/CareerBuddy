"""
Document history service
Track and retrieve user's document generation history
"""
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models import Job, User
from datetime import datetime
from typing import List, Dict
from loguru import logger


def get_user_document_history(db: Session, user_id: str, limit: int = 10) -> List[Dict]:
    """
    Get user's document generation history
    
    Args:
        db: Database session
        user_id: User ID
        limit: Maximum number of documents to return
    
    Returns:
        List of document metadata dictionaries
    """
    try:
        jobs = db.query(Job).filter(
            Job.user_id == user_id,
            Job.status.in_(["completed", "preview_ready"])
        ).order_by(desc(Job.created_at)).limit(limit).all()
        
        history = []
        for job in jobs:
            answers = job.answers or {}
            basics = answers.get('basics', {})
            
            # Map job types to display names
            doc_type_map = {
                'resume': 'Resume',
                'cv': 'CV',
                'cover': 'Cover Letter',
                'revamp': 'Revamp'
            }
            
            doc_info = {
                'id': job.id,
                'type': doc_type_map.get(job.type, job.type.capitalize()),
                'name': basics.get('name', 'Unnamed Document'),
                'target_role': answers.get('target_role', 'N/A'),
                'template': answers.get('template', 'template_1'),
                'created_at': job.created_at.strftime('%Y-%m-%d %H:%M') if job.created_at else 'N/A',
                'status': job.status,
                'file_path': job.file_path or job.draft_text
            }
            
            history.append(doc_info)
        
        logger.info(f"[HISTORY] Retrieved {len(history)} documents for user {user_id}")
        return history
    
    except Exception as e:
        logger.error(f"[HISTORY] Error fetching history for user {user_id}: {e}")
        return []


def get_document_by_id(db: Session, job_id: str, user_id: str) -> Dict | None:
    """
    Get a specific document by job ID
    
    Args:
        db: Database session
        job_id: Job ID
        user_id: User ID (for authorization)
    
    Returns:
        Document metadata or None if not found/unauthorized
    """
    try:
        job = db.query(Job).filter(
            Job.id == job_id,
            Job.user_id == user_id
        ).first()
        
        if not job:
            logger.warning(f"[HISTORY] Document {job_id} not found for user {user_id}")
            return None
        
        answers = job.answers or {}
        basics = answers.get('basics', {})
        
        return {
            'id': job.id,
            'type': job.type,
            'name': basics.get('name', 'Unnamed Document'),
            'created_at': job.created_at,
            'status': job.status,
            'file_path': job.file_path or job.draft_text,
            'answers': answers
        }
    
    except Exception as e:
        logger.error(f"[HISTORY] Error fetching document {job_id}: {e}")
        return None


def count_user_documents(db: Session, user_id: str) -> Dict[str, int]:
    """
    Count user's documents by type
    
    Args:
        db: Database session
        user_id: User ID
    
    Returns:
        Dictionary with document counts by type
    """
    try:
        total = db.query(Job).filter(
            Job.user_id == user_id,
            Job.status.in_(["completed", "preview_ready"])
        ).count()
        
        resumes = db.query(Job).filter(
            Job.user_id == user_id,
            Job.type == "resume",
            Job.status.in_(["completed", "preview_ready"])
        ).count()
        
        cvs = db.query(Job).filter(
            Job.user_id == user_id,
            Job.type == "cv",
            Job.status.in_(["completed", "preview_ready"])
        ).count()
        
        cover_letters = db.query(Job).filter(
            Job.user_id == user_id,
            Job.type == "cover",
            Job.status.in_(["completed", "preview_ready"])
        ).count()
        
        revamps = db.query(Job).filter(
            Job.user_id == user_id,
            Job.type == "revamp",
            Job.status.in_(["completed", "preview_ready"])
        ).count()
        
        return {
            'total': total,
            'resumes': resumes,
            'cvs': cvs,
            'cover_letters': cover_letters,
            'revamps': revamps
        }
    
    except Exception as e:
        logger.error(f"[HISTORY] Error counting documents for user {user_id}: {e}")
        return {
            'total': 0,
            'resumes': 0,
            'cvs': 0,
            'cover_letters': 0,
            'revamps': 0
        }
