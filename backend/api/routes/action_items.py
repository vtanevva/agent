from __future__ import annotations

import json
from typing import Any, List

from flask import Blueprint, jsonify, request

from storage.sqlite_db import get_answered_threads, get_conn, mark_thread_answered
from utils.logger import get_logger
from services.marketing_email_signals import should_suppress_as_non_actionable


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


_REPLY_TYPES_NEEDING_RESPONSE = {"short", "time_relevant", "context_relevant"}


def _is_low_signal_stub(*, subject: str, body: str) -> bool:
    """
    An empty-subject message whose body is empty or just a bare URL /
    single short line does not carry enough context to become a task.
    These are almost always self-forwards or accidental sends and
    shouldn't pollute the action list.
    """
    s = (subject or "").strip()
    b = (body or "").strip()
    if s:
        return False
    if not b:
        return True
    if len(b) < 80 and ("\n" not in b) and (b.startswith("http://") or b.startswith("https://")):
        return True
    if len(b) < 20:
        return True
    return False


def _as_actionable(
    *,
    classification_type: Any,
    classification: dict,
    subject: str = "",
    body: str = "",
) -> bool:
    """
    A row deserves a spot in the tasks/action list when it is either:
      - a concrete action/task (classification_type == 'ACTION' or has_action)
      - or a message that expects a reply (reply_type != 'none')
      - AND it's not a low-signal stub (empty subject + trivial body).

    Marketing/newsletters are excluded upstream by ``should_suppress_as_non_actionable``.
    """
    is_action = str(classification_type or "").strip().upper() == "ACTION"
    has_action = bool(
        classification.get("has_action") is True or classification.get("has_action") == 1
    )
    reply_type = str(classification.get("reply_type") or "none").strip().lower()
    needs_reply = reply_type in _REPLY_TYPES_NEEDING_RESPONSE

    if not (is_action or has_action or needs_reply):
        return False

    # Only reply-type keeps us in? Require at least some content.
    if not (is_action or has_action) and needs_reply:
        if _is_low_signal_stub(subject=subject, body=body):
            return False

    return True


def _text_preview(v: Any, limit: int = 180) -> str:
    s = (str(v) if v is not None else "").strip()
    if not s:
        return ""
    return s[:limit] + ("..." if len(s) > limit else "")


def _chat_task_row_to_item(row: dict) -> dict:
    """Tasks created from chat (``tasks.source='chat'``) for the Home action list."""
    cls = _safe_json_loads(row.get("classification_json"))
    tid = row.get("id")
    due = cls.get("due_datetime") or cls.get("due_datetime_iso") or ""
    snippet = f"Due {due}" if due else "Chat task"
    sid = str(row.get("source_id") or tid or "")
    return {
        "source": "chat_task",
        "source_id": sid,
        "threadId": str(tid) if tid is not None else sid,
        "from": "Chat",
        "subject": row.get("title") or "(Task)",
        "snippet": snippet,
        "channel": None,
        "user": None,
        "ts": row.get("created_at"),
        "created_at": row.get("created_at"),
        "classification_type": row.get("classification_type") or "ACTION",
        "classification": cls,
        "has_action": True,
        "hasAction": True,
    }


