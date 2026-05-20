"""Tests for payments module (credit rules and helpers)."""
import pytest
from app.services import payments
from app.models import Job


class TestCreditRules:
    def test_free_user_can_generate_resume_once(self, db_session, test_user):
        assert payments.can_generate(test_user, "resume") is True

    def test_free_user_blocked_after_free_resume_used(self, db_session, test_user):
        test_user.free_resume_used = True
        test_user.document_credits = 0
        db_session.commit()
        assert payments.can_generate(test_user, "resume") is False

    def test_paid_credits_allow_resume(self, db_session, pro_user):
        assert payments.can_generate(pro_user, "resume") is True

    def test_get_purchase_prompt_for_resume(self):
        msg = payments.get_purchase_prompt("resume")
        assert "buy" in msg.lower() or "₦" in msg


class TestConsumeCredit:
    def test_consume_free_resume_marks_used(self, db_session, test_user):
        kind = payments.consume_credit(test_user, "resume", db_session)
        assert kind == "free"
        db_session.refresh(test_user)
        assert test_user.free_resume_used is True


class TestGenerationHistory:
    def test_count_jobs_by_role(self, db_session, test_user):
        role = "Software Engineer"
        for _ in range(3):
            db_session.add(
                Job(
                    user_id=test_user.id,
                    type="resume",
                    status="done",
                    answers={"target_role": role},
                )
            )
        db_session.commit()

        jobs = db_session.query(Job).filter(Job.user_id == test_user.id).all()
        n = sum(1 for j in jobs if (j.answers or {}).get("target_role") == role)
        assert n == 3


class TestPaymentValidation:
    def test_prices_positive(self):
        assert all(v > 0 for v in payments.PRICES.values())
