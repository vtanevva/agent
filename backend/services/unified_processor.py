from __future__ import annotations

from typing import Any

from utils.logger import get_logger

from integrations.grafik import create_grafik_task
from services.classifier_ai import classify
from services.classification_context import build_classification_input
from services.client_routing import ensure_client
from services.continuity_context import build_continuity_context
from services.follow_up_detector import detect_follow_up_candidate
from services.follow_up_manager import create_follow_up_from_candidate
from services.importance_scoring import score_message_importance
from services.scheduling_awareness import analyze_scheduling_signals
from services.project_context_updater import update_project_context_from_candidate
from services.project_resolution import resolve_project_for_client
from services.project_update_extractor import extract_project_updates
from services.reply_policy import decide_reply_policy
from services.reply_writer import generate_reply
from services.task_linker import find_existing_task_for_message
from services.metrics_tracker import build_metrics_event

from storage.sqlite_db import (
    attach_message_context,
    get_message_context_for_source_id,
    get_project_context,
    insert_message_if_new,
    insert_metrics_event,
    log_event,
    upsert_task,
)


log = get_logger("unified_processor")


def _empty_processing_result(*, source_id: str | None, list_id: str | None) -> dict[str, Any]:
    return {
        "status": "error",
        "source_id": source_id,
        "classification": {},
        "client_name": None,
        "project_name": None,
        "client_id": None,
        "project_id": None,
        "project_resolution_reason": None,
        "project_confidence": None,
        "needs_project_review": False,
        "continuity_context": build_continuity_context(client_id=None, project_id=None),
        "importance_result": score_message_importance(classification={}, continuity_context=build_continuity_context(client_id=None, project_id=None)),
        "scheduling_result": analyze_scheduling_signals(clean_text="", classification={}, now_utc=None),
        "project_update_candidate": {},
        "project_context_update_result": None,
        "updated_project_context": None,
        "follow_up_candidate": {},
        "follow_up_created": False,
        "follow_up_id": None,
        "task_link_result": {},
        "task_link_skipped": False,
        "task_link_skip_reason": None,
        "reply_policy": {
            "should_reply": False,
            "reply_mode": "none",
            "reason": "error",
            "confidence": 0.0,
            "needs_review": True,
        },
        "reply_text": None,
        "should_create_reply": False,
        "should_create_draft": False,
        "draft_status": None,
        "draft_id": None,
        "grafik_task_id": None,
        "linked_grafik_task_id": None,
        "list_id": list_id,
        "error": None,
    }


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _norm_source(source: str | None) -> str:
    s = (source or "").strip().lower()
    return s if s else "unknown"


def _allowed_reply_type(value: Any) -> str:
    reply_type = str(value or "none").strip().lower()
    if reply_type not in {"none", "short", "time_relevant", "context_relevant"}:
        return "none"
    return reply_type


def _as_bool(value: Any) -> bool:
    return bool(value is True or value == 1 or str(value).strip().lower() in {"true", "1", "yes", "y"})


