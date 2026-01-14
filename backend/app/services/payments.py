"""
CareerBuddy - Payment Service
Payment and quota management service with monthly resets.
Author: Sir Dave
"""
import json
import httpx
from datetime import datetime, timedelta
from typing import Dict, Tuple, Literal
from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User, Payment


def _is_admin(user: User) -> bool:
    """
    Check if user is an admin.
    
    Args:
        user: User model
        
    Returns:
        True if user is admin, False otherwise
    """
    return user.telegram_user_id in settings.admin_telegram_ids


# Document type definitions
DocumentType = Literal["resume", "cv", "cover_letter", "revamp"]

# Pricing
PREMIUM_PACKAGE_PRICE = 7500  # ₦7,500 per month

# Quota limits by tier and document type
QUOTA_LIMITS = {
    "free": {
        "resume": 1,
        "cv": 1,
        "cover_letter": 0,  # Not allowed
        "revamp": 1,
        "pdf_allowed": False,
    },
    "pro": {
        "resume": 2,
        "cv": 2,
        "cover_letter": 1,
        "revamp": 1,
        "pdf_allowed": True,
    }
}


def get_document_counts(user: User) -> Dict[str, int]:
    """
    Parse user's generation_count JSON field.

    Returns:
        Dict mapping document types to generation counts
        Example: {"resume": 1, "cv": 0, "cover_letter": 1, "revamp": 0}
    """
    try:
        if isinstance(user.generation_count, str):
            counts = json.loads(user.generation_count)
        else:
            counts = user.generation_count or {}
        
        # Ensure all document types are present
        for doc_type in ["resume", "cv", "cover_letter", "revamp"]:
            if doc_type not in counts:
                counts[doc_type] = 0
        
        return counts
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"[payments] Invalid generation_count for user {user.id}, resetting")
        return {"resume": 0, "cv": 0, "cover_letter": 0, "revamp": 0}


def check_and_reset_quota(db: Session, user: User) -> bool:
    """
    Check if user's quota needs to be reset (monthly).
    
    Args:
        db: Database session
        user: User model
        
    Returns:
        True if quota was reset, False otherwise
    """
    # Admin users don't need quota resets
    if _is_admin(user):
        return False
    
    now = datetime.utcnow()
    
    # Initialize quota_reset_at if not set
    if not user.quota_reset_at:
        user.quota_reset_at = now + timedelta(days=30)
        db.commit()
        logger.info(f"[payments] Initialized quota_reset_at for user {user.id}")
        return False
    
    # Check if reset is due
    if now >= user.quota_reset_at:
        # Reset quota
        user.generation_count = json.dumps({"resume": 0, "cv": 0, "cover_letter": 0, "revamp": 0})
        user.quota_reset_at = now + timedelta(days=30)
        db.commit()
        logger.info(f"[payments] Reset quota for user {user.id}, next reset: {user.quota_reset_at}")
        return True
    
    return False


def check_premium_expiry(db: Session, user: User) -> bool:
    """
    Check if user's premium has expired and downgrade if necessary.
    
    Args:
        db: Database session
        user: User model
        
    Returns:
        True if user was downgraded, False otherwise
    """
    # Admin users never get downgraded
    if _is_admin(user):
        return False
    
    now = datetime.utcnow()
    
    # If user is pro but premium has expired
    if user.tier == "pro" and user.premium_expires_at and now >= user.premium_expires_at:
        user.tier = "free"
        db.commit()
        logger.info(f"[payments] Premium expired for user {user.id}, downgraded to free")
        return True
    
    return False


def can_generate_document(user: User, doc_type: DocumentType) -> Tuple[bool, str]:
    """
    Check if user can generate a document of the given type.

    Args:
        user: User model
        doc_type: Document type (resume, cv, cover_letter, revamp)

    Returns:
        Tuple of (can_generate: bool, reason: str)
    """
    # Admin users have unlimited access
    if _is_admin(user):
        return True, ""
    
    # Get current counts
    counts = get_document_counts(user)
    current_count = counts.get(doc_type, 0)
    
    # Get limit for this tier and document type
    tier_limits = QUOTA_LIMITS.get(user.tier, QUOTA_LIMITS["free"])
    limit = tier_limits.get(doc_type, 0)
    
    # Check if document type is allowed
    if limit == 0:
        return False, f"document_not_allowed|{doc_type}"
    
    # Check if quota exceeded
    if current_count >= limit:
        return False, f"quota_exceeded|{doc_type}|{limit}"
    
    return True, ""


