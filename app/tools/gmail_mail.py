"""Tool: send_email — send a fresh Gmail message."""

import os
import json
import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from pymongo import MongoClient

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


def send_email(user_id: str, to: str, subject: str | None = None, body: str | None = None):
    subject = subject or "(No subject)"
    body = body or "Hello,\n\nBest regards"
    try:
        svc = _service(user_id)
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
