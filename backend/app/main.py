"""
CareerBuddy - AI-powered resume, CV, and cover letter generator
Author: Sir Dave
"""
import json
import logging
import uuid
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger
from sqlalchemy import text

from app.routers.webhook import router as webhook_router
from app.config import settings
from app.db import get_db
from app.middleware import RateLimitMiddleware, rate_limiter

app = FastAPI(title="CareerBuddy Backend")


class JSONFormatter(logging.Formatter):
    """Structured JSON logging for traceability."""

    def format(self, record):
        log_record = {
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "time": self.formatTime(record),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


def _configure_structured_logging():
    """Configure structured JSON logging at app startup."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = str(uuid.uuid4())[:8]
        start = time.time()
        response = await call_next(request)
        dur_ms = int((time.time() - start) * 1000)
        logger.bind(request_id=rid).info(
            f"{request.method} {request.url.path} -> {response.status_code} ({dur_ms}ms)"
        )
        response.headers["X-Request-ID"] = rid
        return response


def _is_public_url(url: str) -> bool:
    """Check if URL is publicly reachable (not localhost)."""
    if not url or not url.strip():
        return False
    lower = url.lower().strip()
    return not (
        lower.startswith("http://localhost")
        or lower.startswith("https://localhost")
        or "127.0.0.1" in lower
    )


async def _register_telegram_webhook() -> None:
    """Register webhook with Telegram when PUBLIC_URL is a real public URL."""
    if not settings.telegram_bot_token:
        logger.warning("[BOOT] TELEGRAM_BOT_TOKEN missing - skipping webhook registration")
        return
    if not _is_public_url(settings.public_url):
        logger.info(
            f"[BOOT] PUBLIC_URL is localhost - webhook not set. "
            "Use ngrok or a public domain and set PUBLIC_URL to enable."
        )
        return
    webhook_url = f"{settings.public_url.rstrip('/')}/webhooks/telegram"
    api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(api_url, json={"url": webhook_url})
            data = r.json()
        if data.get("ok"):
            logger.info(f"[BOOT] Telegram webhook set: {webhook_url}")
        else:
            logger.warning(f"[BOOT] Telegram webhook failed: {data.get('description', 'unknown')}")
    except Exception as e:
        logger.warning(f"[BOOT] Could not set Telegram webhook: {e}")


@app.on_event("startup")
async def startup_event():
    """Check required env and register webhook when PUBLIC_URL is public."""
    _configure_structured_logging()
    required = [
        ("TELEGRAM_BOT_TOKEN", settings.telegram_bot_token),
    ]
    missing = [k for k, v in required if not v]
    if missing:
        logger.warning(f"[BOOT] Missing required env: {', '.join(missing)}")
    await _register_telegram_webhook()
    from app.services.scheduler import start_scheduler
    start_scheduler()


@app.on_event("shutdown")
def shutdown_event():
    """Stop scheduler on shutdown."""
    from app.services.scheduler import stop_scheduler
    stop_scheduler()


@app.get("/health/db")
def health_db(db = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"db": "ok"}

@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


@app.get("/download/{job_id}/{filename}")
async def download_file(job_id: str, filename: str):
    """
    Serve generated documents for download.

    Args:
        job_id: Job UUID
        filename: Document filename

    Returns:
        FileResponse with the document
    """
    # Construct file path
    file_path = Path("output") / "jobs" / job_id / filename

    # Check if file exists
    if not file_path.exists():
        logger.error(f"[download] File not found: {file_path}")
        raise HTTPException(status_code=404, detail="File not found")

    # Serve the file
    logger.info(f"[download] Serving file: {file_path}")
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


app.add_middleware(RequestLogMiddleware)
app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)

app.include_router(webhook_router)