def can_use_pdf(user: User) -> bool:
    """
    Check if user can request PDF format.
    
    Args:
        user: User model
        
    Returns:
        True if PDF is allowed, False otherwise
    """
    # Admin users can always use PDF
    if _is_admin(user):
        return True
    
    tier_limits = QUOTA_LIMITS.get(user.tier, QUOTA_LIMITS["free"])
    return tier_limits.get("pdf_allowed", False)


def update_document_count(db: Session, user: User, doc_type: DocumentType):
    """
    Increment generation count for a specific document type.

    Args:
        db: Database session
        user: User model
        doc_type: Document type
    """
    # Don't track quota for admin users
    if _is_admin(user):
        logger.info(f"[payments] Admin user {user.id} - quota tracking skipped")
        return
    
    counts = get_document_counts(user)
    counts[doc_type] = counts.get(doc_type, 0) + 1
    user.generation_count = json.dumps(counts)
    db.commit()
    logger.info(f"[payments] Updated {doc_type} count for user {user.id}: {counts[doc_type]}")


def get_quota_status(user: User) -> Dict[str, any]:
    """
    Get user's current quota status.
    
    Args:
        user: User model
        
    Returns:
        Dict with quota information
    """
    # Admin users have unlimited quota
    if _is_admin(user):
        return {
            "tier": "admin",
            "resume": {
                "used": 0,
                "limit": "∞",
                "remaining": "∞"
            },
            "cv": {
                "used": 0,
                "limit": "∞",
                "remaining": "∞"
            },
            "cover_letter": {
                "used": 0,
                "limit": "∞",
                "remaining": "∞"
            },
            "revamp": {
                "used": 0,
                "limit": "∞",
                "remaining": "∞"
            },
            "pdf_allowed": True,
            "quota_resets_at": None,
            "premium_expires_at": None,
        }
    
    counts = get_document_counts(user)
    tier_limits = QUOTA_LIMITS.get(user.tier, QUOTA_LIMITS["free"])
    
    return {
        "tier": user.tier,
        "resume": {
            "used": counts["resume"],
            "limit": tier_limits["resume"],
            "remaining": tier_limits["resume"] - counts["resume"]
        },
        "cv": {
            "used": counts["cv"],
            "limit": tier_limits["cv"],
            "remaining": tier_limits["cv"] - counts["cv"]
        },
        "cover_letter": {
            "used": counts["cover_letter"],
            "limit": tier_limits["cover_letter"],
            "remaining": tier_limits["cover_letter"] - counts["cover_letter"]
        },
        "revamp": {
            "used": counts["revamp"],
            "limit": tier_limits["revamp"],
            "remaining": tier_limits["revamp"] - counts["revamp"]
        },
        "pdf_allowed": tier_limits["pdf_allowed"],
        "quota_resets_at": user.quota_reset_at.isoformat() if user.quota_reset_at else None,
        "premium_expires_at": user.premium_expires_at.isoformat() if user.premium_expires_at else None,
    }


