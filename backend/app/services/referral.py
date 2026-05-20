# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Xenaptis Technologies
"""Referral service — code generation and signup tracking."""
import secrets
import string

from loguru import logger
from sqlalchemy.orm import Session

from app.models import Referral, User


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
        if not db.query(Referral).filter(Referral.code == code).first():
            break

    referral = Referral(referrer_id=user.id, code=code)
    db.add(referral)
    db.commit()
    return code


def handle_referral_signup(new_user: User, ref_code: str, db: Session) -> None:
    """Link new user to referral row on first /start with ref code."""
    referral = db.query(Referral).filter(Referral.code == ref_code).first()

    if not referral:
        logger.warning(f"Referral code not found: {ref_code}")
        return

    if str(referral.referrer_id) == str(new_user.id):
        logger.warning(f"Self-referral blocked: user {new_user.id}")
        return

    referral.referee_id = new_user.id
    db.commit()
    logger.info(f"Referral signup linked: code={ref_code} referee={new_user.id}")
