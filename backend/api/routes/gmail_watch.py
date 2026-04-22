from __future__ import annotations

import os
from typing import Any

from flask import Blueprint, jsonify, request

from services.gmail_auth import get_gmail_service
from services.gmail_pubsub import start_watch, stop_watch
from storage.sqlite_db import get_gmail_watch_state
from utils.logger import get_logger


log = get_logger("gmail_watch")
gmail_watch_bp = Blueprint("gmail_watch", __name__)


def _safe_str(v: Any) -> str:
    return (str(v) if v is not None else "").strip()


@gmail_watch_bp.get("/api/gmail/labels")
def list_gmail_labels():
    """
    Convenience endpoint for configuring label-based watches.
    Returns Gmail label {id, name} pairs for the authorized account.
    """
    try:
        service = get_gmail_service()
    except Exception as e:
        return jsonify({"success": False, "action": "connect_google", "error": str(e)}), 200

    try:
        resp = service.users().labels().list(userId="me").execute()
        labels = resp.get("labels") or []
        out = [{"id": str(l.get("id") or ""), "name": str(l.get("name") or "")} for l in labels]
        out = [x for x in out if x["id"] and x["name"]]
        out.sort(key=lambda x: x["name"].lower())
        return jsonify({"success": True, "labels": out, "total": len(out)}), 200
    except Exception as e:
        log.exception(f"labels list failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@gmail_watch_bp.get("/api/gmail/watch/state")
def gmail_watch_state():
    email_address = _safe_str(request.args.get("email_address"))
    if not email_address:
        return jsonify({"success": False, "error": "missing_email_address"}), 400

    state = get_gmail_watch_state(email_address)
    if not state:
        return jsonify({"success": True, "state": None}), 200

    return jsonify({"success": True, "state": state}), 200


@gmail_watch_bp.post("/api/gmail/watch/start")
def gmail_watch_start():
    """
    Starts (or restarts) a Gmail watch for the token account.

    Inputs:
      - topic: optional; defaults to env GMAIL_PUBSUB_TOPIC
      - email_address: optional; if provided must match the token account email
      - label_ids: optional list of label IDs OR label names; if omitted, uses env GMAIL_WATCH_LABELS
    """
    payload = request.get_json(silent=True) or {}
    topic = _safe_str(payload.get("topic")) or _safe_str(os.getenv("GMAIL_PUBSUB_TOPIC"))
    email_address = _safe_str(payload.get("email_address"))
    label_ids = payload.get("label_ids") or payload.get("labels") or None

    if not topic:
        return jsonify({"success": False, "error": "missing_topic", "hint": "set GMAIL_PUBSUB_TOPIC"}), 400

    # Accept a single string or list for labels.
    if isinstance(label_ids, str):
        label_ids = [label_ids]
    if label_ids is not None and not isinstance(label_ids, list):
        label_ids = None

    try:
        resp = start_watch(
            email_address=email_address,
            topic=topic,
            label_ids=[_safe_str(x) for x in (label_ids or []) if _safe_str(x)] or None,
        )
        return jsonify(resp), 200
    except Exception as e:
        log.exception(f"watch start failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@gmail_watch_bp.post("/api/gmail/watch/stop")
def gmail_watch_stop():
    try:
        resp = stop_watch()
        return jsonify(resp), 200
    except Exception as e:
        log.exception(f"watch stop failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


__all__ = ["gmail_watch_bp"]

