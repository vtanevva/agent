from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from storage.sqlite_db import get_conn, utc_iso


def _safe_str(value: Any) -> str:
    return (str(value) if value is not None else "").strip()


def store_chat_message(
    *,
    user_id: str,
    session_id: str,
    role: str,
    text: str,
    extra: dict | None = None,
) -> None:
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


def load_chat_session_messages(*, user_id: str, session_id: str) -> list[dict[str, str]]:
    user_id = _safe_str(user_id)
    session_id = _safe_str(session_id)
    if not user_id or not session_id:
        return []

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

    chat: list[dict[str, str]] = []
    for row in rows:
        role = "user"
        try:
            obj = json.loads(row["payload_json"]) if row["payload_json"] else {}
            role = (obj.get("role") or "user").strip().lower()
        except Exception:
            role = "user"
        chat.append({"role": role, "text": row["text"] or ""})
    return chat


def list_chat_sessions(*, user_id: str, limit: int = 200) -> list[str]:
    user_id = _safe_str(user_id)
    if not user_id:
        return []

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT channel AS session_id, MAX(id) AS last_id
            FROM messages
            WHERE source = 'chat' AND user = ?
            GROUP BY channel
            ORDER BY last_id DESC
            LIMIT ?
            """,
            (user_id, int(limit)),
        ).fetchall()

    return [row["session_id"] for row in rows if row["session_id"]]

