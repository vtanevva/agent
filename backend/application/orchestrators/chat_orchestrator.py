from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from application.orchestrators.event_orchestrator import handle_normalized_event
from application.services.calendar_meeting_action import try_create_meeting_from_chat
from application.services.chat_task_action import try_create_task_from_chat
from application.services.thread_service import store_chat_message
from utils.logger import get_logger
from services.ai_chat_client import complete_chat
from services.chat_project_hint import safe_project_hint

log = get_logger("chat_orchestrator")


def _ingest_chat_for_project_tracking(
    *,
    user_id: str,
    session_id: str,
    user_message: str,
    metadata: dict[str, Any] | None,
) -> None:
    """
    Run chat text through unified ingest so project mention resolution/creation matches Gmail/Slack.
    Best-effort only; must never block the chat reply.
    """
    project_hint = safe_project_hint(user_message)
    normalized = {
        "source": "chat",
        "workspace_id": None,
        "source_id": f"chat:{session_id}:{uuid4().hex}",
        "channel": f"chat:{user_id}",
        "thread_id": session_id,
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "sender": user_id,
        "user_id": user_id,
        "recipient": None,
        "subject": None,
        "raw_text": user_message,
        "text_for_classification": user_message,
        "payload": {
            "now_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "project_name": project_hint,
            "metadata": metadata or {},
            "skip_draft": True,
        },
        "client_name_hint": "Chat",
        "project_name_hint": project_hint,
        "grafik_list_id_hint": None,
        "channel_type": "chat",
    }
    handle_normalized_event(normalized)


def handle_chat_turn(
    *,
    user_id: str,
    session_id: str,
    user_message: str,
    message_type: Any,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        _ingest_chat_for_project_tracking(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            metadata=metadata,
        )
    except Exception as e:
        log.warning("Chat project ingest skipped: %s", e)

    store_chat_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        text=user_message,
        extra={"message_type": message_type, "metadata": metadata} if (message_type or metadata) else None,
    )

    skip_shortcuts = False
    if isinstance(metadata, dict):
        _dp = metadata.get("draft_polish")
        skip_shortcuts = isinstance(_dp, dict) and bool(str(_dp.get("draft") or "").strip())

    shortcut_reply = None
    if not skip_shortcuts:
        shortcut_reply = try_create_meeting_from_chat(user_message, metadata)
    if not shortcut_reply and not skip_shortcuts:
        shortcut_reply = try_create_task_from_chat(
            user_message, metadata, session_id=session_id
        )
    if shortcut_reply:
        intent, reply = "general", shortcut_reply
    else:
        intent, reply = complete_chat(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            message_type=message_type,
            metadata=metadata,
        )

    store_chat_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        text=reply,
        extra={"intent": intent} if intent else None,
    )

    return {"intent": intent, "reply": reply}

