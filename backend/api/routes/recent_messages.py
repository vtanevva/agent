"""
Recent rows from SQLite ``messages`` (for AI / tools to summarize ingested mail without re-classifying).
"""

from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, jsonify, request

from storage.sqlite_db import get_conn
from utils.logger import get_logger

log = get_logger("recent_messages")
recent_messages_bp = Blueprint("recent_messages", __name__)


def _safe_json_loads(v: Any) -> dict:
    if not v:
        return {}
    if isinstance(v, dict):
        return v
    if not isinstance(v, str):
        return {}
    try:
        obj = json.loads(v)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


@recent_messages_bp.get("/api/messages/recent")
def list_recent_messages():
    """
    Latest ingested messages (default: Gmail only), newest first.

    Query: ``user_id`` (optional, reserved), ``limit`` (1–100), ``source`` (e.g. ``gmail``).
    """
    try:
        limit = int(request.args.get("limit") or "25")
    except Exception:
        limit = 25
    limit = max(1, min(limit, 100))

    src_filter = (request.args.get("source") or "gmail").strip().lower()
    if src_filter in ("any", "all", "*"):
        src_filter = ""

    with get_conn() as conn:
        if src_filter:
            rows = conn.execute(
                """
                SELECT id, source, source_id, channel, ts, user, text, payload_json, created_at
                FROM messages
                WHERE source = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (src_filter, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, source, source_id, channel, ts, user, text, payload_json, created_at
                FROM messages
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    items = []
    for r in rows:
        row = dict(r)
        payload = _safe_json_loads(row.get("payload_json"))
        subject = (payload.get("subject") or "").strip()
        from_addr = (
            (payload.get("from") or payload.get("sender") or row.get("user") or row.get("channel") or "")).strip()
        snippet = (row.get("text") or payload.get("snippet") or payload.get("text") or "")[:240]
        items.append(
            {
                "id": row.get("id"),
                "source": row.get("source"),
                "source_id": row.get("source_id"),
                "subject": subject or "(no subject)",
                "from": from_addr,
                "snippet": snippet.strip(),
                "ts": row.get("ts") or row.get("created_at"),
            }
        )

    log.info("[recent_messages] returned count=%s source_filter=%s", len(items), src_filter or "*")
    return jsonify({"success": True, "total": len(items), "items": items}), 200
