from flask import Blueprint, request, jsonify

from utils.logger import get_logger
from services.unified_processor import process_normalized_message
from services.gmail_text import (
    extract_gmail_fields,
    clean_email_text,
    prepare_email_for_classification,
    build_gmail_source_id,
)
from storage.sqlite_db import (
    log_event,
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
    client_name = (payload.get("client_name") or "Email").strip()
    project_name = (payload.get("project_name") or "General").strip()
    list_id = (payload.get("grafik_list_id") or "").strip() or None

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
        "grafik_list_id_hint": list_id,
        "channel_type": None,
        # Preserve legacy Gmail project resolution semantics (incremental refactor):
        "project_resolution_reason": (
            "explicit_project_name" if project_name and project_name != "General" else "fallback_general"
        ),
        "project_confidence": 1.0 if project_name and project_name != "General" else 0.3,
        "needs_project_review": False,
    }

    result = process_normalized_message(normalized)

    # Gmail draft creation remains source-specific for now.
    draft_id = None
    draft_status = "skipped"

    if result.get("reply_policy", {}).get("should_reply") and result.get("reply_policy", {}).get("reply_mode") == "draft_ready" and not result.get("should_create_draft"):
        log.info(
            f"[GMAIL_DRAFT_SKIP:{ingest_source}] source_id={source_id} "
            f"reason=missing_real_gmail_ids_or_forced_skip "
            f"thread_id={thread_id} message_id={message_id}"
        )

    if result.get("should_create_draft") and result.get("reply_text"):
        try:
            from services.gmail_auth import get_gmail_service
            from services.gmail_draft import create_gmail_draft

            gmail_service = get_gmail_service()

            draft_subject = subject
            if subject and not subject.lower().startswith("re:"):
                draft_subject = f"Re: {subject}"
            elif not subject:
                draft_subject = "Re:"

            draft_id = create_gmail_draft(
                service=gmail_service,
                to_email=sender,
                subject=draft_subject,
                reply_text=result.get("reply_text"),
                thread_id=thread_id,
                message_id=message_id,
            )

            draft_status = "created"

            log.info(
                f"[GMAIL_DRAFT:{ingest_source}] source_id={source_id} "
                f"draft_id={draft_id} thread_id={thread_id}"
            )

            log_event(
                source=ingest_source,
                source_id=source_id,
                step="gmail_draft_create",
                status="ok",
                data={
                    "workspace_id": workspace_id,
                    "draft_id": draft_id,
                    "thread_id": thread_id,
                    "reply_type": (result.get("classification") or {}).get("reply_type"),
                },
            )

        except Exception as err:
            draft_status = "error"

            log.exception(
                f"[GMAIL_DRAFT_ERROR:{ingest_source}] source_id={source_id} -> {err}"
            )

            log_event(
                source=ingest_source,
                source_id=source_id,
                step="gmail_draft_create",
                status="error",
                data={
                    "workspace_id": workspace_id,
                    "thread_id": thread_id,
                    "reply_type": (result.get("classification") or {}).get("reply_type"),
                    "error": str(err),
                },
            )

    result["draft_status"] = draft_status
    result["draft_id"] = draft_id

    status = 500 if result.get("status") == "error" else 200
    return jsonify(result), status