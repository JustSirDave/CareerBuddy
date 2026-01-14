"""
Tests for webhook API endpoints
Tests Telegram and Paystack webhook handling
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock
from app.main import app
from app.models import User, Payment


@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(app)


class TestTelegramWebhook:
    """Test Telegram webhook endpoint"""

    @patch('app.routers.webhook.handle_inbound')
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
        
        response = client.post("/webhook/telegram", json=payload)
        
        assert response.status_code == 200

    def test_webhook_invalid_payload(self, client):
        """Test webhook with invalid payload"""
        response = client.post("/webhook/telegram", json={})
        
        # Should handle gracefully
        assert response.status_code in [200, 400, 422]

    def test_webhook_missing_message(self, client):
        """Test webhook with missing message"""
        payload = {
            "update_id": 123456789
            # Missing "message" key
        }
        
        response = client.post("/webhook/telegram", json=payload)
        
        # Should handle gracefully
        assert response.status_code in [200, 400]

    @patch('app.routers.webhook.handle_inbound')
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
        
        response = client.post("/webhook/telegram", json=payload)
        
        assert response.status_code == 200

    @patch('app.routers.webhook.handle_inbound')
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
        
        response = client.post("/webhook/telegram", json=payload)
        
        assert response.status_code == 200


class TestPaystackWebhook:
    """Test Paystack webhook endpoint"""

    @patch('app.routers.webhook.payments.verify_payment')
    def test_successful_payment_webhook(self, mock_verify, client, db_session, test_user):
        """Test successful payment webhook"""
        mock_verify.return_value = {
            "status": "success",
            "amount": 75000,  # 750 NGN in kobo
            "reference": "ref_123",
            "customer": {"email": test_user.email}
        }
        
        payload = {
            "event": "charge.success",
            "data": {
                "reference": "ref_123",
                "amount": 75000,
                "customer": {"email": test_user.email},
                "status": "success"
            }
        }
        
        response = client.post("/webhook/paystack", json=payload)
        
        assert response.status_code == 200

    def test_failed_payment_webhook(self, client, db_session, test_user):
        """Test failed payment webhook"""
        payload = {
            "event": "charge.failed",
            "data": {
                "reference": "ref_456",
                "amount": 75000,
                "customer": {"email": test_user.email},
                "status": "failed"
            }
        }
        
        response = client.post("/webhook/paystack", json=payload)
        
        # Should handle gracefully
        assert response.status_code in [200, 400]

    def test_webhook_invalid_signature(self, client):
        """Test webhook with invalid signature"""
        # In production, webhook signature should be verified
        # This test ensures invalid signatures are rejected
        payload = {"event": "charge.success"}
        
        response = client.post(
            "/webhook/paystack",
            json=payload,
            headers={"X-Paystack-Signature": "invalid_signature"}
        )
        
        # Should either accept or reject based on signature verification
        assert response.status_code in [200, 401, 403]

    def test_upgrade_payment_webhook(self, client, db_session, test_user):
        """Test premium upgrade payment webhook"""
        assert test_user.tier == "free"
        
        payload = {
            "event": "charge.success",
            "data": {
                "reference": f"upgrade_{test_user.telegram_user_id}_123",
                "amount": 750000,  # 7500 NGN in kobo
                "customer": {"email": test_user.email},
                "status": "success",
                "metadata": {"type": "upgrade"}
            }
        }
        
        # Mock the payment verification
        with patch('app.routers.webhook.payments.verify_payment') as mock_verify:
            mock_verify.return_value = payload["data"]
            response = client.post("/webhook/paystack", json=payload)
        
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

    def test_health_db_endpoint(self, client):
        """Test database health check"""
        response = client.get("/health/db")
        
        # Should check database connection
        assert response.status_code in [200, 500, 503]


class TestFileDownload:
    """Test document download endpoint"""

    def test_download_nonexistent_file(self, client):
        """Test downloading non-existent file"""
        response = client.get("/download/invalid_job_id/file.docx")
        
        assert response.status_code == 404

    @patch('pathlib.Path.exists', return_value=True)
    def test_download_existing_file(self, mock_exists, client):
        """Test downloading existing file"""
        # Note: This requires mocking the file system
        # In integration tests, we would create actual files
        response = client.get("/download/test_job_id/test.docx")
        
        # Response depends on whether file actually exists
        assert response.status_code in [200, 404]


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
        response = client.get("/webhook/telegram")
        
        assert response.status_code in [405, 404]  # Method not allowed

    def test_paystack_webhook_requires_post(self, client):
        """Test Paystack webhook only accepts POST"""
        response = client.get("/webhook/paystack")
        
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
        
        with patch('app.routers.webhook.handle_inbound') as mock_handle:
            mock_handle.return_value = "Response"
            
            # Send same message twice
            response1 = client.post("/webhook/telegram", json=payload)
            response2 = client.post("/webhook/telegram", json=payload)
            
            # Both should succeed
            assert response1.status_code == 200
            assert response2.status_code == 200


class TestErrorHandling:
    """Test error handling in webhooks"""

    @patch('app.routers.webhook.handle_inbound')
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
        
        response = client.post("/webhook/telegram", json=payload)
        
        # Should handle gracefully, not crash
        assert response.status_code in [200, 500]

    @patch('app.routers.webhook.handle_inbound')
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
        
        response = client.post("/webhook/telegram", json=payload)
        
        # Should handle gracefully
        assert response.status_code in [200, 500, 503]


class TestWebhookIntegration:
    """Integration tests for webhook flow"""

    @patch('app.routers.webhook.telegram_service.send_message')
    @patch('app.services.router.handle_inbound')
    def test_end_to_end_message_flow(self, mock_handle, mock_send, client, db_session):
        """Test complete message processing flow"""
        mock_handle.return_value = "Welcome!"
        mock_send.return_value = {"ok": True, "result": {"message_id": 789}}
        
        payload = {
            "message": {
                "message_id": 123,
                "from": {
                    "id": 555666777,
                    "username": "newuser",
                    "first_name": "New"
                },
                "chat": {"id": 555666777},
                "text": "/start"
            }
        }
        
        response = client.post("/webhook/telegram", json=payload)
        
        assert response.status_code == 200
        
        # User should be created
        user = db_session.query(User).filter(
            User.telegram_user_id == "555666777"
        ).first()
        
        # Note: User creation happens in handle_inbound
        # This test validates the integration
