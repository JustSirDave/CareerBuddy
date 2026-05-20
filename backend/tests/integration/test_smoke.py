"""
Smoke tests: critical paths with external I/O mocked.
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models import User


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def override_get_db(db_session):
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.clear()


@patch("app.services.telegram.send_choice_menu", new_callable=AsyncMock)
@patch("app.services.telegram.reply_text", new_callable=AsyncMock)
@patch("app.services.telegram.send_typing_action", new_callable=AsyncMock)
def test_new_user_created_on_start(mock_typing, mock_reply, mock_menu, client, db_session):
    """New /start creates a User row and returns 200."""
    tid = "900001001"
    chat_id = 900001001
    payload = {
        "message": {
            "message_id": 9001,
            "from": {"id": chat_id, "username": "smoke", "first_name": "Smoke"},
            "chat": {"id": chat_id, "type": "private"},
            "text": "/start",
        }
    }
    response = client.post("/webhooks/telegram", json=payload)
    assert response.status_code == 200

    user = db_session.query(User).filter(User.telegram_user_id == tid).first()
    assert user is not None
    assert user.monthly_doc_count == 0


def test_telegram_webhook_rejects_missing_secret_token(client, db_session, monkeypatch):
    """When webhook secret is configured, missing header → 403 and no User rows."""
    monkeypatch.setattr(settings, "telegram_webhook_secret", "smoke-test-secret", raising=False)
    count_before = db_session.query(User).count()
    response = client.post(
        "/webhooks/telegram",
        json={
            "message": {
                "message_id": 91001,
                "from": {"id": 9100191001, "username": "sec001"},
                "chat": {"id": 9100191001, "type": "private"},
                "text": "/start",
            }
        },
    )
    assert response.status_code == 403
    assert db_session.query(User).count() == count_before
