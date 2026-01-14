import uuid
import time
from pathlib import Path

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


@app.on_event("startup")
async def startup_event():
    """Check required environment variables on startup"""
    required = [
        ("TELEGRAM_BOT_TOKEN", settings.telegram_bot_token),
    ]
    missing = [k for k, v in required if not v]
    if missing:
        logger.warning(f"[BOOT] Missing required env: {', '.join(missing)}")


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