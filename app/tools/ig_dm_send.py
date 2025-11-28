"""
Tool: send_ig_dm — send a Direct Message from the user’s Instagram
business/creator account to another IG user.

POST https://graph.facebook.com/v19.0/{ig_user_id}/messages
Body:
{
  "messaging_product": "instagram",
  "recipient": { "id": "<recipient_ig_id>" },
  "message":   { "text": "<body text>" }
}
"""

import json
from datetime import datetime

import requests

# Tool registry removed - agents call functions directly now
from app.utils.tool_registry import register, ToolSchema
from app.db.collections import get_tokens_collection

def _get_auth(user_id: str):
    """Get Instagram authentication from MongoDB"""
    tokens = get_tokens_collection()
    if tokens is None:
        raise RuntimeError(
            "MongoDB is not available. Instagram features are disabled. "
            "Please set up a database connection."
        )
    
    try:
        doc = tokens.find_one({"user_id": user_id}, {"instagram": 1})
        if not doc or "instagram" not in doc:
            raise FileNotFoundError(
                f"Instagram token for user '{user_id}' not found. "
                "Ask the user to connect Instagram first."
            )
        instagram_data = doc["instagram"]
        return instagram_data["ig_user_id"], instagram_data["access_token"]
    except Exception as e:
        raise RuntimeError(f"Failed to load Instagram credentials: {e}")

def send_ig_dm(user_id: str, recipient_id: str, text: str):
    ig_uid, token = _get_auth(user_id)

    url = f"https://graph.facebook.com/v19.0/{ig_uid}/messages"
    payload = {
        "messaging_product": "instagram",
        "recipient": {"id": recipient_id},
        "message": {"text": text},
    }
    resp = requests.post(url, params={"access_token": token}, json=payload, timeout=10)
    if resp.status_code >= 300:
        raise RuntimeError(f"Instagram API error {resp.status_code}: {resp.text}")

    msg_id = resp.json().get("id")
    ts = datetime.utcnow().isoformat(timespec="seconds")
    return f"DM sent (id={msg_id}) at {ts} UTC."

# ── register -----------------------------------------------------------------

register(
    send_ig_dm,
    ToolSchema(
        name="send_ig_dm",
        description="Send an Instagram Direct Message from the user's IG business account.",
        parameters={
            "type": "object",
            "properties": {
                "user_id":      {"type": "string"},
                "recipient_id": {"type": "string", "description": "Instagram user ID of the recipient"},
                "text":         {"type": "string"},
            },
            "required": ["user_id", "recipient_id", "text"],
        },
    ),
)