def process_normalized_message(normalized: dict) -> dict[str, Any]:
    """
    Unified, shared orchestration layer.

    Source adapters are responsible for:
      - validating provider payloads
      - ignoring provider-specific events
      - producing a normalized message dict (plus optional hints/overrides)

    This function is responsible for:
      - dedup + shared logging
      - client/project resolution
      - project context fetch
      - classification + enrichment
      - project memory updates
      - follow-up detection + creation
      - task linking
      - reply policy + reply text generation
      - Grafik task creation decision + creation
    """
    source = _norm_source(normalized.get("source"))
    workspace_id = _safe_str(normalized.get("workspace_id"))
    source_id = _safe_str(normalized.get("source_id"))
    payload = normalized.get("payload") or {}

    def _finalize_result(result: dict[str, Any]) -> dict[str, Any]:
        """
        Persist a normalized metrics event and attach it to the response.
        Must never throw (observability must not break processing).
        """
        try:
            metrics_event = build_metrics_event(source=source, result=result)
            metrics_id = insert_metrics_event(metrics_event)
            metrics_event_with_id = {"id": metrics_id, **metrics_event}
            result["metrics_event"] = metrics_event_with_id

            log.info(f"[METRICS_EVENT:{source}] source_id={result.get('source_id')} event={metrics_event_with_id}")
            log_event(
                source=source,
                source_id=str(result.get("source_id") or source_id or ""),
                step="metrics_event",
                status="ok",
                data={"workspace_id": workspace_id, **metrics_event_with_id},
            )
        except Exception as e:
            log.exception(f"[METRICS_EVENT_ERROR:{source}] source_id={result.get('source_id') or source_id} -> {e}")
        return result

    if not source_id:
        result = _empty_processing_result(
            source_id=None,
            list_id=_safe_str(normalized.get("grafik_list_id_hint")),
        )
        result["error"] = "missing_source_id"
        result["reply_policy"] = {
            "should_reply": False,
            "reply_mode": "none",
            "reason": "error_missing_source_id",
            "confidence": 0.0,
            "needs_review": True,
        }
        return _finalize_result(result)

    raw_text = str(normalized.get("raw_text") or "").strip()
    text_for_classification = str(normalized.get("text_for_classification") or "").strip()

    channel = _safe_str(normalized.get("channel"))
    thread_id = _safe_str(normalized.get("thread_id"))
    ts = _safe_str(normalized.get("ts"))
    sender = _safe_str(normalized.get("sender"))
    user_id = _safe_str(normalized.get("user_id"))
    recipient = _safe_str(normalized.get("recipient"))
    subject = _safe_str(normalized.get("subject"))
    channel_type = _safe_str(normalized.get("channel_type"))
    message_id = _safe_str(normalized.get("message_id")) or _safe_str(payload.get("message_id"))

    list_id = _safe_str(normalized.get("grafik_list_id_hint"))
    client_name_hint = _safe_str(normalized.get("client_name_hint"))
    project_name_hint = _safe_str(normalized.get("project_name_hint"))

    continuity_context: dict[str, Any] = build_continuity_context(client_id=None, project_id=None)
    importance_result: dict[str, Any] = score_message_importance(
        classification={},
        continuity_context=continuity_context,
        clean_text=raw_text,
        channel=source,
    )
    scheduling_result: dict[str, Any] = analyze_scheduling_signals(
        clean_text=raw_text,
        classification={},
        project_update_candidate=None,
        follow_up_candidate=None,
        continuity_context=continuity_context,
        now_utc=_safe_str(payload.get("now_utc")),
    )

    # 1) Dedup + message insert
    try:
        is_new, db_message_id = insert_message_if_new(
            source=source,
            source_id=source_id,
            channel=channel or sender or "",
            ts=str(ts or ""),
            user=user_id or sender or "",
            text=raw_text,
            payload=payload,
        )
    except Exception as e:
        log.exception(f"[ERROR:{source}] source_id={source_id} -> insert_message_if_new failed: {e}")
        result = _empty_processing_result(source_id=source_id, list_id=list_id)
        result["error"] = f"insert_message_if_new_failed:{e}"
        result["reply_policy"] = {
            "should_reply": False,
            "reply_mode": "none",
            "reason": "error_insert_message",
            "confidence": 0.0,
            "needs_review": True,
        }
        return _finalize_result(result)

    if not is_new:
        existing = get_message_context_for_source_id(source=source, source_id=source_id) or {}
        existing_client_id = existing.get("client_id")
        existing_project_id = existing.get("project_id")
        continuity_context = build_continuity_context(
            client_id=int(existing_client_id) if existing_client_id else None,
            project_id=int(existing_project_id) if existing_project_id else None,
        )
        importance_result = score_message_importance(
            classification={},
            continuity_context=continuity_context,
            clean_text=raw_text,
            channel=source,
        )
        scheduling_result = analyze_scheduling_signals(
            clean_text=raw_text,
            classification={},
            project_update_candidate=None,
            follow_up_candidate=None,
            continuity_context=continuity_context,
            now_utc=_safe_str(payload.get("now_utc")),
        )

        log.info(f"[DEDUP:{source}] source_id={source_id} -> duplicate delivery skipped")
        log_event(
            source=source,
            source_id=source_id,
            step="dedup",
            status="duplicate",
            data={
                "workspace_id": workspace_id,
                "channel": channel,
                "thread_id": thread_id,
                "ts": ts,
                "sender": sender,
                "user_id": user_id,
                "subject": (subject or "")[:120] if subject else None,
            },
        )
        return _finalize_result({
            "status": "duplicate",
            "source_id": source_id,
            "classification": {},
            "client_name": None,
            "project_name": None,
            "client_id": None,
            "project_id": None,
            "project_resolution_reason": None,
            "project_confidence": None,
            "needs_project_review": False,
            "continuity_context": continuity_context,
            "importance_result": importance_result,
            "scheduling_result": scheduling_result,
            "project_update_candidate": {},
            "project_context_update_result": None,
            "updated_project_context": None,
            "follow_up_candidate": {},
            "follow_up_created": False,
            "follow_up_id": None,
            "task_link_result": {
                "matched": False,
                "reason": "duplicate",
                "task_id": None,
                "grafik_task_id": None,
                "confidence": 0.0,
                "needs_review": False,
            },
            "task_link_skipped": True,
            "task_link_skip_reason": "duplicate_delivery",
            "reply_policy": {
                "should_reply": False,
                "reply_mode": "none",
                "reason": "duplicate_delivery",
                "confidence": 1.0,
                "needs_review": False,
            },
            "reply_text": None,
            "should_create_reply": False,
            "should_create_draft": False,
            "draft_status": None,
            "draft_id": None,
            "grafik_task_id": None,
            "linked_grafik_task_id": None,
            "list_id": list_id,
            "error": None,
        })

    log.info(
        f"[INBOUND:{source}] source_id={source_id} workspace_id={workspace_id} "
        f"channel={channel} thread_id={thread_id} ts={ts} sender={sender} user_id={user_id} "
        f"text_preview={repr(raw_text[:120])}"
    )

    log_event(
        source=source,
        source_id=source_id,
        step="ingest",
        status="ok",
        data={
            "workspace_id": workspace_id,
            "channel": channel,
            "thread_id": thread_id,
            "ts": ts,
            "sender": sender,
            "user_id": user_id,
            "recipient": recipient,
            "subject": subject,
            "channel_type": channel_type,
            "text_preview": raw_text[:120],
        },
    )

    # 2) Client + project resolution (supports adapter overrides)
    client_id = normalized.get("client_id")
    project_id = normalized.get("project_id")
    client_name = _safe_str(normalized.get("client_name")) or client_name_hint
    project_name = _safe_str(normalized.get("project_name")) or project_name_hint

    project_resolution_reason = _safe_str(normalized.get("project_resolution_reason"))
    project_confidence = normalized.get("project_confidence")
    needs_project_review = bool(normalized.get("needs_project_review", False))

    if client_name and not client_id:
        client_id = ensure_client(client_name)

    if client_id and not project_id:
        # Slack may pass an explicit override in payload.project_name.
        # Gmail historically treats payload/default project as explicit; keep that behavior.
        explicit_project_name = _safe_str(payload.get("project_name")) or (
            project_name_hint if source == "gmail" else None
        )
        fallback_project_name = (project_name_hint or "General").strip()
        pid, pname, reason, confidence, needs_review = resolve_project_for_client(
            client_id=int(client_id),
            text=text_for_classification or raw_text,
            explicit_project_name=explicit_project_name,
            fallback_project_name=fallback_project_name,
        )
        project_id = pid
        project_name = pname
        project_resolution_reason = project_resolution_reason or reason
        project_confidence = project_confidence if project_confidence is not None else confidence
        needs_project_review = bool(needs_project_review or needs_review)

    project_context = get_project_context(int(project_id)) if project_id else None

    # 2b) Continuity context (Phase 8B) — gather recent relevant context
    continuity_context = build_continuity_context(
        client_id=int(client_id) if client_id else None,
        project_id=int(project_id) if project_id else None,
    )
    continuity_summary = (continuity_context or {}).get("summary") or {}
    log.info(
        f"[CONTINUITY_CONTEXT:{source}] source_id={source_id} "
        f"client_id={client_id} project_id={project_id} "
        f"has_project_context={continuity_summary.get('has_project_context')} "
        f"recent_message_count={continuity_summary.get('recent_message_count')} "
        f"recent_task_count={continuity_summary.get('recent_task_count')} "
        f"open_follow_up_count={continuity_summary.get('open_follow_up_count')}"
    )
    log_event(
        source=source,
        source_id=source_id,
        step="continuity_context",
        status="ok",
        data={
            "workspace_id": workspace_id,
            "client_id": client_id,
            "project_id": project_id,
            "has_project_context": continuity_summary.get("has_project_context"),
            "recent_message_count": continuity_summary.get("recent_message_count"),
            "recent_task_count": continuity_summary.get("recent_task_count"),
            "open_follow_up_count": continuity_summary.get("open_follow_up_count"),
        },
    )

    # 3) Classification
    classification_input = build_classification_input(
        raw_message_text=text_for_classification or raw_text,
        client_name=client_name,
        project_name=project_name,
        project_context=project_context,
    )

    log.info(f"[CLASSIFY_INPUT_RAW:{source}] source_id={source_id} text={repr(raw_text)}")
    log.info(
        f"[CLASSIFY_INPUT_CLEAN:{source}] source_id={source_id} "
        f"text={repr(text_for_classification or raw_text)}"
    )
    log.info(
        f"[CLASSIFY_INPUT_CONTEXT:{source}] source_id={source_id} "
        f"text={repr(classification_input)}"
    )

    classification = classify(
        classification_input,
        raw_text=(text_for_classification or raw_text),
    ) or {}

    has_action = bool(classification.get("has_action"))
    reply_type = _allowed_reply_type(classification.get("reply_type"))

    classification["has_action"] = has_action
    classification["reply_type"] = reply_type
    classification["client_name"] = client_name
    classification["project_name"] = project_name
    classification["project_resolution_reason"] = project_resolution_reason
    classification["project_confidence"] = project_confidence
    classification["needs_project_review"] = needs_project_review

    # 4) Project update + project memory update
    project_update_candidate = extract_project_updates(text_for_classification or raw_text)
    follow_up_candidate = detect_follow_up_candidate(text_for_classification or raw_text)

    project_context_update_result = update_project_context_from_candidate(
        int(project_id) if project_id else None,
        project_update_candidate,
        updated_by=source,
    )

    if project_context_update_result.get("updated"):
        project_context = get_project_context(int(project_id)) if project_id else project_context

    # 5) Follow-up creation
    follow_up_create_result = create_follow_up_from_candidate(
        source=source,
        source_id=source_id,
        client_id=int(client_id) if client_id else None,
        project_id=int(project_id) if project_id else None,
        candidate=follow_up_candidate,
    )

    # 6) Task linking
    skip_task_link = _as_bool(payload.get("skip_task_link", False))
    task_link_skipped = False
    task_link_skip_reason = None

    if skip_task_link:
        task_link_skipped = True
        task_link_skip_reason = "payload_skip_task_link"
        task_link_result = {
            "matched": False,
            "reason": "skipped",
            "task_id": None,
            "grafik_task_id": None,
            "confidence": 0.0,
            "needs_review": False,
        }
    else:
        task_link_result = find_existing_task_for_message(
            client_id=int(client_id) if client_id else None,
            project_id=int(project_id) if project_id else None,
            raw_text=(text_for_classification or raw_text),
            classification=classification,
            follow_up_candidate=follow_up_candidate,
        )

    # 6b) Importance scoring (advisory, Phase: Aivis Core importance)
    importance_result = score_message_importance(
        classification=classification,
        project_update_candidate=project_update_candidate,
        follow_up_candidate=follow_up_candidate,
        task_link_result=task_link_result,
        continuity_context=continuity_context,
        clean_text=raw_text,
        channel=source,
    )
    log.info(
        f"[IMPORTANCE_SCORE:{source}] source_id={source_id} "
        f"score={importance_result.get('importance_score')} "
        f"level={importance_result.get('importance_level')} "
        f"reasons={importance_result.get('importance_reasons')}"
    )
    log_event(
        source=source,
        source_id=source_id,
        step="importance_score",
        status="ok",
        data={
            "workspace_id": workspace_id,
            "client_id": client_id,
            "project_id": project_id,
            "importance_score": importance_result.get("importance_score"),
            "importance_level": importance_result.get("importance_level"),
            "importance_reasons": importance_result.get("importance_reasons"),
        },
    )

    # 6c) Scheduling awareness (advisory)
    scheduling_result = analyze_scheduling_signals(
        clean_text=raw_text,
        classification=classification,
        project_update_candidate=project_update_candidate,
        follow_up_candidate=follow_up_candidate,
        continuity_context=continuity_context,
        now_utc=_safe_str(payload.get("now_utc")),
    )
    log.info(
        f"[SCHEDULING_AWARENESS:{source}] source_id={source_id} "
        f"has_schedule_signal={scheduling_result.get('has_schedule_signal')} "
        f"due_hint_text={scheduling_result.get('due_hint_text')} "
        f"normalized_due={scheduling_result.get('normalized_due')} "
        f"time_pressure_level={scheduling_result.get('time_pressure_level')} "
        f"overdue_risk={scheduling_result.get('overdue_risk')} "
        f"upcoming_risk={scheduling_result.get('upcoming_risk')}"
    )
    log_event(
        source=source,
        source_id=source_id,
        step="scheduling_awareness",
        status="ok",
        data={
            "workspace_id": workspace_id,
            "client_id": client_id,
            "project_id": project_id,
            "has_schedule_signal": scheduling_result.get("has_schedule_signal"),
            "due_hint_text": scheduling_result.get("due_hint_text"),
            "normalized_due": scheduling_result.get("normalized_due"),
            "time_pressure_level": scheduling_result.get("time_pressure_level"),
            "overdue_risk": scheduling_result.get("overdue_risk"),
            "upcoming_risk": scheduling_result.get("upcoming_risk"),
        },
    )

    # 7) Reply policy + reply generation (source-specific behavior remains outside)
    policy_clean_text = (text_for_classification or raw_text) if source == "slack" else raw_text
    reply_policy = decide_reply_policy(
        channel=source,
        classification=classification,
        clean_text=policy_clean_text,
        project_context=project_context,
        follow_up_candidate=follow_up_candidate,
        project_update_candidate=project_update_candidate,
    )

    log.info(
        f"[REPLY_POLICY:{source}] source_id={source_id} "
        f"should_reply={reply_policy.get('should_reply')} "
        f"reply_mode={reply_policy.get('reply_mode')} "
        f"reason={reply_policy.get('reason')} "
        f"confidence={reply_policy.get('confidence')} "
        f"needs_review={reply_policy.get('needs_review')}"
    )

    log_event(
        source=source,
        source_id=source_id,
        step="reply_policy",
        status="ok",
        data={
            "workspace_id": workspace_id,
            "client_name": client_name,
            "project_name": project_name,
            "client_id": client_id,
            "project_id": project_id,
            **reply_policy,
        },
    )

    should_create_reply = bool(reply_policy.get("should_reply"))
    reply_text = None

    if should_create_reply:
        reply_text = generate_reply(
            original_text=raw_text,
            reply_type=reply_type,
            summary=classification.get("summary"),
            sender=sender or user_id,
            project_name=project_name,
            project_context=project_context,
            project_update_candidate=project_update_candidate,
            classification=classification,
            channel=source,
        )

    classification["suggested_reply"] = reply_text

    if db_message_id:
        attach_message_context(
            message_id=db_message_id,
            client_id=int(client_id) if client_id else None,
            project_id=int(project_id) if project_id else None,
            classification_type="ACTION" if has_action else "INFO",
            classification=classification,
        )

    # 8) Shared event logging (preserve existing event stream)
    log_event(
        source=source,
        source_id=source_id,
        step="classify",
        status="ok",
        data={
            "workspace_id": workspace_id,
            "raw_text": raw_text,
            "heuristic_input": (text_for_classification or raw_text),
            "llm_input": classification_input,
            "client_name": client_name,
            "project_name": project_name,
            "client_id": client_id,
            "project_id": project_id,
            "project_resolution_reason": project_resolution_reason,
            "project_confidence": project_confidence,
            "needs_project_review": needs_project_review,
            **classification,
        },
    )

    log_event(
        source=source,
        source_id=source_id,
        step="project_update_extract",
        status="ok",
        data={
            "workspace_id": workspace_id,
            "client_name": client_name,
            "project_name": project_name,
            "client_id": client_id,
            "project_id": project_id,
            "project_resolution_reason": project_resolution_reason,
            "project_confidence": project_confidence,
            "needs_project_review": needs_project_review,
            **project_update_candidate,
        },
    )

    log_event(
        source=source,
        source_id=source_id,
        step="project_context_update",
        status="ok",
        data={
            "workspace_id": workspace_id,
            "client_name": client_name,
            "project_name": project_name,
            "client_id": client_id,
            "project_id": project_id,
            "confidence": project_update_candidate.get("confidence"),
            **project_context_update_result,
        },
    )

    log_event(
        source=source,
        source_id=source_id,
        step="follow_up_detect",
        status="ok",
        data={
            "workspace_id": workspace_id,
            "client_name": client_name,
            "project_name": project_name,
            "client_id": client_id,
            "project_id": project_id,
            "project_resolution_reason": project_resolution_reason,
            "project_confidence": project_confidence,
            "needs_project_review": needs_project_review,
            **follow_up_candidate,
        },
    )

    log_event(
        source=source,
        source_id=source_id,
        step="follow_up_create",
        status="ok",
        data={
            "workspace_id": workspace_id,
            "client_name": client_name,
            "project_name": project_name,
            "client_id": client_id,
            "project_id": project_id,
            **follow_up_create_result,
        },
    )

    log_event(
        source=source,
        source_id=source_id,
        step="task_link_check",
        status="ok",
        data={
            "workspace_id": workspace_id,
            "client_name": client_name,
            "project_name": project_name,
            "client_id": client_id,
            "project_id": project_id,
            "task_link_skipped": task_link_skipped,
            "task_link_skip_reason": task_link_skip_reason,
            **task_link_result,
        },
    )

    # 9) Draft decision (Gmail only; creation stays in adapter)
    force_skip_draft = _as_bool(payload.get("skip_draft", False))
    has_real_gmail_ids = bool(
        source == "gmail"
        and thread_id
        and str(thread_id).isdigit()
        and message_id
    )
    should_create_draft = (
        source == "gmail"
        and reply_policy.get("reply_mode") == "draft_ready"
        and bool(reply_policy.get("should_reply"))
        and (not force_skip_draft)
        and has_real_gmail_ids
        and bool(reply_text)
    )

    # 10) Route: no task creation when not an action
    if not has_action:
        return _finalize_result({
            "status": "logged",
            "source_id": source_id,
            "classification": classification,
            "client_name": client_name,
            "project_name": project_name,
            "client_id": client_id,
            "project_id": project_id,
            "project_resolution_reason": project_resolution_reason,
            "project_confidence": project_confidence,
            "needs_project_review": needs_project_review,
            "continuity_context": continuity_context,
            "importance_result": importance_result,
            "scheduling_result": scheduling_result,
            "project_update_candidate": project_update_candidate,
            "project_context_update_result": project_context_update_result,
            "updated_project_context": project_context if project_context_update_result.get("updated") else None,
            "follow_up_candidate": follow_up_candidate,
            "follow_up_created": bool(follow_up_create_result.get("created")),
            "follow_up_id": follow_up_create_result.get("follow_up_id"),
            "task_link_result": task_link_result,
            "task_link_skipped": task_link_skipped,
            "task_link_skip_reason": task_link_skip_reason,
            "reply_policy": reply_policy,
            "reply_text": reply_text,
            "should_create_reply": should_create_reply,
            "should_create_draft": should_create_draft,
            "draft_status": None,
            "draft_id": None,
            "grafik_task_id": None,
            "linked_grafik_task_id": None,
            "list_id": list_id,
            "error": None,
        })

    # 11) Prefer linking to existing task (conservative) like current behavior
    if (
        (not task_link_skipped)
        and task_link_result.get("matched")
        and float(task_link_result.get("confidence") or 0.0) >= 0.75
        and (not task_link_result.get("needs_review"))
    ):
        linked_task_id = task_link_result.get("grafik_task_id")
        return _finalize_result({
            "status": "linked_existing_task",
            "source_id": source_id,
            "linked_grafik_task_id": linked_task_id,
            "classification": classification,
            "client_name": client_name,
            "project_name": project_name,
            "client_id": client_id,
            "project_id": project_id,
            "project_resolution_reason": project_resolution_reason,
            "project_confidence": project_confidence,
            "needs_project_review": needs_project_review,
            "continuity_context": continuity_context,
            "importance_result": importance_result,
            "scheduling_result": scheduling_result,
            "project_update_candidate": project_update_candidate,
            "project_context_update_result": project_context_update_result,
            "updated_project_context": project_context if project_context_update_result.get("updated") else None,
            "follow_up_candidate": follow_up_candidate,
            "follow_up_created": bool(follow_up_create_result.get("created")),
            "follow_up_id": follow_up_create_result.get("follow_up_id"),
            "task_link_result": task_link_result,
            "task_link_skipped": task_link_skipped,
            "task_link_skip_reason": task_link_skip_reason,
            "reply_policy": reply_policy,
            "reply_text": reply_text,
            "should_create_reply": should_create_reply,
            "should_create_draft": should_create_draft,
            "draft_status": None,
            "draft_id": None,
            "grafik_task_id": None,
            "linked_grafik_task_id": linked_task_id,
            "list_id": list_id,
            "error": None,
        })

    # 12) Decide Grafik task creation
    if not list_id:
        reason = "missing_grafik_list_id" if source == "gmail" else f"unmapped_channel:{channel}"
        log.info(f"[IGNORE:{source}] source_id={source_id} -> {reason}")

        log_event(
            source=source,
            source_id=source_id,
            step="routing_skip",
            status="ignored",
            data={
                "workspace_id": workspace_id,
                "reason": reason,
                "channel": channel,
                "classification": classification,
            },
        )

        return _finalize_result({
            "status": "ignored",
            "source_id": source_id,
            "reason": reason,
            "classification": classification,
            "client_name": client_name,
            "project_name": project_name,
            "client_id": client_id,
            "project_id": project_id,
            "project_resolution_reason": project_resolution_reason,
            "project_confidence": project_confidence,
            "needs_project_review": needs_project_review,
            "continuity_context": continuity_context,
            "importance_result": importance_result,
            "scheduling_result": scheduling_result,
            "project_update_candidate": project_update_candidate,
            "project_context_update_result": project_context_update_result,
            "updated_project_context": project_context if project_context_update_result.get("updated") else None,
            "follow_up_candidate": follow_up_candidate,
            "follow_up_created": bool(follow_up_create_result.get("created")),
            "follow_up_id": follow_up_create_result.get("follow_up_id"),
            "task_link_result": task_link_result,
            "task_link_skipped": task_link_skipped,
            "task_link_skip_reason": task_link_skip_reason,
            "reply_policy": reply_policy,
            "reply_text": reply_text,
            "should_create_reply": should_create_reply,
            "should_create_draft": should_create_draft,
            "draft_status": None,
            "draft_id": None,
            "grafik_task_id": None,
            "linked_grafik_task_id": None,
            "list_id": list_id,
            "error": None,
        })

    base_title = classification.get("title") or (
        f"{source.capitalize()}: {(subject or text_for_classification or raw_text)[:50]}"
        if (subject or text_for_classification or raw_text)
        else f"{source.capitalize()}: (no text)"
    )
    title = f"[{client_name}] {base_title}" if client_name else base_title

    context_block = ""
    if project_context:
        context_block = (
            "\n\nProject Context:\n"
            f"Summary: {project_context.get('summary')}\n"
            f"Current Status: {project_context.get('current_status')}\n"
            f"Current Priorities: {project_context.get('current_priorities')}\n"
            f"Blockers: {project_context.get('blockers')}\n"
            f"Next Steps: {project_context.get('next_steps')}\n"
        )

    description = (
        f"Client: {client_name or 'Unknown'}\n"
        f"Project: {project_name or 'Unknown'}\n"
        f"Project Resolution: {project_resolution_reason or 'unknown'}\n"
        f"Project Confidence: {project_confidence}\n"
        f"Needs Project Review: {needs_project_review}\n"
        f"Source: {source}\n"
        f"Workspace ID: {workspace_id}\n"
        f"Channel: {channel}\n"
        f"Channel Type: {channel_type}\n"
        f"Thread ID: {thread_id}\n"
        f"TS: {ts}\n"
        f"Sender: {sender}\n"
        f"Recipient: {recipient}\n"
        f"User ID: {user_id}\n"
        f"Subject: {subject}\n\n"
        f"Classification:\n{classification}\n"
        f"Project Update Candidate:\n{project_update_candidate}\n"
        f"Follow-up Candidate:\n{follow_up_candidate}\n"
        f"{context_block}\n"
        f"Raw Message:\n{raw_text}\n\n"
        f"Text Used For Heuristics:\n{text_for_classification or raw_text}\n\n"
        f"Text Used For LLM Classification:\n{classification_input}\n"
    )

    try:
        grafik_task_id = create_grafik_task(list_id, title, description)
        log.info(
            f"[GRAFIK:{source}] source_id={source_id} -> created task_id={grafik_task_id} list_id={list_id}"
        )

        upsert_task(
            source=source,
            source_id=source_id,
            grafik_task_id=grafik_task_id,
            title=title,
            description=description,
            classification=classification,
            client_id=int(client_id) if client_id else None,
            project_id=int(project_id) if project_id else None,
        )

        log_event(
            source=source,
            source_id=source_id,
            step="grafik_create",
            status="ok",
            data={
                "workspace_id": workspace_id,
                "grafik_task_id": grafik_task_id,
                "list_id": list_id,
                "client_name": client_name,
                "project_name": project_name,
                "client_id": client_id,
                "project_id": project_id,
                "project_resolution_reason": project_resolution_reason,
                "project_confidence": project_confidence,
                "needs_project_review": needs_project_review,
            },
        )

        return _finalize_result({
            "status": "created",
            "source_id": source_id,
            "classification": classification,
            "client_name": client_name,
            "project_name": project_name,
            "client_id": client_id,
            "project_id": project_id,
            "project_resolution_reason": project_resolution_reason,
            "project_confidence": project_confidence,
            "needs_project_review": needs_project_review,
            "continuity_context": continuity_context,
            "importance_result": importance_result,
            "scheduling_result": scheduling_result,
            "project_update_candidate": project_update_candidate,
            "project_context_update_result": project_context_update_result,
            "updated_project_context": project_context if project_context_update_result.get("updated") else None,
            "follow_up_candidate": follow_up_candidate,
            "follow_up_created": bool(follow_up_create_result.get("created")),
            "follow_up_id": follow_up_create_result.get("follow_up_id"),
            "task_link_result": task_link_result,
            "task_link_skipped": task_link_skipped,
            "task_link_skip_reason": task_link_skip_reason,
            "reply_policy": reply_policy,
            "reply_text": reply_text,
            "should_create_reply": should_create_reply,
            "should_create_draft": should_create_draft,
            "draft_status": None,
            "draft_id": None,
            "grafik_task_id": grafik_task_id,
            "linked_grafik_task_id": None,
            "list_id": list_id,
            "error": None,
        })

    except Exception as e:
        log.exception(f"[ERROR:{source}] source_id={source_id} -> {e}")
        log_event(
            source=source,
            source_id=source_id,
            step="error",
            status="error",
            data={"workspace_id": workspace_id, "error": str(e)},
        )
        return _finalize_result({
            "status": "error",
            "source_id": source_id,
            "classification": classification,
            "client_name": client_name,
            "project_name": project_name,
            "client_id": client_id,
            "project_id": project_id,
            "project_resolution_reason": project_resolution_reason,
            "project_confidence": project_confidence,
            "needs_project_review": needs_project_review,
            "continuity_context": continuity_context,
            "importance_result": importance_result,
            "scheduling_result": scheduling_result,
            "project_update_candidate": project_update_candidate,
            "project_context_update_result": project_context_update_result,
            "updated_project_context": project_context if project_context_update_result.get("updated") else None,
            "follow_up_candidate": follow_up_candidate,
            "follow_up_created": bool(follow_up_create_result.get("created")),
            "follow_up_id": follow_up_create_result.get("follow_up_id"),
            "task_link_result": task_link_result,
            "task_link_skipped": task_link_skipped,
            "task_link_skip_reason": task_link_skip_reason,
            "reply_policy": {
                "should_reply": False,
                "reply_mode": "none",
                "reason": "error",
                "confidence": 0.0,
                "needs_review": True,
            },
            "reply_text": reply_text,
            "should_create_reply": False,
            "should_create_draft": False,
            "draft_status": None,
            "draft_id": None,
            "grafik_task_id": None,
            "linked_grafik_task_id": None,
            "list_id": list_id,
            "error": str(e),
        })

