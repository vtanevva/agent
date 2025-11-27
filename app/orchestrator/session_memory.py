import json
from typing import List, Dict, Any

from app.utils.db_utils import get_conversations_collection


def load_session_memory(
    user_id: str,
    session_id: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Load the last N messages for a (user_id, session_id) pair and convert them
    into OpenAI Chat Completions message format.

    Returns a list like: [{"role": "user" | "assistant", "content": "..."}]
    """
    session_memory: List[Dict[str, Any]] = []
    conversations = get_conversations_collection()
    if conversations is None:
        return session_memory

    try:
        chat_doc = conversations.find_one({"user_id": user_id, "session_id": session_id})
        if chat_doc and "messages" in chat_doc:
            for msg in chat_doc["messages"][-limit:]:
                role = "assistant" if msg.get("role") == "bot" else msg.get("role", "user")
                text = msg.get("text", "")
                if not isinstance(text, str):
                    try:
                        text = json.dumps(text, ensure_ascii=False)
                    except Exception:
                        text = str(text)
                session_memory.append({"role": role, "content": text})
    except Exception as e:
        print(f"[ERROR] Failed to load session history: {e}", flush=True)

    return session_memory


