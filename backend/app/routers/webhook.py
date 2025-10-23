from fastapi import APIRouter, Request, HTTPException
from app.services.security import valid_signature
from app.services.whatsapp import reply_text

router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])

@router.post("")
async def receive(request: Request):
    body = await request.body()
    if not valid_signature(request.headers.get("X-Hub-Signature-256"), body):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()

    # TEMP: log inbound for debugging
    print("INBOUND PAYLOAD:", payload)

    wa_id, text = extract_message(payload)
    if wa_id:
        # IMPORTANT: await here
        resp = await reply_text(wa_id, "Hi! Do you want a Resume, CV, or Cover Letter?")
        # TEMP: log outbound result
        print("SEND RESULT:", resp)
    return {"status": "ok"}

# Minimal extractor tolerant to common shapes

def extract_message(payload: dict) -> tuple[str | None, str | None]:
    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        contacts = value.get("contacts", [])
        messages = value.get("messages", [])
        wa_id = contacts[0]["wa_id"] if contacts else None
        text = None
        if messages:
            msg = messages[0]
            t = msg.get("type")
            if t == "text":
                text = msg["text"]["body"]
            elif t == "button":
                text = msg.get("button", {}).get("text")
            elif t == "interactive":
                inter = msg.get("interactive", {})
                text = (inter.get("button_reply", {}) or inter.get("list_reply", {})).get("title")
        return wa_id, text
    except Exception:
        return None, None