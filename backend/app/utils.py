# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Xenaptis Technologies
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
    """Generate document filename: firstname_lastname_doctype.pdf (FIX 3 naming)."""
    answers = job.answers or {}
    basics = answers.get("basics", {}) or {}
    raw_name = (basics.get("name") or "").strip()

    def _slug(s: str) -> str:
        return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')

    if raw_name:
        parts = raw_name.split()
        if len(parts) >= 2:
            name_slug = f"{_slug(parts[0])}_{_slug(parts[-1])}"
        else:
            name_slug = _slug(parts[0])
    else:
        job_id_short = str(getattr(job, 'id', 'unknown'))[:8]
        doc_map = {"resume": "resume", "cv": "cv", "cover": "cover_letter", "revamp": "revamp"}
        dt = doc_map.get(job.type, job.type or "document")
        return f"careerbuddy_{dt}_{job_id_short}.pdf"

    doc_map = {"resume": "resume", "cv": "cv", "cover": "cover_letter", "revamp": "revamp"}
    doc_type = doc_map.get(job.type, job.type or "document")
    return f"{name_slug}_{doc_type}.pdf"
