"""Tool: forward_email — forward a Gmail message to another recipient."""

import json
import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from app.utils.tool_registry import register, ToolSchema
from app.utils.google_api_helpers import get_gmail_service


def forward_email(
    user_id: str,
    thread_id: str,        # may be a messageId; we auto‑resolve
    to: str,
    body: str = "",
    subj_prefix: str = "Fwd:",
):
    """
    Forward a Gmail message to another recipient.
    
    Parameters
    ----------
    user_id : str
        User identifier
    thread_id : str
        Thread ID or message ID (will be resolved)
    to : str
        Recipient email address
    body : str
        Optional message body to include with the forward
    subj_prefix : str
        Subject prefix (default: "Fwd:")
        
    Returns
    -------
    str
        Success message or error
    """
    try:
        svc = get_gmail_service(user_id)
    except Exception as e:
        return f"Error: Gmail service unavailable - {e}"

    # 1 – resolve messageId → threadId (and get Subject and body)
    try:
        msg_meta = (
            svc.users()
            .messages()
            .get(
                userId="me",
                id=thread_id,
                format="full",
                metadataHeaders=["Subject", "Message-ID", "From", "Date"],
            )
            .execute()
        )
        real_thread_id = msg_meta.get("threadId", thread_id)
        subj = next(
            (h["value"] for h in msg_meta["payload"]["headers"] if h["name"] == "Subject"),
            "(No subject)"
        )
        # Get the original message body
        original_body = _extract_message_body(msg_meta)
    except HttpError as e:
        if e.resp.status in (400, 404):
            # assume we already had a threadId; fetch the thread instead
            thread_resp = (
                svc.users()
                .threads()
                .get(userId="me", id=thread_id, format="full")
                .execute()
            )
            real_thread_id = thread_id
            first_msg = thread_resp["messages"][0]
            subj = next(
                (h["value"] for h in first_msg["payload"]["headers"] if h["name"] == "Subject"),
                "(No subject)"
            )
            original_body = _extract_message_body(first_msg)
            msg_meta = first_msg
        else:
            raise

    # 2 – build MIME forward message
    # Include original message in the body
    from_header = next(
        (h["value"] for h in msg_meta["payload"]["headers"] if h["name"] == "From"),
        "Unknown"
    )
    date_header = next(
        (h["value"] for h in msg_meta["payload"]["headers"] if h["name"] == "Date"),
        ""
    )
    
    # Build forward body
    forward_body = body if body else ""
    if forward_body:
        forward_body += "\n\n"
    forward_body += f"---------- Forwarded message ----------\n"
    forward_body += f"From: {from_header}\n"
    forward_body += f"Date: {date_header}\n"
    forward_body += f"Subject: {subj}\n"
    forward_body += f"To: {to}\n\n"
    forward_body += original_body
    
    mime = MIMEText(forward_body)
    mime["to"] = to
    mime["subject"] = subj if subj_prefix in subj else f"{subj_prefix} {subj}"

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    svc.users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()

    return f"Email forwarded to {to}."


def _extract_message_body(msg):
    """Extract plain text body from Gmail message."""
    payload = msg.get("payload", {})
    body_text = ""
    
    # Check if multipart
    if payload.get("mimeType") == "multipart/alternative" or payload.get("mimeType") == "multipart/mixed":
        parts = payload.get("parts", [])
        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data")
                if data:
                    import base64
                    body_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    break
    elif payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            import base64
            body_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    
    return body_text or "(No body content)"


# Register the tool
register(
    forward_email,
    ToolSchema(
        name="forward_email",
        description="Forward a Gmail message to another recipient.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "thread_id": {"type": "string"},
                "to": {"type": "string"},
                "body": {"type": "string"},
                "subj_prefix": {"type": "string"},
            },
            "required": ["user_id", "thread_id", "to"],
        },
    ),
)