async def create_premium_payment_link(user: User) -> Dict:
    """
    Create a Paystack payment link for premium package purchase.

    Args:
        user: User model

    Returns:
        Dict with payment link details or error
    """
    if not settings.paystack_secret:
        logger.error("[payments] Paystack secret key not configured")
        return {"error": "payment_not_configured"}

    try:
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {settings.paystack_secret}",
            "Content-Type": "application/json"
        }

        # Paystack expects amount in kobo (1 Naira = 100 kobo)
        amount_kobo = PREMIUM_PACKAGE_PRICE * 100

        payload = {
            "email": user.email or f"user_{user.telegram_user_id}@careerbuddy.temp",
            "amount": amount_kobo,
            "metadata": {
                "user_id": user.id,
                "telegram_user_id": user.telegram_user_id,
                "purpose": "premium_package",
                "package": "monthly"
            },
            "callback_url": f"{settings.public_url}/webhooks/paystack"
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code >= 400:
                logger.error(f"[payments] Paystack API error: {response.status_code} {response.text}")
                return {"error": "payment_api_failed"}

            data = response.json()

            if data.get("status"):
                payment_data = data.get("data", {})
                logger.info(f"[payments] Premium payment link created for user {user.id}: {payment_data.get('reference')}")
                return {
                    "authorization_url": payment_data.get("authorization_url"),
                    "access_code": payment_data.get("access_code"),
                    "reference": payment_data.get("reference")
                }
            else:
                logger.error(f"[payments] Paystack returned error: {data.get('message')}")
                return {"error": "payment_creation_failed"}

    except Exception as e:
        logger.error(f"[payments] Exception creating payment link: {e}")
        return {"error": str(e)}


async def verify_payment(reference: str) -> Dict:
    """
    Verify a Paystack payment reference.

    Args:
        reference: Paystack payment reference

    Returns:
        Dict with verification status and metadata
    """
    if not settings.paystack_secret:
        logger.error("[payments] Paystack secret key not configured")
        return {"error": "payment_not_configured"}

    try:
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {
            "Authorization": f"Bearer {settings.paystack_secret}"
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers)

            if response.status_code >= 400:
                logger.error(f"[payments] Paystack verification error: {response.status_code}")
                return {"error": "verification_failed"}

            data = response.json()

            if data.get("status"):
                return data.get("data", {})
            else:
                logger.error(f"[payments] Verification returned error: {data.get('message')}")
                return {"error": "verification_failed"}

    except Exception as e:
        logger.error(f"[payments] Exception verifying payment: {e}")
        return {"error": str(e)}


def upgrade_to_premium(db: Session, user: User) -> bool:
    """
    Upgrade user to premium tier.
    
    Args:
        db: Database session
        user: User model
        
    Returns:
        True if successful, False otherwise
    """
    try:
        now = datetime.utcnow()
        user.tier = "pro"
        user.premium_expires_at = now + timedelta(days=30)  # 30 days from now
        
        # Reset quota to premium limits
        user.generation_count = json.dumps({"resume": 0, "cv": 0, "cover_letter": 0, "revamp": 0})
        user.quota_reset_at = now + timedelta(days=30)
        
        db.commit()
        logger.info(f"[payments] Upgraded user {user.id} to premium, expires: {user.premium_expires_at}")
        return True
    except Exception as e:
        logger.error(f"[payments] Failed to upgrade user {user.id}: {e}")
        db.rollback()
        return False


def record_payment(db: Session, user_id: str, reference: str, amount: int, metadata: Dict, raw_payload: Dict | None = None):
    """
    Record a successful payment in the database.

    Args:
        db: Database session
        user_id: User ID
        reference: Payment reference
        amount: Amount paid (in kobo)
        metadata: Payment metadata
        raw_payload: Raw webhook payload
    """
    try:
        payment = Payment(
            user_id=user_id,
            reference=reference,
            amount=amount / 100,  # Convert kobo to Naira
            status="success",
            payment_metadata=metadata or {},
            raw_webhook=raw_payload,
        )
        db.add(payment)
        db.commit()
        logger.info(f"[payments] Recorded payment: {reference} for user {user_id}")
    except Exception as e:
        logger.error(f"[payments] Failed to record payment: {e}")
        db.rollback()


def record_waived_payment(db: Session, user_id: str, purpose: str = "test", reference: str | None = None):
    """
    Record a waived (no-charge) payment placeholder for testing.
    
    Args:
        db: Database session
        user_id: User ID
        purpose: Purpose of the payment (premium_package, test, etc.)
        reference: Optional reference
    """
    try:
        payment = Payment(
            user_id=user_id,
            reference=reference or f"waived-{user_id}",
            amount=0,
            status="waived",
            payment_metadata={"purpose": purpose, "note": "waived for testing"},
            raw_webhook=None,
        )
        db.add(payment)
        db.commit()
        logger.info(f"[payments] Recorded waived payment for user {user_id}, purpose={purpose}")
    except Exception as e:
        logger.error(f"[payments] Failed to record waived payment: {e}")
        db.rollback()
