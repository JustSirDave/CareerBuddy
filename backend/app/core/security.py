import hmac, hashlib
from app.config import settings

HEADER = "X-Hub-Signature-256"

def valid_signature(sig_header: str | None, body: bytes) -> bool:
    if not sig_header:
        return False
    sig = sig_header.replace("sha256=", "")
    expected = hmac.new(settings.wa_app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)