"""Shared utility functions for CareerBuddy."""
import hashlib
import hmac as _hmac
import re
import time
from datetime import datetime


def generate_download_token(job_id: str, secret: str, ttl: int = 3600) -> str:
    """Return a signed expiring token for a download URL."""
    expiry = int(time.time()) + ttl
    payload = f"{job_id}.{expiry}"
    sig = _hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{expiry}:{sig}"


def verify_download_token(job_id: str, token: str, secret: str) -> bool:
    """Return True if token is valid and not expired. Always passes when secret is empty (dev mode)."""
    if not secret:
        return True
    try:
        expiry_str, sig = token.split(":", 1)
        if int(expiry_str) < int(time.time()):
            return False
        payload = f"{job_id}.{expiry_str}"
        expected = _hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return _hmac.compare_digest(sig, expected)
    except Exception:
        return False


def generate_filename(job) -> str:
    """Generate a user-friendly document filename from a Job instance."""
    answers = job.answers or {}
    basics = answers.get("basics", {}) or {}
    name = basics.get("name", "Document")
    clean_name = re.sub(r'[<>:"/\\|?*]', "", str(name))
    doc_map = {"resume": "Resume", "cv": "CV", "cover": "Cover Letter", "revamp": "Revamp"}
    doc_type = doc_map.get(job.type, job.type.capitalize() if job.type else "Document")
    return f"{clean_name} - {doc_type}.docx"
