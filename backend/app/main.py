from fastapi import FastAPI, Request, HTTPException
from loguru import logger
from app.routers.webhook import router as whatsapp_router
from app.config import settings

app = FastAPI(title="BuddyAI Backend")

@app.post("/webhook")
async def noop():
    return {"ok": True}
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

@app.api_route("/webhook", methods=["GET", "POST"])
async def noop():
    return {"ok": True}

@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}

app.include_router(whatsapp_router)