
import os
from pydantic import BaseModel


class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "local")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "info")

    wa_verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    wa_app_secret: str = os.getenv("WHATSAPP_APP_SECRET", "")
    wa_token: str = os.getenv("WHATSAPP_TOKEN", "")
    phone_number_id: str = os.getenv("PHONE_NUMBER_ID", "")
    paystack_secret: str = os.getenv("PAYSTACK_SECRET", "")

settings = Settings()