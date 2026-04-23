from __future__ import annotations

from typing import Any

from application.services.thread_service import store_chat_message
from application.services.calendar_meeting_action import try_create_meeting_from_chat
from services.ai_chat_client import complete_chat


def handle_chat_turn(
    *,
    user_id: str,
    session_id: str,
    user_message: str,
    message_type: Any,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    store_chat_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        text=user_message,
        extra={"message_type": message_type, "metadata": metadata} if (message_type or metadata) else None,
    )

    shortcut_reply = try_create_meeting_from_chat(user_message, metadata)
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

