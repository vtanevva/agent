"""Tool: send_email — send a fresh Gmail message."""

import json
import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Tool registry removed - agents call functions directly now
from app.utils.tool_registry import register, ToolSchema
from app.utils.google_api_helpers import get_gmail_service


def send_email(user_id: str, to: str, subject: str | None = None, body: str | None = None):
    subject = subject or "(No subject)"
    body = body or "Hello,\n\nBest regards"
    try:
        svc = get_gmail_service(user_id)
    except Exception as e:
        return f"Error: Gmail service unavailable - {e}"

    mime = MIMEText(body)
    mime["to"] = to
    mime["subject"] = subject

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    message = {"raw": raw}
    svc.users().messages().send(userId="me", body=message).execute()

    return f"Email sent to {to}."


# Register the tool
register(
    send_email,
    ToolSchema(
        name="send_email",
        description="Send an email via the user's Gmail account.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["user_id", "to"],
        },
    ),
)
