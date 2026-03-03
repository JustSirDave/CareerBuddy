"""
Referral service — code generation, signup tracking, conversion, credit issuance.
"""
import secrets
import string
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import Referral, User
from app.services.telegram import reply_text
from loguru import logger


def _generate_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_or_create_referral_code(user: User, db: Session) -> str:
    """Return existing referral code or create a new one."""
    existing = (
        db.query(Referral)
        .filter(Referral.referrer_id == user.id, Referral.referee_id.is_(None))
        .first()
    )
    if existing:
        return existing.code

    while True:
        code = _generate_code()
        clash = db.query(Referral).filter(Referral.code == code).first()
        if not clash:
            break

    referral = Referral(referrer_id=user.id, code=code)
    db.add(referral)
    db.commit()
    return code


def handle_referral_signup(new_user: User, ref_code: str, db: Session) -> None:
    """Link new user to referral on first /start with ref code."""
    referral = db.query(Referral).filter(Referral.code == ref_code).first()

    if not referral:
        logger.warning(f"Referral code not found: {ref_code}")
        return

    if str(referral.referrer_id) == str(new_user.id):
        logger.warning(f"Self-referral blocked: user {new_user.id}")
        return

    referral.referee_id = new_user.id
    new_user.referred_by_code = ref_code
    db.commit()
    logger.info(f"Referral signup linked: code={ref_code} referee={new_user.id}")


def get_completed_payment_count(user_id: str, db: Session) -> int:
    """Count user's successful payments (excluding waived)."""
    from app.models import Payment
    return (
        db.query(Payment)
        .filter(
            Payment.user_id == user_id,
            Payment.status.in_(["success", "successful"]),
        )
        .count()
    )


async def process_referral_conversion(user: User, db: Session) -> None:
    """
    Call when user completes first paid purchase.
    If they were referred, reward the referrer.
    """
    if not user.referred_by_code:
        return

    referral = (
        db.query(Referral)
        .filter(
            Referral.code == user.referred_by_code,
            Referral.status == "pending",
        )
        .first()
    )
    if not referral:
        return

    referral.status = "converted"
    referral.converted_at = datetime.utcnow()
    db.commit()

    await _issue_credit(referral, db)


async def _issue_credit(referral: Referral, db: Session) -> None:
    """Award credit to referrer and notify both parties."""
    referrer = db.query(User).filter(User.id == referral.referrer_id).first()
    referee = db.query(User).filter(User.id == referral.referee_id).first()

    if not referrer:
        return

    referrer.referral_credits = (referrer.referral_credits or 0) + 1
    referral.status = "rewarded"
    referral.rewarded_at = datetime.utcnow()
    db.commit()

    try:
        await reply_text(
            referrer.telegram_user_id,
            "Someone you referred just made their first purchase!\n\n"
            "You've earned *1 free document credit* 🎉\n\n"
            f"Your credits: *{referrer.referral_credits}*\n\n"
            "Credits apply automatically on your next document. "
            "Use /referral to share your link and earn more!",
        )
    except Exception as e:
        logger.error(f"Failed to notify referrer: {e}")

    if referee:
        try:
            await reply_text(
                referee.telegram_user_id,
                "A friend referred you to CareerBuddy — they just earned a free credit because of you! 🙌",
            )
        except Exception as e:
            logger.error(f"Failed to notify referee: {e}")


def apply_referral_credit(user: User, db: Session) -> bool:
    """
    Deduct 1 credit if available. Returns True if credit was applied.
    Call BEFORE initiating payment. If True, skip payment entirely.
    """
    credits = getattr(user, "referral_credits", 0) or 0
    if credits > 0:
        user.referral_credits = credits - 1
        db.commit()
        logger.info(f"Referral credit applied: user={user.id} remaining={user.referral_credits}")
        return True
    return False
