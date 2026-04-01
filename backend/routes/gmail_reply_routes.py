from __future__ import annotations

import base64
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, jsonify, request

from services.gmail_auth import get_gmail_service
from services.gmail_message import extract_plain_text, get_header
from services.reply_writer import generate_reply
from storage.sqlite_db import get_conn
from utils.logger import get_logger


log = get_logger("gmail_reply")
gmail_reply_bp = Blueprint("gmail_reply", __name__)


def _safe_str(v: Any) -> str:
    return (str(v) if v is not None else "").strip()


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


def _gmail_connect_error(reason: str) -> Tuple[dict, int]:
    # Keep response shape compatible with existing Expo modals.
    return {"success": False, "action": "connect_google", "error": reason}, 200


def _get_thread_detail(service, thread_id: str) -> Tuple[dict, Optional[str]]:
    """
    Returns (detail, last_message_id)
    """
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    msgs = (thread or {}).get("messages") or []
    if not msgs:
        return {"subject": "", "from": "", "date": "", "body": ""}, None

    # Pick the latest message by internalDate
    def _ts(m: dict) -> int:
        try:
            return int(m.get("internalDate") or 0)
        except Exception:
            return 0

    last = sorted(msgs, key=_ts)[-1]
    payload = last.get("payload") or {}
    headers = payload.get("headers") or []

    subject = get_header(headers, "Subject") or ""
    from_value = get_header(headers, "From") or ""
    date_value = get_header(headers, "Date") or ""
    body = extract_plain_text(payload) or ""

    return {"subject": subject, "from": from_value, "date": date_value, "body": body}, str(last.get("id") or "") or None


