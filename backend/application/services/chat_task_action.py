"""
Detect simple \"add a task … by Sunday\" chat lines and persist ``tasks`` rows
so the weekly schedule and home action list can show them.
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
    if re.search(r"\bremind\s+me\s+to\b", t):
        return True
    return False


def _extract_task_title(text: str) -> str | None:
    m = re.search(r"(?i)(?:add|create)\s+(?:a\s+)?task\s+to\s+(.+?)\s+by\b", text)
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
    If ``user_message`` is a concrete task-with-deadline request, upsert a SQLite task
    and return a user-facing reply. Otherwise ``None``.
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
    classification: dict[str, Any] = {
        "type": "ACTION",
        "has_action": True,
        "due_datetime": due_iso,
        "due_datetime_iso": due_iso,
        "summary": title,
    }

    sid = (session_id or "session").strip() or "session"
    source_id = f"chat_task:{sid}:{uuid4().hex}"
    grafik_task_id = f"aivis-local-{uuid4().hex}"

    from storage.sqlite_db import upsert_task

    upsert_task(
        source="chat",
        source_id=source_id,
        grafik_task_id=grafik_task_id,
        title=title,
        description=f"Created from chat. Original: {text[:500]}",
        classification=classification,
        client_id=None,
        project_id=None,
    )

    when = due.strftime("%A, %B %d, %Y at %H:%M")
    return (
        f'I added "{title}" to your tasks with a due time of {when} (your local time). '
        "You will see it on your home screen and on the weekly schedule."
    )
