from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import requests

from utils.logger import get_logger

log = get_logger("ai_chat_client")

DEFAULT_AI_URL = "http://127.0.0.1:5055"


def _timeout_s() -> float:
    try:
        return float(os.getenv("AI_SERVICE_TIMEOUT", "120"))
    except ValueError:
        return 120.0


def complete_chat(
    *,
    user_id: str,
    session_id: str,
    user_message: str,
    message_type: Any,
    metadata: Optional[Dict[str, Any]],
) -> Tuple[str, str]:
    """
    Call the out-of-process AI chat service. Returns (intent, reply).
    On failure returns ("general", user-facing fallback message).
    """
    base = (os.getenv("AI_SERVICE_URL") or DEFAULT_AI_URL).rstrip("/")
    url = f"{base}/v1/chat"
    secret = (os.getenv("AI_SERVICE_SECRET") or "").strip()
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-AI-Service-Secret"] = secret

    payload: Dict[str, Any] = {
        "user_id": user_id,
        "session_id": session_id,
        "message": user_message,
        "message_type": message_type,
        "metadata": metadata,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=_timeout_s())
    except requests.RequestException as e:
        log.exception("AI service unreachable url=%s err=%s", url, e)
        return (
            "general",
            "I'm having trouble reaching the assistant service. Is the AI service running?",
        )

    try:
        data = resp.json()
    except Exception:
        log.error("AI service returned non-JSON: %s", (resp.text or "")[:500])
        return "general", "I'm having trouble processing that right now. Please try again."

    if resp.status_code >= 400 or not data.get("success", True):
        log.warning(
            "AI service error status=%s body=%s",
            resp.status_code,
            str(data)[:300],
        )
        reply = data.get("reply")
        if isinstance(reply, str) and reply.strip():
            return (str(data.get("intent") or "general"), reply)
        return "general", "I'm having trouble processing that right now. Please try again."

    intent = str(data.get("intent") or "general")
    reply = str(data.get("reply") or "")
    return intent, reply
