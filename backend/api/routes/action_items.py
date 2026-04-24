from __future__ import annotations

import json
import re
from typing import Any, List

from flask import Blueprint, jsonify, request

from storage.sqlite_db import get_answered_threads, get_conn, mark_thread_answered
from utils.logger import get_logger
from services.marketing_email_signals import should_suppress_as_non_actionable
from services.gmail_auth import get_linked_gmail_address


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


# Messages whose reply_type is ``short`` only need a trivial "ok / alright" answer
# and should not clutter Home. Only substantive reply types stay in the feed.
_REPLY_TYPES_NEEDING_RESPONSE = {"time_relevant", "context_relevant"}

# Chat task rows use ``source_id = f"chat_task:{session_id}:{uuid}"`` where ``session_id`` is
# ``{userId}-{6 random base36 chars}`` (see ``frontend/src/config/api.js`` ``genSession``).
_CHAT_SESSION_SUFFIX_LEN = 6


def _resolve_gmail_mailbox_scope(user_id: str) -> str | None:
    """
    Mailbox email used to filter stored Gmail rows.

    If ``user_id`` is already an email, use it. Otherwise resolve from the per-user
    OAuth token so short login names still see only their linked inbox.
    """
    uid = (user_id or "").strip().lower()
    if not uid:
        return None
    if "@" in uid:
        return uid
    return get_linked_gmail_address(uid)


def _chat_task_source_id_matches_user(source_id: Any, user_id: str) -> bool:
    if not (user_id or "").strip():
        return True
    uid = user_id.strip().lower()
    sid = str(source_id or "")
    parts = sid.split(":")
    if len(parts) < 3 or parts[0] != "chat_task":
        return True
    session_id = parts[1]
    prefix = f"{uid}-"
    if not session_id.startswith(prefix):
        return False
    return len(session_id) == len(uid) + 1 + _CHAT_SESSION_SUFFIX_LEN


def _row_visible_for_app_user(
    *,
    src: str,
    payload: dict,
    request_user: str,
    mailbox_scope: str | None,
) -> bool:
    """
    Per-profile visibility for stored ``messages`` rows.

    Prefer ``payload.app_user_id`` (stamped by unified ingest). Legacy Gmail rows fall back to
    mailbox match when the viewer has a resolved mailbox. Unstamped Slack is hidden for
    logged-in viewers (cannot prove ownership).
    """
    ru = (request_user or "").strip().lower()
    if not ru:
        return True
    puid = str(payload.get("app_user_id") or "").strip().lower()
    if puid:
        return puid == ru
    src_l = (src or "").strip().lower()
    if src_l == "gmail" and mailbox_scope:
        workspace = str(
            payload.get("workspace_id")
            or payload.get("workspaceId")
            or payload.get("emailAddress")
            or ""
        ).strip().lower()
        return bool(workspace and workspace == mailbox_scope)
    if src_l == "slack":
        return False
    return True


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


# Titles for tasks created before the ``build_task_title_and_description`` fix
# were built as ``"Gmail: Subject: Body: <first 50 chars of wrapped classifier
# input>"`` when both the classifier title and the subject were empty. Strip
# those labels at read time so the UI shows the actual task text.
_LEADING_SOURCE_PREFIX_RE = re.compile(
    r"^\s*(?:gmail|slack|chat(?:_task)?|outlook|email)\s*:\s*",
    re.IGNORECASE,
)
_LEADING_SUBJECT_EMPTY_RE = re.compile(r"^\s*subject\s*:\s*(?=body\s*:)", re.IGNORECASE)
_LEADING_BODY_RE = re.compile(r"^\s*body\s*:\s*", re.IGNORECASE)


def _clean_task_title(raw: Any) -> str:
    """Drop stale ``"<Source>: Subject: Body: ..."`` prefixes left on older rows."""
    s = (str(raw) if raw is not None else "").strip()
    if not s:
        return ""
    prev = None
    # Iterate because some rows accumulated multiple prefixes (e.g. re-ingest).
    while prev != s:
        prev = s
        s = _LEADING_SOURCE_PREFIX_RE.sub("", s, count=1).strip()
        s = _LEADING_SUBJECT_EMPTY_RE.sub("", s, count=1).strip()
        s = _LEADING_BODY_RE.sub("", s, count=1).strip()
    return s or str(raw).strip()


def _source_label_for_home(source: str) -> str:
    s = (source or "").strip().lower()
    if s == "gmail":
        return "Email"
    if s == "slack":
        return "Slack"
    if s in ("chat", "chat_task"):
        return "Chat"
    return s.capitalize() if s else ""


