from __future__ import annotations

import json
from typing import Any, List

from flask import Blueprint, jsonify, request

from storage.sqlite_db import get_conn
from utils.logger import get_logger


log = get_logger("action_items")
action_items_bp = Blueprint("action_items", __name__)


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


def _as_actionable(*, classification_type: Any, classification: dict) -> bool:
    if str(classification_type or "").strip().upper() == "ACTION":
        return True
    return bool(classification.get("has_action") is True or classification.get("has_action") == 1)


def _text_preview(v: Any, limit: int = 180) -> str:
    s = (str(v) if v is not None else "").strip()
    if not s:
        return ""
    return s[:limit] + ("..." if len(s) > limit else "")


def _row_to_item(row: dict) -> dict:
    payload = _safe_json_loads(row.get("payload_json"))
    cls = _safe_json_loads(row.get("classification_json"))

    source = row.get("source") or ""

    # "threadId" is what the Expo UI expects for list identity/actions.
    if source == "gmail":
        thread_id = payload.get("thread_id") or payload.get("threadId") or payload.get("thread_id")
    elif source == "slack":
        thread_id = payload.get("thread_ts") or payload.get("threadTs") or payload.get("ts") or row.get("ts")
    else:
        thread_id = payload.get("thread_id") or payload.get("thread_ts") or row.get("ts")

    # Always fall back to source_id to keep IDs stable.
    thread_id = thread_id or row.get("source_id")

    from_value = (
        payload.get("from")
        or payload.get("sender")
        or payload.get("user")
        or row.get("user")
        or row.get("channel")
        or ""
    )

    subject = payload.get("subject") or cls.get("title") or ""
    snippet = payload.get("snippet") or _text_preview(payload.get("text") or row.get("text") or "")

    classification_type = row.get("classification_type")
    actionable = _as_actionable(classification_type=classification_type, classification=cls)

    return {
        "source": source,
        "source_id": row.get("source_id"),
        "threadId": str(thread_id) if thread_id is not None else None,
        "from": from_value,
        "subject": subject,
        "snippet": snippet,
        "channel": row.get("channel"),
        "user": row.get("user"),
        "ts": row.get("ts"),
        "created_at": row.get("created_at"),
        "classification_type": classification_type,
        "classification": cls,
        "has_action": bool(actionable),
        "hasAction": bool(actionable),
    }


@action_items_bp.get("/api/action-items")
def list_action_items():
    """
    Unified action items across all sources (gmail, slack, ...).

    Returns a flat list for the Expo UI:
      { success: true, total: N, items: [...] }
    """
    user_id = (request.args.get("user_id") or "").strip().lower()
    # Only scope by mailbox/workspace when user_id looks like an email.
    # In local/dev the app often uses short ids like "v".
    should_scope_workspace = bool(user_id and "@" in user_id)
    try:
        limit = int(request.args.get("limit") or request.args.get("max_results") or "100")
    except Exception:
        limit = 100
    limit = max(1, min(limit, 2000))

    fetch_n = min(max(limit * 10, 500), 8000)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              id,
              source,
              source_id,
              channel,
              ts,
              user,
              text,
              payload_json,
              classification_type,
              classification_json,
              created_at
            FROM messages
            ORDER BY id DESC
            LIMIT ?
            """,
            (fetch_n,),
        ).fetchall()

    items: List[dict] = []
    for r in rows:
        row = dict(r)
        payload = _safe_json_loads(row.get("payload_json"))
        cls = _safe_json_loads(row.get("classification_json"))

        # Optional scoping: if user_id matches a workspace/mailbox in payload.
        if should_scope_workspace:
            workspace = (
                (payload.get("workspace_id") or payload.get("workspaceId") or payload.get("emailAddress") or "")
            )
            workspace = str(workspace or "").strip().lower()
            if workspace and workspace != user_id:
                continue

        if not _as_actionable(classification_type=row.get("classification_type"), classification=cls):
            continue

        items.append(_row_to_item(row))
        if len(items) >= limit:
            break

    return jsonify({"success": True, "total": len(items), "items": items}), 200


@action_items_bp.post("/api/action-items/archive")
def archive_action_item():
    # Placeholder (no-op). The UI hides items optimistically.
    payload = request.get_json(silent=True) or {}
    return jsonify({"success": True, "thread_id": payload.get("thread_id")}), 200


@action_items_bp.post("/api/action-items/done")
def done_action_item():
    # Placeholder (no-op). The UI hides items optimistically.
    payload = request.get_json(silent=True) or {}
    return jsonify({"success": True, "thread_id": payload.get("thread_id")}), 200


__all__ = ["action_items_bp"]

