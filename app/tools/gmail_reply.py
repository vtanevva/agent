"""Tool: reply_email — reply inside an existing Gmail thread or by messageId."""

import os
import json
import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from pymongo import MongoClient
from dotenv import load_dotenv


from ..agent_core.tool_registry import register, ToolSchema

# -----------------------
# MongoDB tokens setup
# -----------------------
# Use the same MongoDB connection as server.py
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

# Initialize MongoDB connection
client = None
tokens = None

if MONGO_URI:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        db = client.get_database()
        tokens = db["tokens"]
    except Exception as e:
        print(f"[WARNING] MongoDB connection failed: {e}")
        tokens = None
else:
    print("[WARNING] MONGO_URI not set.")


def _service(user_id: str):
    # Check if MongoDB is available
    if tokens is None:
        raise RuntimeError(
            "MongoDB is not available. Gmail features are disabled. Please set up a database connection."
        )
    
    try:
        # Load stored Google OAuth credentials from MongoDB
        doc = tokens.find_one({"user_id": user_id}, {"google": 1})
        if not doc or "google" not in doc:
            raise FileNotFoundError(
                f"Google OAuth token for user '{user_id}' not found. Ask the user to connect Gmail first."
            )
        creds_info = doc["google"]
        creds = Credentials.from_authorized_user_info(creds_info)
        return build("gmail", "v1", credentials=creds, cache_discovery=False)
    except Exception as e:
        raise RuntimeError(f"Failed to load Gmail service: {e}")


def reply_email(
    user_id: str,
    thread_id: str,        # may be a messageId; we auto‑resolve
    to: str,
    body: str,
    subj_prefix: str = "Re:",
):
    try:
        svc = _service(user_id)
    except Exception as e:
        return f"Error: Gmail service unavailable - {e}"

    # 1 – resolve messageId → threadId (and get Subject)
    try:
        msg_meta = (
            svc.users()
            .messages()
            .get(
                userId="me",
                id=thread_id,
                format="metadata",
                metadataHeaders=["Subject", "Message-ID"],
            )
            .execute()
        )
        real_thread_id = msg_meta.get("threadId", thread_id)
        subj = next(
            (h["value"] for h in msg_meta["payload"]["headers"] if h["name"] == "Subject"),
            "(No subject)"
        )
    except HttpError as e:
        if e.resp.status in (400, 404):
            # assume we already had a threadId; fetch the thread instead
            thread_resp = (
                svc.users()
                .threads()
                .get(userId="me", id=thread_id, format="metadata")
                .execute()
            )
            real_thread_id = thread_id
            first_msg = thread_resp["messages"][0]
            subj = next(
                (h["value"] for h in first_msg["payload"]["headers"] if h["name"] == "Subject"),
                "(No subject)"
            )
            msg_meta = first_msg
        else:
            raise

    # 2 – build MIME reply
    mime = MIMEText(body)
    mime["to"] = to
    mime["subject"] = subj if subj_prefix in subj else f"{subj_prefix} {subj}"
    # Use Message-ID header if available for threading
    msg_id = next((h["value"] for h in msg_meta["payload"]["headers"] if h["name"] in ("Message-ID", "Message-Id")), None)
    if msg_id:
        mime["In-Reply-To"] = msg_id
        mime["References"] = msg_id

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    svc.users().messages().send(
        userId="me",
        body={"raw": raw, "threadId": real_thread_id},
    ).execute()

    return f"Reply sent in thread {real_thread_id}."


# Register the tool
register(
    reply_email,
    ToolSchema(
        name="reply_email",
        description="Send a reply inside an existing Gmail thread (accepts threadId or messageId).",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "thread_id": {"type": "string"},
                "to": {"type": "string"},
                "body": {"type": "string"},
                "subj_prefix": {"type": "string"},
            },
            "required": ["user_id", "thread_id", "to", "body"],
        },
    ),
)
