"""Tool: list_recent_emails — show the user’s most‑recent *received* emails.

Returns JSON like:
[
  { "idx": 1,
    "threadId": "1983025185d299de",
    "from": "Deya Ivanova <ivanova.deq06@gmail.com>",
    "subject": "Re: Come Join Me",
    "snippet": "No thanks. I don’t like you" },
  ...
]
"""

import os
import json
from collections import OrderedDict
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
        # Rehydrate to Credentials
        creds = Credentials.from_authorized_user_info(creds_info)
        return build("gmail", "v1", credentials=creds, cache_discovery=False)
    except Exception as e:
        raise RuntimeError(f"Failed to load Gmail service: {e}")


def list_recent_emails(user_id: str, max_results: int = 5):
    try:
        svc = _service(user_id)
    except Exception as e:
        return json.dumps([{
            "error": "Gmail service unavailable",
            "message": str(e),
            "suggestion": "Please set up MongoDB and connect your Gmail account."
        }])

    # 1) Find up to 50 newest *received* messages (to:me AND not from:me)
    resp = svc.users().messages().list(
        userId="me",
        q="in:inbox to:me -from:me -from:mailer-daemon@googlemail.com",
        maxResults=50,
    ).execute()

    messages = resp.get("messages", [])

    # 2) Keep first message per thread, preserving order (newest first)
    threads_seen = OrderedDict()
    for m in messages:
        msg = (
            svc.users()
            .messages()
            .get(userId="me", id=m["id"], format="metadata", metadataHeaders=["Subject", "From"])
            .execute()
        )
        t_id = msg["threadId"]
        if t_id not in threads_seen:
            threads_seen[t_id] = msg
        if len(threads_seen) >= max_results:
            break

    # 3) Build JSON list
    items = []
    for idx, (t_id, msg) in enumerate(threads_seen.items(), start=1):
        hdrs = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        items.append({
            "idx": idx,
            "threadId": msg["threadId"],
            "from": hdrs.get("From", ""),
            "subject": hdrs.get("Subject", "(No subject)"),
            "snippet": msg.get("snippet", "")[:120],
        })

    return json.dumps(items, ensure_ascii=False)


# Register the tool
register(
    list_recent_emails,
    ToolSchema(
        name="list_recent_emails",
        description="Return a JSON array of the user's latest received inbox threads.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["user_id"],
        },
    ),
)
