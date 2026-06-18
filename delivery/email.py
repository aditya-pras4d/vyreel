"""
Sends the brief PDF to the creator by email via Gmail SMTP.

This is the pilot delivery channel. WhatsApp (delivery/whatsapp.py) is kept
intact and can be switched back on later without re-onboarding anyone — we
already collect the WhatsApp number as a required field.

Required env:
  GMAIL_USER          the Gmail address briefs are sent from
  GMAIL_APP_PASSWORD  a Google App Password (NOT the normal account password;
                      generate one at https://myaccount.google.com/apppasswords)

Optional env:
  FROM_NAME           display name on the From header (default "Vyreel")
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import smtplib
import ssl
from datetime import date
from email.message import EmailMessage
from dotenv import load_dotenv
from db import get_conn

load_dotenv()

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # implicit TLS (SMTP over SSL)


def send(creator_email: str, handle: str, brief_id: int, pdf_path: str, topic: str) -> bool:
    user = os.environ.get("GMAIL_USER")
    password = os.environ.get("GMAIL_APP_PASSWORD")

    if not user or not password:
        print("[email] GMAIL_USER or GMAIL_APP_PASSWORD not set, skipping send")
        return False
    if not creator_email:
        print(f"[email] @{handle.lstrip('@')} has no email on file, skipping")
        return False
    if not os.path.exists(pdf_path):
        print(f"[email] PDF not found at {pdf_path}")
        return False

    today = date.today().strftime("%B %d")
    filename = f"Vyreel Brief - {today}.pdf"
    from_name = os.environ.get("FROM_NAME", "Vyreel")

    msg = EmailMessage()
    msg["Subject"] = f"Your Vyreel brief — {topic}"
    msg["From"] = f"{from_name} <{user}>"
    msg["To"] = creator_email
    msg.set_content(
        f"Hi @{handle.lstrip('@')},\n\n"
        f"Your Vyreel brief for {today} is ready.\n"
        f"Today's top opportunity: {topic}.\n\n"
        f"The full breakdown is attached as a PDF.\n\n"
        f"— Vyreel"
    )

    with open(pdf_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="pdf",
            filename=filename,
        )

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as server:
            server.login(user, password)
            server.send_message(msg)
    except Exception as e:
        print(f"[email] send failed: {e}")
        return False

    conn = get_conn()
    try:
        conn.execute("UPDATE briefs SET sent_at = datetime('now') WHERE id = ?", (brief_id,))
        conn.commit()
    finally:
        conn.close()

    print(f"[email] sent to {creator_email}")
    return True
