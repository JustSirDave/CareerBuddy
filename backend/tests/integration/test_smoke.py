"""
Smoke tests: critical paths with external I/O mocked.
"""
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models import Payment, User


@contextmanager
def _paystack_secret_cleared():
    old = settings.paystack_secret
    settings.paystack_secret = ""
    try:
        yield
    finally:
        settings.paystack_secret = old


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
def test_new_user_receives_free_credits(
    mock_typing, mock_reply, mock_menu, client, db_session
):
    """New /start user has free resume/CV and cover-letter allowances (User flags, not Credit rows)."""
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
    assert user.free_resume_used is False
    assert user.free_cover_letter_used is False


@patch("app.services.telegram.reply_text", new_callable=AsyncMock)
@patch("app.services.payments.verify_payment", new_callable=AsyncMock)
def test_paystack_webhook_awards_credit(mock_verify, mock_reply, client, db_session, test_user):
    """Pending Paystack payment + charge.success updates payment and awards credits."""
    ref = "smoke_paystack_ref_1"
    pay = Payment(
        user_id=test_user.id,
        reference=ref,
        amount=750000,
        currency="NGN",
        status="pending",
        provider="paystack",
        product_type="resume",
    )
    db_session.add(pay)
    db_session.commit()

    mock_verify.return_value = {
        "status": "success",
        "reference": ref,
        "amount": 750000,
    }
    payload = {"event": "charge.success", "data": {"reference": ref, "amount": 750000}}

    with _paystack_secret_cleared():
        with patch("app.services.referral.process_referral_conversion", new_callable=AsyncMock):
            response = client.post("/webhooks/paystack", json=payload)

    assert response.status_code == 200
    db_session.refresh(pay)
    assert pay.status == "success"
    db_session.refresh(test_user)
    assert test_user.document_credits >= 1


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
