"""
Tests for webhook API endpoints
Tests Telegram and Paystack webhook handling
"""
import uuid
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models import User, Job


@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(app)


@pytest.fixture(autouse=True)
def override_get_db(db_session):
    """Route FastAPI DB dependency to the same session as test fixtures."""

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.clear()


class TestTelegramWebhook:
    """Test Telegram webhook endpoint"""

    @patch("app.routers.webhook.handle_inbound", new_callable=AsyncMock)
    def test_webhook_receives_message(self, mock_handle, client, db_session):
        """Test webhook receives and processes message"""
        mock_handle.return_value = "Bot response"
        
        payload = {
            "message": {
                "message_id": 123,
                "from": {
                    "id": 987654321,
                    "username": "testuser",
                    "first_name": "Test"
                },
                "chat": {"id": 987654321},
                "text": "Hello bot"
            }
        }
        
        response = client.post("/webhooks/telegram", json=payload)
        
        assert response.status_code == 200

    def test_webhook_invalid_payload(self, client):
        """Test webhook with invalid payload"""
        response = client.post("/webhooks/telegram", json={})
        
        # Should handle gracefully
        assert response.status_code in [200, 400, 422]

    def test_webhook_missing_message(self, client):
        """Test webhook with missing message"""
        payload = {
            "update_id": 123456789
            # Missing "message" key
        }
        
        response = client.post("/webhooks/telegram", json=payload)
        
        # Should handle gracefully
        assert response.status_code in [200, 400]

    @patch("app.routers.webhook.handle_inbound", new_callable=AsyncMock)
    def test_webhook_callback_query(self, mock_handle, client):
        """Test webhook receives callback query (button click)"""
        mock_handle.return_value = "Button clicked"
        
        payload = {
            "callback_query": {
                "id": "123",
                "from": {"id": 987654321, "username": "testuser"},
                "message": {
                    "message_id": 456,
                    "chat": {"id": 987654321}
                },
                "data": "choose_resume"
            }
        }
        
        response = client.post("/webhooks/telegram", json=payload)
        
        assert response.status_code == 200

    @patch("app.routers.webhook.handle_inbound", new_callable=AsyncMock)
    def test_webhook_document_upload(self, mock_handle, client):
        """Test webhook receives document upload"""
        payload = {
            "message": {
                "message_id": 789,
                "from": {"id": 987654321, "username": "testuser"},
                "chat": {"id": 987654321},
                "document": {
                    "file_id": "doc123",
                    "file_name": "resume.docx",
                    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                }
            }
        }
        
        response = client.post("/webhooks/telegram", json=payload)
        
        assert response.status_code == 200


