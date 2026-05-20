# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Xenaptis Technologies
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
    public_url: str = os.getenv("PUBLIC_URL", "http://localhost:8000")

    # Telegram Bot
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    # Env: TELEGRAM_WEBHOOK_SECRET — required in production (SEC-001); optional locally
    telegram_webhook_secret: Optional[str] = os.getenv("TELEGRAM_WEBHOOK_SECRET") or None
    admin_telegram_ids: list[str] = [
        id.strip() for id in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
        if id.strip()
    ]

    # Database — normalise scheme so SQLAlchemy uses psycopg v3, not psycopg2
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@postgres:5432/buddy"
    ).replace("postgresql://", "postgresql+psycopg://", 1).replace("postgres://", "postgresql+psycopg://", 1)

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

    # AI/LLM
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    # Cloudinary cloud storage
    cloudinary_cloud_name: str = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    cloudinary_api_key: str = os.getenv("CLOUDINARY_API_KEY", "")
    cloudinary_api_secret: str = os.getenv("CLOUDINARY_API_SECRET", "")

    # Monthly document limit
    monthly_doc_limit: int = int(os.getenv("MONTHLY_DOC_LIMIT", "5"))

    # Feedback
    feedback_channel_id: str = os.getenv("FEEDBACK_CHANNEL_ID", "")

    # Security
    download_secret: str = os.getenv("DOWNLOAD_SECRET", "")


settings = Settings()