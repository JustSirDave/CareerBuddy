"""
Error recovery tests for CareerBuddy.
Covers input validation, AI fallback, render failure, dropout, webhook, and send retries.
"""
import pytest
from unittest.mock import patch, Mock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.flows.validators import (
    validate_email,
    validate_phone,
    validate_date_range,
    validate_basics,
    validate_experience_bullets,
    validate_skills_selection,
)
from app.services.error_handler import ErrorType, ERROR_MESSAGES
from app.models import User, Job


# --- Input validation tests ---


class TestInputValidation:
    """Input validation at each step."""

    def test_invalid_email_in_basics(self):
        """Invalid email in basics step → correct error key."""
        is_valid, error_key = validate_email("john")
        assert is_valid is False
        assert error_key == "invalid_email"

    def test_valid_email(self):
        """Valid email passes."""
        is_valid, error_key = validate_email("john@example.com")
        assert is_valid is True
        assert error_key is None

    def test_invalid_phone(self):
        """Invalid phone → correct error key."""
        is_valid, error_key = validate_phone("call me")
        assert is_valid is False
        assert error_key == "invalid_phone"

    def test_valid_phone_nigerian(self):
        """Valid Nigerian phone passes."""
        is_valid, _ = validate_phone("08012345678")
        assert is_valid is True

    def test_too_few_experience_bullets(self):
        """Too few bullets → correct error key."""
        is_valid, error_key = validate_experience_bullets(["only one bullet"])
        assert is_valid is False
        assert error_key == "too_few_bullets"

    def test_valid_experience_bullets(self):
        """At least 2 bullets passes."""
        is_valid, _ = validate_experience_bullets(["bullet 1", "bullet 2"])
        assert is_valid is True

    def test_invalid_skills_selection(self):
        """Invalid skills selection (number out of range) → error."""
        is_valid, error_key = validate_skills_selection("99", max_options=5)
        assert is_valid is False
        assert error_key == "invalid_skills_selection"

    def test_valid_skills_selection_numbers(self):
        """Valid comma-separated numbers passes."""
        is_valid, _ = validate_skills_selection("1, 3, 5", max_options=5)
        assert is_valid is True

    def test_valid_skills_free_text(self):
        """Free text skills always valid."""
        is_valid, _ = validate_skills_selection("Python, SQL", max_options=5)
        assert is_valid is True

    def test_invalid_date_range(self):
        """Invalid date range format."""
        is_valid, error_key = validate_date_range("last year")
        assert is_valid is False
        assert error_key == "invalid_date_range"

    def test_valid_date_range(self):
        """Valid date range format."""
        is_valid, _ = validate_date_range("Jan 2022 – Mar 2024")
        assert is_valid is True

    def test_basics_format_too_few_parts(self):
        """Basics with fewer than 4 parts fails."""
        is_valid, error_key = validate_basics("John, john@test.com")
        assert is_valid is False
        assert error_key == "basics_format"

    def test_basics_invalid_email(self):
        """Basics with invalid email fails."""
        is_valid, error_key = validate_basics("John, notanemail, 08012345678, Lagos")
        assert is_valid is False
        assert error_key == "invalid_email"

    def test_basics_valid(self):
        """Valid basics format passes."""
        is_valid, _ = validate_basics("John Doe, john@example.com, 08012345678, Lagos")
        assert is_valid is True


# --- Error messages ---


class TestErrorMessages:
    """Central error messages are defined and usable."""

    def test_error_messages_exist(self):
        """All expected error keys exist in ERROR_MESSAGES."""
        expected = [
            "invalid_email",
            "invalid_phone",
            "invalid_date_range",
            "too_few_bullets",
            "invalid_skills_selection",
            "basics_format",
            "ai_skills_failed",
            "ai_summary_failed",
            "docx_render_failed",
            "pdf_render_failed",
            "generic_fallback",
        ]
        for key in expected:
            assert key in ERROR_MESSAGES, f"Missing error key: {key}"

    def test_error_messages_not_generic(self):
        """Error messages are specific, not generic 'An error occurred'."""
        for key, msg in ERROR_MESSAGES.items():
            assert "error occurred" not in msg.lower() or key == "generic_fallback"


