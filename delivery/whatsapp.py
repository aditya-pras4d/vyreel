"""
Sends the brief PDF to the creator via the WhatsApp Cloud API (Meta Graph API).

Required env:
  WHATSAPP_TOKEN            permanent access token for the WhatsApp Business app
  WHATSAPP_PHONE_NUMBER_ID  sender phone-number id from the Meta developer console

Optional env:
  WHATSAPP_TEMPLATE_NAME    name of an approved message template with a DOCUMENT
                            header and two body params: {{1}} = topic, {{2}} = date.
                            Required for scheduled daily sends — WhatsApp only
                            delivers business-initiated messages outside the 24h
                            customer-service window if they use an approved template.
  WHATSAPP_TEMPLATE_LANG    template language code (default "en")

Without WHATSAPP_TEMPLATE_NAME set, falls back to a free-form document message,
which only reaches creators who messaged us within the last 24h (fine for testing).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import date
import requests
from dotenv import load_dotenv
from db import get_conn

load_dotenv()

GRAPH_BASE = "https://graph.facebook.com/v21.0"


def _upload_pdf(phone_number_id: str, token: str, pdf_path: str) -> str:
    """Uploads the PDF to WhatsApp media storage, returns the media id."""
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            f"{GRAPH_BASE}/{phone_number_id}/media",
            headers={"Authorization": f"Bearer {token}"},
            data={"messaging_product": "whatsapp", "type": "application/pdf"},
            files={"file": (os.path.basename(pdf_path), f, "application/pdf")},
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json()["id"]


def send(creator_phone: str, handle: str, brief_id: int, pdf_path: str, topic: str) -> bool:
    token = os.environ.get("WHATSAPP_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    if not token or not phone_number_id:
        print("[whatsapp] WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID not set, skipping send")
        return False
    if not creator_phone:
        print(f"[whatsapp] @{handle.lstrip('@')} has no phone number on file, skipping")
        return False
    if not os.path.exists(pdf_path):
        print(f"[whatsapp] PDF not found at {pdf_path}")
        return False

    to = creator_phone.lstrip("+")
    today = date.today().strftime("%B %d")
    filename = f"Vyreel Brief - {today}.pdf"

    try:
        media_id = _upload_pdf(phone_number_id, token, pdf_path)

        template = os.environ.get("WHATSAPP_TEMPLATE_NAME")
        if template:
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {
                    "name": template,
                    "language": {"code": os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")},
                    "components": [
                        {
                            "type": "header",
                            "parameters": [
                                {"type": "document",
                                 "document": {"id": media_id, "filename": filename}}
                            ],
                        },
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": topic},
                                {"type": "text", "text": today},
                            ],
                        },
                    ],
                },
            }
        else:
            print("[whatsapp] WHATSAPP_TEMPLATE_NAME not set — sending free-form message "
                  "(only delivered if the creator messaged us within 24h)")
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "document",
                "document": {
                    "id": media_id,
                    "filename": filename,
                    "caption": f"Your Vyreel brief is ready. Today's top opportunity: {topic}.",
                },
            }

        resp = requests.post(
            f"{GRAPH_BASE}/{phone_number_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()

    except requests.RequestException as e:
        detail = f" — {e.response.text[:300]}" if getattr(e, "response", None) is not None else ""
        print(f"[whatsapp] send failed: {e}{detail}")
        return False

    conn = get_conn()
    try:
        conn.execute("UPDATE briefs SET sent_at = datetime('now') WHERE id = ?", (brief_id,))
        conn.commit()
    finally:
        conn.close()

    print(f"[whatsapp] sent to +{to}")
    return True