def _find_latest_gmail_row_for_thread(thread_id: str) -> Optional[dict]:
    """
    Find the most recent SQLite `messages` row for a Gmail threadId.
    We avoid SQLite JSON queries to keep compatibility.
    """
    thread_id = _safe_str(thread_id)
    if not thread_id:
        return None

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, source, source_id, text, payload_json, classification_type, classification_json, created_at
            FROM messages
            WHERE source = 'gmail'
            ORDER BY id DESC
            LIMIT 2000
            """
        ).fetchall()

    best = None
    for r in rows:
        row = dict(r)
        payload = _safe_json_loads(row.get("payload_json"))
        pid = _safe_str(payload.get("thread_id") or payload.get("threadId") or payload.get("thread_id"))
        if pid == thread_id:
            best = row
            break
    return best


@gmail_reply_bp.post("/api/gmail/thread-detail")
def thread_detail():
    payload = request.get_json(silent=True) or {}
    thread_id = _safe_str(payload.get("thread_id") or payload.get("threadId"))
    if not thread_id:
        return jsonify({"success": False, "error": "missing_thread_id"}), 400

    try:
        service = get_gmail_service()
    except Exception as e:
        body, status = _gmail_connect_error(str(e))
        return jsonify(body), status

    try:
        detail, _last_mid = _get_thread_detail(service, thread_id)
        return jsonify({"success": True, **detail}), 200
    except Exception as e:
        log.exception(f"thread-detail failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@gmail_reply_bp.post("/api/gmail/draft-reply")
def draft_reply():
    payload = request.get_json(silent=True) or {}
    thread_id = _safe_str(payload.get("thread_id") or payload.get("threadId"))
    to_email = _safe_str(payload.get("to"))
    user_points = _safe_str(payload.get("user_points"))
    if not thread_id:
        return jsonify({"success": False, "error": "missing_thread_id"}), 400

    # Best-effort: pull stored suggested reply from SQLite classification.
    row = _find_latest_gmail_row_for_thread(thread_id)
    classification = _safe_json_loads((row or {}).get("classification_json"))
    raw_text = _safe_str((row or {}).get("text"))
    suggested = _safe_str(classification.get("suggested_reply"))

    if suggested and not user_points:
        return jsonify({"success": True, "body": suggested}), 200

    # If we don't have a stored suggestion (or user asked for a specific angle), generate a new one.
    reply_type = _safe_str(classification.get("reply_type")) or "short"
    summary = _safe_str(classification.get("summary")) or None
    sender = _safe_str(classification.get("sender")) or None
    project_name = _safe_str(classification.get("project_name")) or None

    cls_for_prompt = dict(classification or {})
    if user_points:
        cls_for_prompt["user_points"] = user_points

    reply = generate_reply(
        original_text=raw_text or user_points or "",
        reply_type=reply_type,
        summary=summary,
        sender=sender or to_email or None,
        project_name=project_name,
        project_context=None,
        project_update_candidate=None,
        classification=cls_for_prompt,
        channel="email",
    )
    reply = _safe_str(reply)
    if not reply:
        return jsonify({"success": False, "error": "failed_to_generate_draft"}), 500

    return jsonify({"success": True, "body": reply}), 200


@gmail_reply_bp.post("/api/gmail/draft-forward")
def draft_forward():
    payload = request.get_json(silent=True) or {}
    thread_id = _safe_str(payload.get("thread_id") or payload.get("threadId"))
    if not thread_id:
        return jsonify({"success": False, "error": "missing_thread_id"}), 400

    try:
        service = get_gmail_service()
    except Exception as e:
        body, status = _gmail_connect_error(str(e))
        return jsonify(body), status

    try:
        detail, _last_mid = _get_thread_detail(service, thread_id)
        original = _safe_str(detail.get("body"))
        forward_body = f"Forwarding below:\n\n---\n{original}"
        return jsonify({"success": True, "body": forward_body}), 200
    except Exception as e:
        log.exception(f"draft-forward failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def _encode_mime_message(msg: MIMEMultipart) -> str:
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return raw


@gmail_reply_bp.post("/api/gmail/reply")
def send_reply():
    payload = request.get_json(silent=True) or {}
    thread_id = _safe_str(payload.get("thread_id") or payload.get("threadId"))
    to_email = _safe_str(payload.get("to"))
    body_text = _safe_str(payload.get("body"))
    if not thread_id or not to_email or not body_text:
        return jsonify({"success": False, "error": "missing_thread_id_to_or_body"}), 400

    try:
        service = get_gmail_service()
    except Exception as e:
        body, status = _gmail_connect_error(str(e))
        return jsonify(body), status

    try:
        detail, last_mid = _get_thread_detail(service, thread_id)
        subject = _safe_str(detail.get("subject"))
        if subject and not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        if not subject:
            subject = "Re:"

        msg = MIMEMultipart()
        msg["To"] = to_email
        msg["Subject"] = subject
        if last_mid:
            msg["In-Reply-To"] = last_mid
            msg["References"] = last_mid
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        raw = _encode_mime_message(msg)
        resp = service.users().messages().send(userId="me", body={"raw": raw, "threadId": thread_id}).execute()
        return jsonify({"success": True, "id": resp.get("id")}), 200
    except Exception as e:
        log.exception(f"reply send failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@gmail_reply_bp.post("/api/gmail/forward")
def forward():
    payload = request.get_json(silent=True) or {}
    thread_id = _safe_str(payload.get("thread_id") or payload.get("threadId"))
    to_email = _safe_str(payload.get("to"))
    body_text = _safe_str(payload.get("body"))
    if not thread_id or not to_email:
        return jsonify({"success": False, "error": "missing_thread_id_or_to"}), 400

    try:
        service = get_gmail_service()
    except Exception as e:
        body, status = _gmail_connect_error(str(e))
        return jsonify(body), status

    try:
        detail, _last_mid = _get_thread_detail(service, thread_id)
        subject = _safe_str(detail.get("subject"))
        if subject and not subject.lower().startswith(("fwd:", "fw:")):
            subject = f"Fwd: {subject}"
        if not subject:
            subject = "Fwd:"

        original = _safe_str(detail.get("body"))
        combined = body_text.strip() + ("\n\n---\n" if body_text.strip() else "") + original

        msg = MIMEMultipart()
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(combined, "plain", "utf-8"))
        raw = _encode_mime_message(msg)
        resp = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return jsonify({"success": True, "id": resp.get("id")}), 200
    except Exception as e:
        log.exception(f"forward send failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


__all__ = ["gmail_reply_bp"]

