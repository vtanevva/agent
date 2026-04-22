from flask import Blueprint, request, jsonify

from utils.logger import get_logger
from application.orchestrators.event_orchestrator import handle_normalized_event
from integrations.grafik import resolve_grafik_list_id_from_channel
from services.slack_text import (
    extract_payload_parts,
    extract_text,
    extract_channel,
    extract_ts,
    extract_user,
    clean_text,
    prepare_text_for_classification,
    should_ignore_event,
    build_fallback_source_id,
)

log = get_logger("ingest")
slack_bp = Blueprint("slack", __name__)


@slack_bp.post("/slack/events")
@slack_bp.post("/ingest/slack")
def ingest_slack():
    payload = request.get_json(silent=True) or {}
    ingest_source = (payload.get("source") or "slack").strip()
    workspace_id = (payload.get("workspace_id") or payload.get("team_id") or "").strip()

    if payload.get("type") == "url_verification" and payload.get("challenge"):
        return jsonify({"challenge": payload["challenge"]}), 200

    is_slack_events_api = payload.get("type") in {"event_callback", "url_verification"}
    is_flat_payload = (
        not payload.get("type")
        and (
            payload.get("text")
            or payload.get("channel")
            or payload.get("channel_id")
        )
    )

    event, container, message = extract_payload_parts(payload)

    if is_flat_payload:
        text = (payload.get("text") or "").strip()
        channel = (payload.get("channel") or payload.get("channel_id") or "").strip()
        ts = str(payload.get("ts") or payload.get("message_ts") or payload.get("event_ts") or "").strip()
        user_id = (payload.get("user_id") or payload.get("user") or "").strip()
        user = user_id
        clean_text_value = clean_text(text)

        log.info(
            f"[SLACK_DEBUG:{ingest_source}] raw_type=None event_type=None channel_type=None "
            f"subtype=None workspace_id={workspace_id} channel={channel} user_id={user_id} "
            f"text_preview={repr(text[:120])}"
        )

        if not clean_text_value:
            log.info(
                f"[IGNORE:{ingest_source}] reason=empty_text channel={channel} user_id={user_id}"
            )
            return jsonify(
                {
                    "status": "ignored",
                    "reason": "empty_text",
                    "reply_policy": {
                        "should_reply": False,
                        "reply_mode": "none",
                        "reason": "empty_text",
                        "confidence": 1.0,
                        "needs_review": False,
                    },
                }
            ), 200

    else:
        raw_event_type = payload.get("type")

        if raw_event_type == "event_callback" and not event:
            log.info(f"[IGNORE:{ingest_source}] empty event_callback payload")
            return jsonify(
                {
                    "status": "ignored",
                    "reason": "empty_event",
                    "reply_policy": {
                        "should_reply": False,
                        "reply_mode": "none",
                        "reason": "empty_event",
                        "confidence": 1.0,
                        "needs_review": False,
                    },
                }
            ), 200

        text = extract_text(payload, event, message)
        channel = extract_channel(payload, event, container)
        ts = extract_ts(payload, event)
        user, user_id = extract_user(payload, event)
        clean_text_value = clean_text(text)

        log.info(
            f"[SLACK_DEBUG:{ingest_source}] raw_type={payload.get('type')} "
            f"event_type={event.get('type')} "
            f"channel_type={event.get('channel_type')} "
            f"subtype={event.get('subtype')} "
            f"workspace_id={workspace_id} channel={channel} user_id={user_id} "
            f"text_preview={repr(text[:120])}"
        )

        should_ignore, reason = should_ignore_event(event, clean_text_value)
        if should_ignore:
            log.info(
                f"[IGNORE:{ingest_source}] reason={reason} "
                f"channel={channel} user_id={user_id} text_preview={repr(text[:120])}"
            )
            return jsonify(
                {
                    "status": "ignored",
                    "reason": reason,
                    "reply_policy": {
                        "should_reply": False,
                        "reply_mode": "none",
                        "reason": "ignored_event",
                        "confidence": 1.0,
                        "needs_review": False,
                    },
                }
            ), 200

    if channel and ts:
        source_id = f"{channel}:{ts}"
    else:
        source_id = build_fallback_source_id(channel, user_id, clean_text_value)

    text_for_classification = prepare_text_for_classification(clean_text_value)

    log.info(
        f"[CLASSIFY_INPUT_RAW:{ingest_source}] source_id={source_id} text={repr(clean_text_value)}"
    )
    log.info(
        f"[CLASSIFY_INPUT_CLEAN:{ingest_source}] source_id={source_id} "
        f"text={repr(text_for_classification)}"
    )
    list_id, client_name, routed_project_name = resolve_grafik_list_id_from_channel(channel)

    normalized = {
        "source": ingest_source,
        "workspace_id": workspace_id or None,
        "source_id": source_id,
        "channel": channel,
        "thread_id": None,
        "ts": str(ts) if ts is not None else None,
        "sender": user_id or user,
        "user_id": user_id,
        "recipient": None,
        "subject": None,
        "raw_text": clean_text_value,
        "text_for_classification": text_for_classification,
        "payload": payload,
        "client_name_hint": client_name,
        "project_name_hint": routed_project_name,
        "grafik_list_id_hint": list_id,
        "channel_type": (event.get("channel_type") if event else None),
    }

    result = handle_normalized_event(normalized)

    # Keep response shape stable across sources (draft fields are Gmail-specific,
    # but clients/tests may rely on them existing).
    result.setdefault("should_create_draft", False)
    result.setdefault("draft_status", None)
    result.setdefault("draft_id", None)

    status = 500 if result.get("status") == "error" else 200
    return jsonify(result), status