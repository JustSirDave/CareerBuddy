# backend/app/api/whatsapp_webhook.py
from fastapi import APIRouter, Request, HTTPException, Depends
from loguru import logger

from app.services.security import valid_signature
from app.services.idempotency import seen_or_mark  # ADD THIS
from app.db import get_db
from app.services.whatsapp import reply_text, send_choice_menu
from app.services.router import handle_inbound

router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])

@router.post("")
async def receive(request: Request, db=Depends(get_db)):
    body = await request.body()
    if not valid_signature(request.headers.get("X-Hub-Signature-256"), body):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    
    # Ignore delivery/read/status callbacks
    value = (
        payload.get("entry", [{}])[0]
        .get("changes", [{}])[0]
        .get("value", {})
    )
    if not value.get("messages"):
        return {"status": "ignored"}

    wa_id, text, msg_id = extract_message(payload)
    if not wa_id:
        return {"status": "ignored"}

    # ← EARLY DEDUPLICATION: Check BEFORE calling handle_inbound
    if msg_id and seen_or_mark(msg_id):
        logger.warning(f"[webhook] Duplicate msg_id={msg_id} from wa_id={wa_id}, skipping")
        return {"status": "duplicate"}

    # Now process the message
    reply = handle_inbound(db, wa_id, text or "", msg_id=msg_id)

    if reply == "__SHOW_MENU__":
        await send_choice_menu(wa_id)
        return {"status": "ok"}

    if reply:
        await reply_text(wa_id, reply)
    return {"status": "ok"}


def extract_message(payload: dict) -> tuple[str | None, str | None, str | None]:
    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        contacts = value.get("contacts", [])
        messages = value.get("messages", [])
        wa_id = contacts[0]["wa_id"] if contacts else None
        text = None
        msg_id = None
        if messages:
            msg = messages[0]
            msg_id = msg.get("id")
            t = msg.get("type")
            if t == "text":
                text = msg["text"]["body"]
            elif t == "button":
                text = msg.get("button", {}).get("text")
            elif t == "interactive":
                inter = msg.get("interactive", {})
                text = (inter.get("button_reply", {}) or inter.get("list_reply", {})).get("title")
        return wa_id, text, msg_id
    except Exception as e:
        logger.error(f"[webhook] Failed to extract message: {e}")
        return None, None, None