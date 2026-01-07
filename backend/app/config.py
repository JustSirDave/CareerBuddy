import os
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

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@postgres:5432/buddy"
    )

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

    # AI/LLM
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    # Payments (Phase 5)
    paystack_secret: str = os.getenv("PAYSTACK_SECRET", "")

    # Storage (Phase 4)
    s3_endpoint: str = os.getenv("S3_ENDPOINT", "")
    s3_region: str = os.getenv("S3_REGION", "")
    s3_bucket: str = os.getenv("S3_BUCKET", "")
    s3_access_key_id: str = os.getenv("S3_ACCESS_KEY_ID", "")
    s3_secret_access_key: str = os.getenv("S3_SECRET_ACCESS_KEY", "")


settings = Settings()