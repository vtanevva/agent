from __future__ import annotations

import io
import os
from typing import Any

from flask import Blueprint, jsonify, request

from application.orchestrators.chat_orchestrator import handle_chat_turn
from application.services.thread_service import (
    list_chat_sessions,
    load_chat_session_messages,
)
from utils.logger import get_logger


log = get_logger("chat_api")
chat_api_bp = Blueprint("chat_api", __name__)


def _safe_str(v: Any) -> str:
    return (str(v) if v is not None else "").strip()


@chat_api_bp.post("/api/chat")
def api_chat():
    """
    Unified chat endpoint:
    - generates reply via AI chat service (HTTP: AI_SERVICE_URL, default :5055)
    - persists conversation into SQLite (/backend) as source='chat'
    """
    payload = request.get_json(silent=True) or {}
    user_id = _safe_str(payload.get("user_id") or payload.get("userId"))
    session_id = _safe_str(payload.get("session_id") or payload.get("sessionId"))
    user_message = payload.get("message") or payload.get("text") or payload.get("user_message") or ""
    user_message = str(user_message or "")

    message_type = payload.get("message_type") or payload.get("messageType")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None

    if not user_id or not session_id:
        return jsonify({"success": False, "error": "missing_user_id_or_session_id"}), 400

    result = handle_chat_turn(
        user_id=user_id,
        session_id=session_id,
        user_message=user_message,
        message_type=message_type,
        metadata=metadata,
    )
    return jsonify({"success": True, "intent": result["intent"], "reply": result["reply"]}), 200


@chat_api_bp.post("/api/session_chat")
def session_chat():
    payload = request.get_json(silent=True) or {}
    user_id = _safe_str(payload.get("user_id") or payload.get("userId"))
    session_id = _safe_str(payload.get("session_id") or payload.get("sessionId"))
    if not user_id or not session_id:
        return jsonify({"chat": []}), 200

    return jsonify({"chat": load_chat_session_messages(user_id=user_id, session_id=session_id)}), 200


@chat_api_bp.post("/api/sessions-log")
def sessions_log():
    payload = request.get_json(silent=True) or {}
    user_id = _safe_str(payload.get("user_id") or payload.get("userId"))
    if not user_id:
        return jsonify({"sessions": []}), 200

    return jsonify({"sessions": list_chat_sessions(user_id=user_id)}), 200


__all__ = ["chat_api_bp"]