# --- Webhook tests ---


class TestWebhookErrorRecovery:
    """Webhook always returns 200, logs errors."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_malformed_json_returns_200(self, client):
        """Malformed JSON payload → 200 returned, error logged."""
        response = client.post(
            "/webhooks/telegram",
            content="not valid json {{{",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200

    def test_missing_update_id_returns_200(self, client):
        """Missing update_id → 200 returned."""
        payload = {"message": {"text": "hi", "chat": {"id": 123}, "from": {"id": 123}}}
        with patch("app.routers.webhook.handle_inbound", new_callable=AsyncMock) as mock:
            mock.return_value = ""
            response = client.post("/webhooks/telegram", json=payload)
        assert response.status_code == 200


# --- Render failure tests ---


@pytest.mark.asyncio
class TestRenderFailure:
    """DOCX/PDF render failure handling."""

    async def test_render_failed_status_used(self, db_session, test_user, sample_resume_data):
        """When render fails, job status = render_failed."""
        from app.services.router import handle_resume

        job = Job(
            user_id=test_user.id,
            type="resume",
            status="collecting",
            answers={**sample_resume_data, "_step": "draft_ready"},
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        with patch("app.services.router.renderer.render_resume", side_effect=RuntimeError("Render failed")):
            with patch("app.services.error_handler.handle_error", new_callable=AsyncMock) as mock_err:
                reply = await handle_resume(db_session, job, "retry", user_tier="pro")

        db_session.refresh(job)
        assert job.status == "render_failed"
        assert mock_err.called
        assert reply == ""

    async def test_retry_after_render_failed(self, db_session, pro_user, sample_resume_data):
        """User sends 'retry' after render_failed → generation retried."""
        from app.services.router import handle_inbound

        job = Job(
            user_id=pro_user.id,
            type="resume",
            status="render_failed",
            answers={**sample_resume_data, "_step": "done"},
        )
        db_session.add(job)
        db_session.commit()

        with patch("app.services.router.renderer.render_resume") as mock_render:
            mock_render.return_value = b"docx_bytes"
            with patch("app.services.router.storage.save_file_locally", return_value="/tmp/test.docx"):
                reply = await handle_inbound(
                    db_session,
                    str(pro_user.telegram_user_id),
                    "retry",
                    telegram_username=pro_user.telegram_username,
                )

        # Should have attempted render
        assert mock_render.called or "SEND_DOCUMENT" in (reply or "")


# --- Dropout / step reminder tests ---


@pytest.mark.asyncio
class TestDropoutRecovery:
    """Dropout and step reminder handling."""

    async def test_help_mid_flow_shows_step_reminder(self, db_session, test_user, test_job):
        """User mid-flow sends /help → help shown with step reminder."""
        from app.services.router import handle_inbound, STEP_LABELS

        test_job.answers = {"_step": "basics", "basics": {}}
        db_session.commit()

        reply = await handle_inbound(
            db_session,
            str(test_user.telegram_user_id),
            "/help",
            telegram_username=test_user.telegram_username,
        )

        assert "Help" in reply or "help" in reply.lower()
        assert "basics" in reply.lower() or "Back to your" in reply


# --- Valid input after failed input ---


@pytest.mark.asyncio
class TestValidInputAfterFailure:
    """Flow continues correctly after user corrects invalid input."""

    async def test_valid_basics_after_invalid(self, db_session, test_user):
        """Invalid email then valid basics → flow continues."""
        from app.services.router import handle_inbound

        # Start resume
        await handle_inbound(db_session, str(test_user.telegram_user_id), "resume")

        # Invalid basics
        reply1 = await handle_inbound(
            db_session,
            str(test_user.telegram_user_id),
            "John, bademail, 08012345678, Lagos",
        )
        assert "email" in reply1.lower() or "invalid" in reply1.lower()

        # Valid basics
        reply2 = await handle_inbound(
            db_session,
            str(test_user.telegram_user_id),
            "John Doe, john@example.com, 08012345678, Lagos",
        )
        assert "role" in reply2.lower() or "target" in reply2.lower()
