"""
CareerBuddy - Payment Service
Pay-per-document credit system with Paystack integration.
Author: Sir Dave
"""
import uuid
import httpx
from typing import Dict, Tuple
from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User, Payment


def _is_admin(user: User) -> bool:
    return user.telegram_user_id in settings.admin_telegram_ids


# ---------------------------------------------------------------------------
# Pricing (amounts in kobo — 100 kobo = ₦1)
# ---------------------------------------------------------------------------
PRICES = {
    "resume": 750_000,
    "cv": 750_000,
    "cover_letter": 300_000,
    "bundle": 1_500_000,
}

PRICE_DISPLAY = {
    "resume": "₦7,500",
    "cv": "₦7,500",
    "cover_letter": "₦3,000",
    "bundle": "₦15,000",
}

CREDIT_AWARDS = {
    "resume":       {"document_credits": 1, "cover_letter_credits": 0},
    "cv":           {"document_credits": 1, "cover_letter_credits": 0},
    "cover_letter": {"document_credits": 0, "cover_letter_credits": 1},
    "bundle":       {"document_credits": 2, "cover_letter_credits": 1},
}

VALID_PRODUCT_TYPES = set(PRICES.keys())


# ---------------------------------------------------------------------------
# Credit helpers
# ---------------------------------------------------------------------------

def can_generate_free(user: User, doc_type: str) -> bool:
    if _is_admin(user):
        return True
    if doc_type in ("resume", "cv"):
        return not getattr(user, "free_resume_used", False)
    if doc_type in ("cover_letter", "cover"):
        return not getattr(user, "free_cover_letter_used", False)
    return False


def has_paid_credit(user: User, doc_type: str) -> bool:
    if _is_admin(user):
        return True
    if doc_type in ("resume", "cv"):
        return (getattr(user, "document_credits", 0) or 0) > 0
    if doc_type in ("cover_letter", "cover"):
        return (getattr(user, "cover_letter_credits", 0) or 0) > 0
    return False


def can_generate(user: User, doc_type: str) -> bool:
    if _is_admin(user):
        return True
    return can_generate_free(user, doc_type) or has_paid_credit(user, doc_type)


def consume_credit(user: User, doc_type: str, db: Session) -> str:
    """
    Consume one credit for the given doc_type.
    Returns "free", "paid_credit", or "admin".
    Raises ValueError if no credit available.
    Free credits are consumed before paid credits.
    """
    if _is_admin(user):
        return "admin"

    if can_generate_free(user, doc_type):
        if doc_type in ("resume", "cv"):
            user.free_resume_used = True
        else:
            user.free_cover_letter_used = True
        db.commit()
        return "free"

    if has_paid_credit(user, doc_type):
        if doc_type in ("resume", "cv"):
            user.document_credits = (user.document_credits or 0) - 1
        else:
            user.cover_letter_credits = (user.cover_letter_credits or 0) - 1
        db.commit()
        return "paid_credit"

    raise ValueError(f"No credit available for {doc_type}")


def can_use_pdf(user: User, credit_type: str) -> bool:
    """PDF is available for paid credits and admins, not free credits."""
    if _is_admin(user):
        return True
    return credit_type in ("paid_credit", "admin")


def get_credit_summary(user: User) -> str:
    if _is_admin(user):
        return "👑 *Admin* — Unlimited access"
    lines = []
    if not getattr(user, "free_resume_used", False):
        lines.append("✓ 1 free resume/CV available")
    if not getattr(user, "free_cover_letter_used", False):
        lines.append("✓ 1 free cover letter available")
    doc_credits = getattr(user, "document_credits", 0) or 0
    cl_credits = getattr(user, "cover_letter_credits", 0) or 0
    ref_credits = getattr(user, "referral_credits", 0) or 0
    if doc_credits > 0:
        lines.append(f"📄 {doc_credits} document credit{'s' if doc_credits != 1 else ''}")
    if cl_credits > 0:
        lines.append(f"✉️ {cl_credits} cover letter credit{'s' if cl_credits != 1 else ''}")
    if ref_credits > 0:
        lines.append(f"🎁 {ref_credits} referral credit{'s' if ref_credits != 1 else ''}")
    return "\n".join(lines) if lines else "No credits remaining."


def get_purchase_prompt(doc_type: str) -> str:
    if doc_type in ("resume", "cv"):
        return (
            f"You've used your free {doc_type}.\n\n"
            f"*Single document* — {PRICE_DISPLAY['resume']}\n"
            f"*Bundle* (2 docs + 1 cover letter) — {PRICE_DISPLAY['bundle']} _save ₦3,000_\n\n"
            f"Type /buy\\_{doc_type} or /buy\\_bundle"
        )
    return (
        "You've used your free cover letter.\n\n"
        f"*Cover letter* — {PRICE_DISPLAY['cover_letter']}\n"
        f"*Bundle* (2 docs + 1 cover letter) — {PRICE_DISPLAY['bundle']} _save ₦3,000_\n\n"
        "Type /buy\\_cover\\_letter or /buy\\_bundle"
    )


# ---------------------------------------------------------------------------
# Paystack integration
# ---------------------------------------------------------------------------