def _task_row_to_item(row: dict) -> dict:
    """
    Turn a ``tasks`` row into a Home action item. Works for gmail / slack / chat
    sources — everything the unified processor creates lives in the same table.
    """
    cls = _safe_json_loads(row.get("classification_json"))
    tid = row.get("id")
    due = (
        cls.get("due_datetime")
        or cls.get("due_datetime_iso")
        or (cls.get("normalized_due") or {}).get("iso")
    )
    src = str(row.get("source") or "").strip().lower()
    label = _source_label_for_home(src)
    snippet = f"Due {due}" if due else (label or "Task")
    sid = str(row.get("source_id") or tid or "")
    thread_id = row.get("thread_id") or (str(tid) if tid is not None else sid)
    # Keep ``source`` semantically aligned with Home UI. The unified processor
    # now writes chat-created tasks with ``source="chat_task"`` directly, so
    # we just pass it through. Older rows written as ``source="chat"`` are
    # rewritten to ``chat_task`` for UI consistency.
    api_source = "chat_task" if src == "chat" else src
    return {
        "source": api_source,
        "source_id": sid,
        "task_id": tid,
        "threadId": str(thread_id) if thread_id else sid,
        "from": label or "Task",
        "subject": _clean_task_title(row.get("title")) or "(Task)",
        "snippet": snippet,
        "channel": None,
        "user": None,
        "ts": row.get("created_at"),
        "created_at": row.get("created_at"),
        "classification_type": row.get("classification_type") or "ACTION",
        "classification": cls,
        "due_datetime": due,
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

    subject = _clean_task_title(payload.get("subject") or cls.get("title") or "")
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

    Rows are filtered by ``payload.app_user_id`` when present (set by Gmail Pub/Sub / Slack
    ingest via ``profile_link``). Legacy Gmail without a stamp still matches the viewer's
    mailbox when known. Chat-sourced tasks match ``user_id`` via ``source_id`` session prefix.

    Returns a flat list for the Expo UI:
      { success: true, total: N, items: [...] }
    """
    user_id = (request.args.get("user_id") or "").strip().lower()
    mailbox_scope = _resolve_gmail_mailbox_scope(user_id)
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

    # Tasks (unified local table: gmail / slack / chat). Loaded first so we can
    # dedupe the messages list: if a thread already became a task, the message
    # should not also appear as an "unanswered message" on Home.
    task_rows: List[dict] = []
    try:
        with get_conn() as conn:
            tr = conn.execute(
                """
                SELECT id, source, source_id, thread_id, workspace_id,
                       title, description,
                       classification_type, classification_json,
                       status, created_at
                FROM tasks
                WHERE COALESCE(status, 'pending') != 'completed'
                ORDER BY id DESC
                LIMIT ?
                """,
                (min(max(limit * 2, 200), 1000),),
            ).fetchall()
        task_rows = [dict(r) for r in tr]
    except Exception as e:
        log.warning("[action-items] tasks read failed: %s", e)

    task_items: List[dict] = []
    task_thread_keys: set[tuple[str, str]] = set()
    for r in task_rows:
        src = str(r.get("source") or "").strip().lower()

        # Per-user scoping:
        #   - chat tasks use ``source_id = chat_task:<session>:<uuid>``
        #   - gmail tasks carry ``workspace_id = mailbox email``
        #   - slack tasks are not user-scoped yet (single workspace assumption)
        if src in ("chat", "chat_task"):
            if not _chat_task_source_id_matches_user(r.get("source_id"), user_id):
                continue
        elif src == "gmail" and mailbox_scope:
            wid = str(r.get("workspace_id") or "").strip().lower()
            if wid and wid != mailbox_scope:
                continue

        task_items.append(_task_row_to_item(r))

        tid = str(r.get("thread_id") or "").strip()
        if src and tid:
            task_thread_keys.add((src, tid))

    items: List[dict] = []
    for r in rows:
        row = dict(r)
        payload = _safe_json_loads(row.get("payload_json"))
        cls = _safe_json_loads(row.get("classification_json"))
        src_l = str(row.get("source") or "").strip().lower()

        # Transcript / in-app agent lines and the raw ``chat_task`` ingest line
        # are not direct Home items — the resulting task row (loaded above)
        # already represents them in the feed.
        if src_l in ("chat", "gmail_chat", "slack_chat", "chat_task"):
            continue

        if not _row_visible_for_app_user(
            src=src_l, payload=payload, request_user=user_id, mailbox_scope=mailbox_scope
        ):
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
            thread_id_raw = (
                payload.get("thread_id")
                or payload.get("threadId")
                or payload.get("thread_ts")
                or payload.get("threadTs")
            )
            tid = str(thread_id_raw) if thread_id_raw else ""
            if answered_map and tid:
                answered_at = answered_map.get(tid)
                if answered_at:
                    received_at = str(row.get("created_at") or "")
                    # ISO-8601 UTC strings sort lexicographically — reply after receipt => hide.
                    if not received_at or answered_at >= received_at:
                        continue
            # Dedupe: if this thread already became a task (shown above),
            # don't also list the raw message here.
            if tid and (src_l, tid) in task_thread_keys:
                continue

        items.append(_row_to_item(row))
        if len(items) >= limit:
            break

    merged = sorted(
        task_items + items,
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

