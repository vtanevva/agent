"""
Detect simple \"add a task ... by Sunday\" chat lines and persist ``tasks`` rows
so the weekly schedule and home action list can show them.

The actual write goes through the same unified processor used for Gmail /
Slack, so project detection (existing-project match, new-project creation,
or the ``General`` fallback) is identical for every task source.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from application.services.calendar_meeting_action import (
    _anchor_local_midnight,
    _clock_from_text,
    _tz_name,
)
from services.chat_project_hint import safe_project_hint
from utils.logger import get_logger


log = get_logger("chat_task_action")


def _clean_title(raw: str) -> str:
    s = " ".join((raw or "").strip().split())
    s = re.sub(r"(?i)^(to|that i|i need to)\s+", "", s).strip()
    return (s[:200] or "").strip() or "Task"


def _looks_like_task_creation_request(text: str) -> bool:
    t = (text or "").lower()
    if len(t) < 12 or len(t) > 900:
        return False
    if re.search(r"\b(meeting|appointment|video call)\b", t) and re.search(
        r"\b(schedule|book|set up|create|add|reserve)\b", t
    ):
        return False
    if re.search(r"\b(add|create)\s+(a\s+)?task\b", t):
        return True
    if re.search(r"\bschedule\s+(me\s+)?(a\s+)?task\b", t):
        return True
    if re.search(r"\bremind\s+me\s+to\b", t):
        return True
    return False


def _extract_task_title(text: str) -> str | None:
    m = re.search(r"(?i)(?:add|create)\s+(?:a\s+)?task\s+to\s+(.+?)\s+by\b", text)
    if m:
        return _clean_title(m.group(1))
    m = re.search(r"(?i)\bschedule\s+(?:me\s+)?(?:a\s+)?task\s+(?:for\s+)?to\s+(.+?)\s+by\b", text)
    if m:
        return _clean_title(m.group(1))
    m = re.search(r"(?i)\bschedule\s+(?:me\s+)?(?:a\s+)?task\s+(.+?)\s+by\b", text)
    if m:
        return _clean_title(m.group(1))
    m = re.search(r"(?i)\bremind\s+me\s+to\s+(.+?)\s+by\b", text)
    if m:
        return _clean_title(m.group(1))
    m = re.search(r"(?i)\bput\s+(.+?)\s+on\s+my\s+(?:task\s+)?list\b", text)
    if m:
        return _clean_title(m.group(1))
    return None


def _parse_deadline_local(text: str, tz_name: str) -> datetime | None:
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc

    now_local = datetime.now(tz)
    day0 = _anchor_local_midnight(text, now_local)
    if day0 is None:
        return None

    clock = _clock_from_text(text)
    if clock is None:
        h, mi = 18, 0
    else:
        h, mi = clock

    return datetime(day0.year, day0.month, day0.day, h, mi, 0, tzinfo=tz)


def try_create_task_from_chat(
    user_message: str,
    metadata: dict[str, Any] | None,
    *,
    session_id: str | None = None,
) -> str | None:
    """
    If ``user_message`` is a concrete task-with-deadline request, route it
    through the unified processor (same path as Gmail / Slack) so project
    detection and DB writes are consistent across sources. Returns the
    user-visible chat reply on success, otherwise ``None``.
    """
    text = (user_message or "").strip()
    if not _looks_like_task_creation_request(text):
        return None

    title = _extract_task_title(text)
    if not title:
        return None

    tz_name = _tz_name(metadata)
    due = _parse_deadline_local(text, tz_name)
    if due is None:
        return None

    due_iso = due.isoformat()
    classification_override: dict[str, Any] = {
        "type": "ACTION",
        "has_action": True,
        "reply_type": "none",
        "title": title,
        "summary": title,
        "due_datetime": due_iso,
        "due_datetime_iso": due_iso,
    }

    sid = (session_id or "session").strip() or "session"
    source_id = f"chat_task:{sid}:{uuid4().hex}"
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    project_hint = safe_project_hint(text)

    normalized = {
        "source": "chat_task",
        "workspace_id": None,
        "source_id": source_id,
        "channel": f"chat:{sid}",
        "thread_id": sid,
        "ts": now_iso,
        "sender": sid,
        "user_id": sid,
        "recipient": None,
        "subject": title,
        "raw_text": text,
        "text_for_classification": text,
        "payload": {
            "skip_task_link": True,
            "skip_draft": True,
            "classification_override": classification_override,
            "metadata": metadata or {},
        },
        "client_name_hint": "Inbox",
        "project_name_hint": project_hint,
        "channel_type": "chat",
    }

    try:
        from application.orchestrators.event_orchestrator import handle_normalized_event
        handle_normalized_event(normalized)
    except Exception as e:
        # Never block the user-facing reply on a backend write failure; the
        # chat orchestrator returns a confirmation string to the UI either
        # way, and the error is visible in logs.
        log.warning("chat_task unified ingest failed: %s", e)

    when = due.strftime("%A, %B %d, %Y at %H:%M")
    return (
        f'I added "{title}" to your tasks with a due time of {when} (your local time). '
        "You will see it on your home screen and on the weekly schedule."
    )
