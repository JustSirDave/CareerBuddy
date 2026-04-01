"""
CareerBuddy - Configuration
Author: Sir Dave
"""
import os
from typing import Optional

from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings(BaseModel):
    # Application
    app_env: str = os.getenv("APP_ENV", "local")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "info")
    public_url: str = os.getenv("PUBLIC_URL", "http://localhost:8000")

    # Telegram Bot
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_bot_username: str = os.getenv("TELEGRAM_BOT_USERNAME", "CareerBuddyBot")
    # Env: TELEGRAM_WEBHOOK_SECRET — required in production (SEC-001); optional locally
    telegram_webhook_secret: Optional[str] = os.getenv("TELEGRAM_WEBHOOK_SECRET") or None
    admin_telegram_ids: list[str] = [
        id.strip() for id in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
        if id.strip()
    ]

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@postgres:5432/buddy"
    )

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

    # AI/LLM
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    # Payments
    paystack_secret: str = os.getenv("PAYSTACK_SECRET", "")


settings = Settings()