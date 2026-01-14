"""
CareerBuddy - Payment Service
Payment and generation limit management service.
Author: Sir Dave
"""
import json
import httpx
from typing import Dict, Tuple
from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User, Payment


# Generation limits
FREE_TIER_LIMIT = 2  # Free users get 2 documents total
PAID_GENERATION_PRICE = 7500  # ₦7,500 per generation
MAX_GENERATIONS_PER_ROLE = 5  # Max 5 documents per role


def get_generation_counts(user: User) -> Dict[str, int]:
    """
    Parse user's generation_count JSON field.

    Returns:
        Dict mapping role names to generation counts
    """
    try:
        if isinstance(user.generation_count, str):
            return json.loads(user.generation_count)
        return user.generation_count or {}
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"[payments] Invalid generation_count for user {user.id}, resetting")
        return {}


def update_generation_count(db: Session, user: User, role: str):
    """
    Increment generation count for a specific role.

    Args:
        db: Database session
        user: User model
        role: Target role name
    """
    counts = get_generation_counts(user)
    counts[role] = counts.get(role, 0) + 1
    user.generation_count = json.dumps(counts)
    db.commit()
    logger.info(f"[payments] Updated generation count for user {user.id}, role '{role}': {counts[role]}")


def get_total_generations(user: User) -> int:
    """Get total number of generations across all roles."""
    counts = get_generation_counts(user)
    return sum(counts.values())


def can_generate(user: User, role: str) -> Tuple[bool, str]:
    """
    Check if user can generate a document for the given role.

    Args:
        user: User model
        role: Target role name

    Returns:
        Tuple of (can_generate: bool, reason: str)
    """
    counts = get_generation_counts(user)
    role_count = counts.get(role, 0)
    total_count = sum(counts.values())

    # Check per-role limit (applies to all users)
    if role_count >= MAX_GENERATIONS_PER_ROLE:
        return False, f"max_per_role|{role}"

    # Check free tier limit
    if user.tier == "free":
        if total_count >= FREE_TIER_LIMIT:
            return False, "free_limit_reached"
        return True, ""

    # Pro tier users can generate (they pay per generation)
    return True, ""


async def create_payment_link(user: User, role: str, amount: int = PAID_GENERATION_PRICE) -> Dict:
    """
    Create a Paystack payment link for document generation.

    Args:
        user: User model
        role: Target role for generation
        amount: Amount in Naira (kobo will be calculated)

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
        amount_kobo = amount * 100

        payload = {
            "email": user.email or f"user_{user.telegram_user_id}@careerbuddy.temp",
            "amount": amount_kobo,
            "metadata": {
                "user_id": user.id,
                "telegram_user_id": user.telegram_user_id,
                "role": role,
                "purpose": "document_generation"
            },
            # route lives under /webhooks/paystack
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
                logger.info(f"[payments] Payment link created for user {user.id}: {payment_data.get('reference')}")
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


def record_payment(db: Session, user_id: str, reference: str, amount: int, metadata: Dict, raw_payload: Dict | None = None):
    """
    Record a successful payment in the database.

    Args:
        db: Database session
        user_id: User ID
        reference: Payment reference
        amount: Amount paid (in kobo)
        metadata: Payment metadata
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


def record_waived_payment(db: Session, user_id: str, role: str, reference: str | None = None):
    """
    Record a waived (no-charge) payment placeholder while gateway is bypassed.
    """
    try:
        payment = Payment(
            user_id=user_id,
            reference=reference or f"waived-{user_id}",
            amount=0,
            status="waived",
            payment_metadata={"role": role, "note": "waived"},
            raw_webhook=None,
        )
        db.add(payment)
        db.commit()
        logger.info(f"[payments] Recorded waived payment for user {user_id}, role={role}")
    except Exception as e:
        logger.error(f"[payments] Failed to record waived payment: {e}")
        db.rollback()