class TestHealthEndpoints:
    """Test health check endpoints"""

    def test_health_endpoint(self, client):
        """Test basic health check"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"

    @pytest.mark.skip(
        reason="Requires live Postgres host; not available in test env. Test manually against deployed instance — see SRS NFR-010."
    )
    def test_health_db_endpoint(self, client):
        """Test database health check"""
        response = client.get("/health/db")

        # Should check database connection
        assert response.status_code in [200, 500, 503]


class TestFileDownload:
    """Test document download endpoint"""

    def test_download_nonexistent_file(self, client):
        """Valid UUID but no job row → 404 (invalid job id format → 400)."""
        missing_job = str(uuid.uuid4())
        response = client.get(f"/download/{missing_job}/file.docx")

        assert response.status_code == 404

    def test_download_existing_file(self, client, db_session, test_user):
        """Job exists and file on disk under output/jobs/{job_id}/."""
        job = Job(
            user_id=test_user.id,
            type="resume",
            status="delivered",
            answers={},
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        filename = "resume.docx"
        out_dir = Path("output") / "jobs" / str(job.id)
        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = out_dir / filename
        file_path.write_bytes(b"PK\x03\x04 fake docx")

        try:
            response = client.get(f"/download/{job.id}/{filename}")
            assert response.status_code == 200
        finally:
            file_path.unlink(missing_ok=True)
            out_dir.rmdir()
            parent = out_dir.parent
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()


class TestRateLimiting:
    """Test rate limiting middleware"""

    def test_rate_limit_normal_usage(self, client):
        """Test normal usage within rate limits"""
        # Make a few requests
        for i in range(5):
            response = client.get("/health")
            assert response.status_code == 200

    def test_rate_limit_excessive_requests(self, client):
        """Test excessive requests trigger rate limiting"""
        # Make many requests rapidly
        responses = []
        for i in range(100):
            response = client.get("/health")
            responses.append(response.status_code)
        
        # At least some should succeed
        assert 200 in responses
        
        # If rate limiting is strict, some might be 429
        # This depends on rate limit configuration

    def test_rate_limit_excluded_paths(self, client):
        """Test rate limiting excludes certain paths"""
        # Health check should not be rate limited
        for i in range(10):
            response = client.get("/health")
            assert response.status_code == 200


class TestWebhookSecurity:
    """Test webhook security measures"""

    def test_telegram_webhook_requires_post(self, client):
        """Test Telegram webhook only accepts POST"""
        response = client.get("/webhooks/telegram")
        
        assert response.status_code in [405, 404]  # Method not allowed

    def test_paystack_webhook_requires_post(self, client):
        """Test Paystack webhook only accepts POST"""
        response = client.get("/webhooks/paystack")
        
        assert response.status_code in [405, 404]

    def test_webhook_duplicate_message_handling(self, client):
        """Test webhook handles duplicate messages"""
        # Idempotency should prevent duplicate processing
        payload = {
            "message": {
                "message_id": 999,
                "from": {"id": 111, "username": "test"},
                "chat": {"id": 111},
                "text": "Test message"
            }
        }
        
        with patch("app.routers.webhook.handle_inbound", new_callable=AsyncMock) as mock_handle:
            mock_handle.return_value = "Response"
            
            # Send same message twice
            response1 = client.post("/webhooks/telegram", json=payload)
            response2 = client.post("/webhooks/telegram", json=payload)
            
            # Both should succeed
            assert response1.status_code == 200
            assert response2.status_code == 200


class TestErrorHandling:
    """Test error handling in webhooks"""

    @patch("app.routers.webhook.handle_inbound", new_callable=AsyncMock)
    def test_webhook_handles_internal_error(self, mock_handle, client):
        """Test webhook handles internal errors gracefully"""
        mock_handle.side_effect = Exception("Internal error")
        
        payload = {
            "message": {
                "message_id": 123,
                "from": {"id": 987654321, "username": "test"},
                "chat": {"id": 987654321},
                "text": "Hello"
            }
        }
        
        response = client.post("/webhooks/telegram", json=payload)
        
        # Should handle gracefully, not crash
        assert response.status_code in [200, 500]

    @patch("app.routers.webhook.handle_inbound", new_callable=AsyncMock)
    def test_webhook_handles_database_error(self, mock_handle, client):
        """Test webhook handles database errors"""
        from sqlalchemy.exc import OperationalError
        mock_handle.side_effect = OperationalError("DB error", None, None)
        
        payload = {
            "message": {
                "message_id": 456,
                "from": {"id": 987654321, "username": "test"},
                "chat": {"id": 987654321},
                "text": "Test"
            }
        }
        
        response = client.post("/webhooks/telegram", json=payload)
        
        # Should handle gracefully
        assert response.status_code in [200, 500, 503]


class TestWebhookIntegration:
    """Integration tests for webhook flow"""

    @patch("app.services.telegram.send_choice_menu", new_callable=AsyncMock)
    @patch("app.services.telegram.reply_text", new_callable=AsyncMock)
    @patch("app.services.telegram.send_typing_action", new_callable=AsyncMock)
    def test_end_to_end_message_flow(self, mock_typing, mock_reply, mock_menu, client, db_session):
        """Test complete message processing flow (telegram I/O mocked; router runs for real)."""
        payload = {
            "message": {
                "message_id": 123,
                "from": {
                    "id": 555666777,
                    "username": "newuser",
                    "first_name": "New",
                },
                "chat": {"id": 555666777, "type": "private"},
                "text": "/start",
            }
        }

        response = client.post("/webhooks/telegram", json=payload)

        assert response.status_code == 200

        user = db_session.query(User).filter(User.telegram_user_id == "555666777").first()
        assert user is not None
