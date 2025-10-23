import httpx
from loguru import logger
from app.config import settings

GRAPH_BASE = "https://graph.facebook.com/v20.0"

async def reply_text(wa_id: str, text: str):
    url = f"{GRAPH_BASE}/{settings.phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {settings.wa_token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "text",
        "text": {"body": text}
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            logger.error(f"WhatsApp send failed: {r.status_code} {r.text}")
        return r.json() if r.content else {}