def _row_to_item(row: dict) -> dict:
    payload = _safe_json_loads(row.get("payload_json"))
    cls = _safe_json_loads(row.get("classification_json"))

    source = row.get("source") or ""

    # "threadId" is what the Expo UI expects for list identity/actions.
    gmail_thread_id: str | None = None
    if source == "gmail":
        _tid = payload.get("thread_id") or payload.get("threadId")
        if _tid is not None and str(_tid).strip():
            gmail_thread_id = str(_tid).strip()
        thread_id = gmail_thread_id
    elif source == "slack":
        thread_id = payload.get("thread_ts") or payload.get("threadTs") or payload.get("ts") or row.get("ts")
    else:
        thread_id = payload.get("thread_id") or payload.get("thread_ts") or row.get("ts")

    # Fall back to source_id for list identity only (may be a message id, not a Gmail thread id).
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
    body_for_check = str(
        row.get("text")
        or payload.get("text")
        or payload.get("body")
        or payload.get("snippet")
        or ""
    )

    classification_type = row.get("classification_type")
    actionable = _as_actionable(
        classification_type=classification_type,
        classification=cls,
        subject=subject,
        body=body_for_check,
    )

    out: dict = {
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
    if source == "gmail":
        out["gmailThreadId"] = gmail_thread_id
    return out


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

    # Threads the user has already replied to — hide messages older than the reply.
    try:
        gmail_answered = get_answered_threads(source="gmail")
    except Exception as e:
        log.warning("[action-items] get_answered_threads(gmail) failed: %s", e)
        gmail_answered = {}
    try:
        slack_answered = get_answered_threads(source="slack")
    except Exception as e:
        log.warning("[action-items] get_answered_threads(slack) failed: %s", e)
        slack_answered = {}

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

        # Transcript / in-app agent lines are not the mail/Slack action inbox.
        if str(row.get("source") or "").strip().lower() in ("chat", "gmail_chat", "slack_chat"):
            continue

        subj_for_check = (payload.get("subject") or cls.get("title") or "").strip()
        body_for_check = str(
            row.get("text")
            or payload.get("text")
            or payload.get("body")
            or payload.get("snippet")
            or ""
        )

        if not _as_actionable(
            classification_type=row.get("classification_type"),
            classification=cls,
            subject=subj_for_check,
            body=body_for_check,
        ):
            continue

        src_l = str(row.get("source") or "").strip().lower()

        # Hide marketing / notifications / no-reply / ESP traffic already stored
        # (no re-ingest required; this is a runtime filter).
        if src_l == "gmail":
            sender_g = str(
                payload.get("from")
                or payload.get("sender")
                or row.get("user")
                or ""
            )
            suppress, _reason = should_suppress_as_non_actionable(
                payload=payload,
                subject=subj_for_check,
                raw_text=body_for_check.strip(),
                sender=sender_g,
            )
            if suppress:
                continue

        # Hide items on threads the user already replied to AFTER this message arrived.
        if src_l in ("gmail", "slack"):
            answered_map = gmail_answered if src_l == "gmail" else slack_answered
            if answered_map:
                thread_id_raw = (
                    payload.get("thread_id")
                    or payload.get("threadId")
                    or payload.get("thread_ts")
                    or payload.get("threadTs")
                )
                tid = str(thread_id_raw) if thread_id_raw else ""
                if tid:
                    answered_at = answered_map.get(tid)
                    if answered_at:
                        received_at = str(row.get("created_at") or "")
                        # ISO-8601 UTC strings sort lexicographically — reply after receipt => hide.
                        if not received_at or answered_at >= received_at:
                            continue

        items.append(_row_to_item(row))
        if len(items) >= limit:
            break

    chat_task_rows: List[dict] = []
    try:
        with get_conn() as conn:
            ct = conn.execute(
                """
                SELECT id, source, source_id, title, description,
                       classification_type, classification_json, created_at
                FROM tasks
                WHERE lower(trim(source)) = 'chat'
                ORDER BY id DESC
                LIMIT ?
                """,
                (min(limit, 100),),
            ).fetchall()
        chat_task_rows = [dict(r) for r in ct]
    except Exception as e:
        log.warning("[action-items] chat tasks read failed: %s", e)

    chat_items = [_chat_task_row_to_item(r) for r in chat_task_rows]
    merged = sorted(
        chat_items + items,
        key=lambda x: str(x.get("created_at") or x.get("ts") or ""),
        reverse=True,
    )[:limit]

    return jsonify({"success": True, "total": len(merged), "items": merged}), 200


def _mark_thread_answered_from_payload(payload: dict) -> dict:
    """
    Shared handler for 'done' / 'archive'. Treat a user click as an explicit
    "this thread has been taken care of" and persist it in ``thread_replies``
    so the tasks list hides it permanently.
    """
    source = str(payload.get("source") or "").strip().lower()
    thread_id = str(payload.get("thread_id") or payload.get("threadId") or "").strip()
    workspace_id = str(
        payload.get("workspace_id")
        or payload.get("workspaceId")
        or payload.get("email_address")
        or payload.get("user_id")
        or ""
    ).strip().lower()

    if source in ("gmail", "slack") and thread_id and workspace_id:
        try:
            mark_thread_answered(
                source=source,
                workspace_id=workspace_id,
                thread_id=thread_id,
            )
        except Exception as e:
            log.warning("[action-items] mark_thread_answered failed: %s", e)
            return {"success": False, "thread_id": thread_id, "error": str(e)}

    return {"success": True, "thread_id": thread_id or None}


@action_items_bp.post("/api/action-items/archive")
def archive_action_item():
    payload = request.get_json(silent=True) or {}
    return jsonify(_mark_thread_answered_from_payload(payload)), 200


@action_items_bp.post("/api/action-items/done")
def done_action_item():
    payload = request.get_json(silent=True) or {}
    return jsonify(_mark_thread_answered_from_payload(payload)), 200


__all__ = ["action_items_bp"]

