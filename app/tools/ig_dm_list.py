"""
Tool: list_recent_ig_dms — return latest incoming DM threads.

Returns JSON array like:
[
  { "idx": 1,
    "threadId": "t_178746392...",
    "recipientId": "17841400000000",
    "from": "datacamp",
    "snippet": "Hi, thanks for following …" },
  …
]
"""

import os, pickle, json, requests
from collections import OrderedDict
from app.agent_core.tool_registry import register, ToolSchema

TOKEN_PATH = "tokens/{user_id}_ig.pkl"

def _get_auth(user_id: str):
    path = TOKEN_PATH.format(user_id=user_id)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Instagram token for user '{user_id}' not found. "
            "Ask the user to connect Instagram first."
        )
    with open(path, "rb") as f:
        data = pickle.load(f)           # {page_id, ig_user_id, access_token}
    return data["page_id"], data["access_token"]

def list_recent_ig_dms(user_id: str, max_results: int = 5):
    page_id, token = _get_auth(user_id)

    # 1) Fetch conversations ordered by newest
    url = f"https://graph.facebook.com/v19.0/{page_id}/conversations"
    params = {
        "fields": "participants,messages.limit(1){id,from,text}",
        "limit": 25,
        "access_token": token,
    }
    convs = requests.get(url, params=params, timeout=10).json().get("data", [])

    # 2) Deduplicate by thread, keep only incoming (not sent by page)
    items, seen = [], OrderedDict()
    for conv in convs:
        msg = conv.get("messages", {}).get("data", [])[0]  # newest
        if not msg:
            continue
        sender_id = msg["from"]["id"]
        if sender_id == page_id:            # skip outgoing
            continue
        t_id = conv["id"]
        if t_id in seen:
            continue
        seen[t_id] = True
        items.append(
            {
                "idx": len(items) + 1,
                "threadId": t_id,
                "recipientId": sender_id,
                "from": msg["from"].get("name", sender_id),
                "snippet": msg.get("text", "")[:120],
            }
        )
        if len(items) >= max_results:
            break

    return json.dumps(items, ensure_ascii=False)

# ── register -----------------------------------------------------------------

register(
    list_recent_ig_dms,
    ToolSchema(
        name="list_recent_ig_dms",
        description="Return a JSON array of the user's latest incoming IG DM threads.",
        parameters={
            "type": "object",
            "properties": {
                "user_id":     {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["user_id"],
        },
    ),
)
