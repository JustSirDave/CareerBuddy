"""
Tests for onboarding flow
"""
import pytest
from unittest.mock import patch

from app.models import User, Job
from app.flows import onboarding


class TestNewUserWelcome:
    def test_new_user_receives_welcome_message(self, db_session):
        user = User(telegram_user_id="999888777", telegram_username="newuser", onboarding_complete=False)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        result = onboarding.handle_new_user_welcome(db_session, user, "Alice")
        assert "Welcome to CareerBuddy" in result
        assert "Alice" in result
        db_session.refresh(user)
        assert user.onboarding_step == "awaiting_intent_response"
        assert user.onboarding_complete is False


class TestIntentDetection:
    @patch("app.flows.onboarding.ai.detect_onboarding_intent")
    def test_high_confidence_resume_intent_creates_job(self, mock_detect, db_session):
        mock_detect.return_value = {
            "intent": "resume",
            "confidence": "high",
            "extracted_role": "Data Analyst",
            "extracted_company": None
        }
        user = User(telegram_user_id="111222333", onboarding_complete=False, onboarding_step="awaiting_intent_response")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        result = onboarding.handle_onboarding_intent_response(
            db_session, user, "I need a new resume for a data analyst role", "111222333", "Bob"
        )
        assert "Let's build" in result or "Step 1" in result or "Basic" in result
        db_session.refresh(user)
        assert user.onboarding_complete is True
        assert user.onboarding_step is None
        job = db_session.query(Job).filter(Job.user_id == user.id).first()
        assert job is not None
        assert job.type == "resume"
        assert job.answers.get("target_role") == "Data Analyst"

    @patch("app.flows.onboarding.ai.detect_onboarding_intent")
    def test_low_confidence_intent_shows_soft_menu(self, mock_detect, db_session):
        mock_detect.return_value = {
            "intent": "unclear",
            "confidence": "low",
            "extracted_role": None,
            "extracted_company": None
        }
        user = User(telegram_user_id="777888999", onboarding_complete=False, onboarding_step="awaiting_intent_response")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        result = onboarding.handle_onboarding_intent_response(db_session, user, "I'm not sure", "777888999", "Dave")
        assert "__SHOW_DOCUMENT_MENU__|" in result
        db_session.refresh(user)
        assert user.onboarding_complete is True
        assert user.onboarding_step is None
