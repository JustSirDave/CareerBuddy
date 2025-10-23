import uuid
import time

from fastapi import FastAPI, Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from loguru import logger

from app.routers.webhook import router as whatsapp_router
from app.config import settings


app = FastAPI(title="CareerBuddy Backend")

@app.post("/webhook")
async def noop():
    return {"ok": True}


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

# WhatsApp verify endpoint must parse hub.* params
@app.get("/webhooks/whatsapp")
async def whatsapp_verify(request: Request):
    qp = request.query_params
    mode = qp.get("hub.mode")
    challenge = qp.get("hub.challenge")
    token = qp.get("hub.verify_token")
    if mode == "subscribe" and token == settings.wa_verify_token and challenge:
        return int(challenge)
    raise HTTPException(status_code=403, detail="Verification failed")

async def check_env():
    required = [
        ("WHATSAPP_VERIFY_TOKEN", settings.wa_verify_token),
        ("WHATSAPP_APP_SECRET", settings.wa_app_secret),
        ("WHATSAPP_TOKEN", settings.wa_token),
        ("PHONE_NUMBER_ID", settings.phone_number_id),
    ]
    missing = [k for k, v in required if not v]
    if missing:
        # log clearly; you can also raise RuntimeError to stop
        print(f"[BOOT] Missing required env: {', '.join(missing)}")

@app.api_route("/webhook", methods=["GET", "POST"])
async def noop():
    return {"ok": True}

@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}

app.add_middleware(RequestLogMiddleware)

app.include_router(whatsapp_router)