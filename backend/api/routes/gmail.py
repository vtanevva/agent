from flask import Blueprint, request, jsonify

from application.orchestrators.event_orchestrator import handle_normalized_event
from application.services.reply_service import maybe_create_gmail_draft
from storage.sqlite_db import get_user_id_for_gmail_address
from utils.logger import get_logger
from services.gmail_text import (
    extract_gmail_fields,
    clean_email_text,
    prepare_email_for_classification,
    build_gmail_source_id,
)

log = get_logger("gmail")
gmail_bp = Blueprint("gmail", __name__)


@gmail_bp.post("/gmail/events")
@gmail_bp.post("/ingest/gmail")
def ingest_gmail():
    payload = request.get_json(silent=True) or {}
    ingest_source = (payload.get("source") or "gmail").strip()
    workspace_id = (payload.get("workspace_id") or "").strip()

    fields = extract_gmail_fields(payload)

    message_id = fields["message_id"]
    thread_id = fields["thread_id"]
    sender = fields["sender"]
    recipient = fields["recipient"]
    subject = fields["subject"]
    body = fields["body"]
    timestamp = fields["timestamp"]

    clean_text_value = clean_email_text(subject, body)

    log.info(
        f"[GMAIL_DEBUG:{ingest_source}] "
        f"workspace_id={workspace_id} "
        f"message_id={message_id} thread_id={thread_id} "
        f"sender={sender} subject={repr(subject[:120])}"
    )

    if not clean_text_value:
        log.info(
            f"[IGNORE:{ingest_source}] reason=empty_email_text message_id={message_id}"
        )
        return jsonify(
            {
                "status": "ignored",
                "reason": "empty_email_text",
                "reply_policy": {
                    "should_reply": False,
                    "reply_mode": "none",
                    "reason": "empty_email_text",
                    "confidence": 1.0,
                    "needs_review": False,
                },
            }
        ), 200

    source_id = build_gmail_source_id(message_id, thread_id, sender, subject)

    text_for_classification = prepare_email_for_classification(subject, body)
    # Callers may still pass ``client_name`` / ``project_name`` for testing;
    # otherwise we let the unified processor's project resolver pick the right
    # project (by name match in text, single-known, or the "General" fallback).
    client_name = (payload.get("client_name") or "Inbox").strip()
    project_name = (payload.get("project_name") or "").strip() or None

    normalized = {
        "source": ingest_source,
        "workspace_id": workspace_id or None,
        "source_id": source_id,
        "channel": sender,
        "thread_id": thread_id,
        "ts": str(timestamp) if timestamp is not None else None,
        "sender": sender,
        "user_id": None,
        "recipient": recipient,
        "subject": subject,
        "raw_text": clean_text_value,
        "text_for_classification": text_for_classification,
        "payload": payload,
        "client_name_hint": client_name,
        "project_name_hint": project_name,
        "channel_type": None,
        "project_resolution_reason": None,
        "project_confidence": None,
        "needs_project_review": False,
    }

    wid = (workspace_id or "").strip().lower()
    if wid:
        owner_uid = get_user_id_for_gmail_address(wid)
        if owner_uid:
            normalized["app_user_id"] = owner_uid

    result = handle_normalized_event(normalized)
    draft_result = maybe_create_gmail_draft(
        ingest_source=ingest_source,
        workspace_id=workspace_id or None,
        source_id=source_id,
        thread_id=thread_id,
        message_id=message_id,
        sender=sender,
        subject=subject,
        result=result,
    )
    result["draft_status"] = draft_result["draft_status"]
    result["draft_id"] = draft_result["draft_id"]

    status = 500 if result.get("status") == "error" else 200
    return jsonify(result), status