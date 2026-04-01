from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from flask import Blueprint, jsonify, request

from storage.sqlite_db import get_conn, utc_iso
from utils.logger import get_logger


log = get_logger("chat_api")
chat_api_bp = Blueprint("chat_api", __name__)


def _safe_str(v: Any) -> str:
    return (str(v) if v is not None else "").strip()


def _insert_chat_message(*, user_id: str, session_id: str, role: str, text: str, extra: dict | None = None) -> None:
    user_id = _safe_str(user_id)
    session_id = _safe_str(session_id)
    role = _safe_str(role) or "user"
    text = str(text or "")

    if not user_id or not session_id:
        return

    now = utc_iso()
    payload = {"user_id": user_id, "session_id": session_id, "role": role}
    if extra:
        payload.update(extra)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO messages
              (source, source_id, channel, ts, user, text, payload_json, created_at)
            VALUES
              (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "chat",
                f"chat:{user_id}:{session_id}:{uuid4().hex[:12]}",
                session_id,
                now,
                user_id,
                text,
                json.dumps(payload, ensure_ascii=False),
                now,
            ),
        )
        conn.commit()


@chat_api_bp.post("/api/chat")
def api_chat():
    """
    Unified chat endpoint:
    - generates reply using the existing orchestrator (from /app)
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

    _insert_chat_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        text=user_message,
        extra={"message_type": message_type, "metadata": metadata} if (message_type or metadata) else None,
    )

    try:
        from app.agents.orchestrator import get_orchestrator

        orch = get_orchestrator()
        intent, reply = orch.handle_chat(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            metadata=metadata,
            message_type=message_type,
        )
    except Exception as e:
        log.exception(f"Orchestrator error: {e}")
        intent, reply = "general", "I'm having trouble processing that right now. Please try again."

    _insert_chat_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        text=reply,
        extra={"intent": intent} if intent else None,
    )

    return jsonify({"success": True, "intent": intent, "reply": reply}), 200


@chat_api_bp.post("/api/session_chat")
def session_chat():
    payload = request.get_json(silent=True) or {}
    user_id = _safe_str(payload.get("user_id") or payload.get("userId"))
    session_id = _safe_str(payload.get("session_id") or payload.get("sessionId"))
    if not user_id or not session_id:
        return jsonify({"chat": []}), 200

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT text, payload_json, created_at
            FROM messages
            WHERE source = 'chat' AND user = ? AND channel = ?
            ORDER BY id ASC
            """,
            (user_id, session_id),
        ).fetchall()

    chat = []
    for r in rows:
        role = "user"
        try:
            obj = json.loads(r["payload_json"]) if r["payload_json"] else {}
            role = (obj.get("role") or "user").strip().lower()
        except Exception:
            role = "user"
        chat.append({"role": role, "text": r["text"] or ""})

    return jsonify({"chat": chat}), 200


@chat_api_bp.post("/api/sessions-log")
def sessions_log():
    payload = request.get_json(silent=True) or {}
    user_id = _safe_str(payload.get("user_id") or payload.get("userId"))
    if not user_id:
        return jsonify({"sessions": []}), 200

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT channel AS session_id, MAX(id) AS last_id
            FROM messages
            WHERE source = 'chat' AND user = ?
            GROUP BY channel
            ORDER BY last_id DESC
            LIMIT 200
            """,
            (user_id,),
        ).fetchall()

    sessions = [r["session_id"] for r in rows if r["session_id"]]
    return jsonify({"sessions": sessions}), 200


__all__ = ["chat_api_bp"]

