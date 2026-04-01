from __future__ import annotations

import json
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from storage.sqlite_db import get_conn
from utils.logger import get_logger


log = get_logger("gmail_triage")
gmail_triage_bp = Blueprint("gmail_triage", __name__)


ALL_CATEGORIES = [
    "urgent",
    "action_items",
    "waiting_for_reply",
    "clients",
    "invoices",
    "normal",
    "notifications",
    "newsletters",
    "promotional",
    "transactional",
    "social",
]


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


def _is_actionable(*, classification_type: Any, classification: dict) -> bool:
    if str(classification_type or "").strip().upper() == "ACTION":
        return True
    return bool(classification.get("has_action") is True or classification.get("has_action") == 1)


def _pick_category(*, actionable: bool, classification: dict) -> str:
    # Minimal mapping: we only need actionable items to render in the UI.
    if actionable:
        return "action_items"

    # If we ever show non-actionable, keep them in 'normal' by default.
    # (Classifier has other categories like status_update, greeting, etc.)
    return "normal"


def _email_row_to_item(row: dict) -> dict:
    payload = _safe_json_loads(row.get("payload_json"))
    cls = _safe_json_loads(row.get("classification_json"))

    # Prefer Gmail payload fields when present.
    thread_id = (
        payload.get("thread_id")
        or payload.get("threadId")
        or payload.get("threadId".lower())
        or payload.get("threadId".upper())
        or payload.get("thread_id".upper())
        or payload.get("threadId")
        or payload.get("thread_id")
    )
    if not thread_id:
        thread_id = payload.get("threadId") or payload.get("thread_id")

    from_value = payload.get("from") or payload.get("sender") or row.get("channel") or ""
    subject = payload.get("subject") or ""
    snippet = payload.get("snippet") or ""
    if not snippet:
        # Build a short snippet from stored message text.
        txt = (row.get("text") or "").strip()
        snippet = txt[:180] + ("..." if len(txt) > 180 else "")

    classification_type = row.get("classification_type")
    actionable = _is_actionable(classification_type=classification_type, classification=cls)
    category = _pick_category(actionable=actionable, classification=cls)

    item = {
        "source": row.get("source"),
        "source_id": row.get("source_id"),
        "threadId": str(thread_id) if thread_id is not None else None,
        "from": from_value,
        "subject": subject,
        "snippet": snippet,
        "ts": row.get("ts"),
        "created_at": row.get("created_at"),
        "classification_type": classification_type,
        "classification": cls,
        # Include both snake_case + camelCase for frontend compatibility
        "has_action": bool(actionable),
        "hasAction": bool(actionable),
        "category": category,
    }
    return item


@gmail_triage_bp.get("/api/gmail/triaged-inbox")
def triaged_inbox():
    user_id = (request.args.get("user_id") or "").strip().lower()
    try:
        max_results = int(request.args.get("max_results") or "100")
    except Exception:
        max_results = 100

    # Optional filter: return only a specific category.
    category_filter = (request.args.get("category_filter") or "").strip().lower() or None

    max_results = max(1, min(max_results, 2000))

    with get_conn() as conn:
        # Pull recent gmail messages; we filter by token email if available in payload.
        rows = conn.execute(
            """
            SELECT
              id,
              source,
              source_id,
              channel,
              ts,
              text,
              payload_json,
              classification_type,
              classification_json,
              created_at
            FROM messages
            WHERE source = 'gmail'
            ORDER BY id DESC
            LIMIT ?
            """,
            (max_results,),
        ).fetchall()

    items: List[dict] = []
    for r in rows:
        row = dict(r)
        item = _email_row_to_item(row)

        # If a user_id was provided and looks like an email, filter to that mailbox when we can.
        if user_id and "@" in user_id:
            payload = _safe_json_loads(row.get("payload_json"))
            email_addr = (payload.get("emailAddress") or payload.get("email_address") or "").strip().lower()
            if email_addr and email_addr != user_id:
                continue

        items.append(item)

    categories: Dict[str, List[dict]] = {k: [] for k in ALL_CATEGORIES}
    for it in items:
        cat = (it.get("category") or "normal").strip().lower()
        if cat not in categories:
            cat = "normal"
        categories[cat].append(it)

    if category_filter:
        categories = {k: (v if k == category_filter else []) for k, v in categories.items()}

    total = sum(len(v) for v in categories.values())
    category_counts = {k: len(v) for k, v in categories.items()}

    return jsonify(
        {
            "success": True,
            "classification_version": "local-sqlite-v1",
            "cached": False,
            "background_worker_triggered": False,
            "total_classified": len(items),
            "total": total,
            "categories": categories,
            "category_counts": category_counts,
        }
    ), 200


@gmail_triage_bp.post("/api/gmail/poll-new")
def poll_new():
    # Local backend already ingests from Pub/Sub; this endpoint is a safe no-op.
    return jsonify({"success": True, "status": "noop"}), 200


@gmail_triage_bp.post("/api/gmail/archive")
def archive():
    # Stub: optimistic UI hides locally. Implement real Gmail archive if needed.
    payload = request.get_json(silent=True) or {}
    return jsonify({"success": True, "thread_id": payload.get("thread_id")}), 200


@gmail_triage_bp.post("/api/gmail/mark-handled")
def mark_handled():
    payload = request.get_json(silent=True) or {}
    return jsonify({"success": True, "thread_id": payload.get("thread_id")}), 200


__all__ = ["gmail_triage_bp"]