async def initiate_payment(user: User, product_type: str, db: Session) -> Dict:
    """
    Create a Paystack payment link for a given product type.
    Saves a pending Payment record.
    Returns {"payment_url": str, "reference": str} or {"error": str}.
    """
    if product_type not in VALID_PRODUCT_TYPES:
        return {"error": f"Invalid product type: {product_type}"}
    if not settings.paystack_secret:
        logger.error("[payments] Paystack secret key not configured")
        return {"error": "payment_not_configured"}

    amount_kobo = PRICES[product_type]
    reference = f"cb_{product_type}_{user.id}_{uuid.uuid4().hex[:8]}"

    try:
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {settings.paystack_secret}",
            "Content-Type": "application/json",
        }
        payload = {
            "email": user.email or f"user_{user.telegram_user_id}@careerbuddy.temp",
            "amount": amount_kobo,
            "reference": reference,
            "metadata": {
                "user_id": user.id,
                "telegram_user_id": user.telegram_user_id,
                "product_type": product_type,
            },
            "callback_url": f"{settings.public_url}/webhooks/paystack",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code >= 400:
            logger.error(f"[payments] Paystack API error: {response.status_code} {response.text}")
            return {"error": "payment_api_failed"}

        data = response.json()
        if not data.get("status"):
            logger.error(f"[payments] Paystack returned error: {data.get('message')}")
            return {"error": "payment_creation_failed"}

        payment_data = data.get("data", {})

        payment = Payment(
            user_id=user.id,
            reference=reference,
            amount=amount_kobo,
            status="pending",
            product_type=product_type,
            payment_metadata={
                "user_id": user.id,
                "telegram_user_id": user.telegram_user_id,
                "product_type": product_type,
            },
        )
        db.add(payment)
        db.commit()

        logger.info(f"[payments] Payment initiated: {reference} ({product_type}) for user {user.id}")
        return {
            "payment_url": payment_data.get("authorization_url"),
            "reference": reference,
        }

    except Exception as e:
        logger.error(f"[payments] Exception creating payment link: {e}")
        return {"error": str(e)}


async def confirm_payment_and_award_credits(reference: str, db: Session):
    """
    Called from Paystack webhook on charge.success.
    1. Find Payment by reference
    2. Verify with Paystack API
    3. Mark payment confirmed
    4. Award credits
    Returns (user, product_type) on success, None otherwise.
    """
    payment = db.query(Payment).filter(Payment.reference == reference).first()
    if not payment:
        logger.warning(f"[payments] Payment not found for reference: {reference}")
        return None
    if payment.status in ("success", "confirmed"):
        logger.info(f"[payments] Payment {reference} already confirmed — idempotent skip")
        return None

    verification = await verify_payment(reference)
    if verification.get("error") or verification.get("status") != "success":
        logger.warning(f"[payments] Verification failed for {reference}: {verification}")
        return None

    payment.status = "success"
    payment.raw_webhook = verification
    db.commit()

    user = db.query(User).filter(User.id == payment.user_id).first()
    if not user:
        logger.error(f"[payments] User not found for payment {reference}")
        return None

    product_type = payment.product_type or "resume"
    awards = CREDIT_AWARDS.get(product_type, CREDIT_AWARDS["resume"])
    user.document_credits = (user.document_credits or 0) + awards["document_credits"]
    user.cover_letter_credits = (user.cover_letter_credits or 0) + awards["cover_letter_credits"]
    db.commit()

    logger.info(
        f"[payments] Credits awarded for {reference}: "
        f"doc={awards['document_credits']} cl={awards['cover_letter_credits']} "
        f"user={user.id}"
    )
    return (user, product_type)


async def verify_payment(reference: str) -> Dict:
    if not settings.paystack_secret:
        return {"error": "payment_not_configured"}
    try:
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {"Authorization": f"Bearer {settings.paystack_secret}"}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers)
        if response.status_code >= 400:
            return {"error": "verification_failed"}
        data = response.json()
        if data.get("status"):
            return data.get("data", {})
        return {"error": "verification_failed"}
    except Exception as e:
        logger.error(f"[payments] Exception verifying payment: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Record helpers (backward-compatible)
# ---------------------------------------------------------------------------

def record_payment(db: Session, user_id: str, reference: str, amount: int,
                   metadata: Dict, raw_payload: Dict | None = None,
                   product_type: str | None = None):
    try:
        payment = Payment(
            user_id=user_id,
            reference=reference,
            amount=amount,
            status="success",
            product_type=product_type or metadata.get("product_type"),
            payment_metadata=metadata or {},
            raw_webhook=raw_payload,
        )
        db.add(payment)
        db.commit()
        logger.info(f"[payments] Recorded payment: {reference} for user {user_id}")
    except Exception as e:
        logger.error(f"[payments] Failed to record payment: {e}")
        db.rollback()


def record_waived_payment(db: Session, user_id: str, purpose: str = "test",
                          reference: str | None = None):
    try:
        payment = Payment(
            user_id=user_id,
            reference=reference or f"waived-{user_id}-{uuid.uuid4().hex[:6]}",
            amount=0,
            status="waived",
            product_type=purpose,
            payment_metadata={"purpose": purpose, "note": "waived"},
            raw_webhook=None,
        )
        db.add(payment)
        db.commit()
        logger.info(f"[payments] Recorded waived payment for user {user_id}")
    except Exception as e:
        logger.error(f"[payments] Failed to record waived payment: {e}")
        db.rollback()
