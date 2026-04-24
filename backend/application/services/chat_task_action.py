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

# Verbs / nouns for "this message is asking to record a task" (not the task title itself).
_TASK_VERB = r"(?:add|create|make|set(?:\s+up)?|start|open|log|track|file|queue)"
_TASK_ART = r"(?:a\s+|an\s+|the\s+|my\s+|this\s+)?"
_TASK_NOUN = r"(?:new\s+)?(?:task|todo|to-?do|action\s+item)\b"
_SCHEDULE_TASK = r"\bschedule\s+(?:me\s+)?(?:a\s+)?task\b"

# After the title, user usually gives a deadline — allow common wordings so we do not
# require the literal word "by" (e.g. "before Friday", "due by Monday").
_DEADLINE_BOUNDARY = (
    r"(?:\s+by\b|\s+before\b|\s+until\b|\s+due\s+by\b|\s+due\s+on\b|\s+no\s+later\s+than\b)"
)
# When there is no date phrase, title is the rest of the message (one line); see
# ``_clean_title`` for trailing thanks / punctuation.
_TITLE_TO_EOL = r"(.+)$"


def _clean_title(raw: str) -> str:
    s = (raw or "").strip()
    s = s.split("\n", 1)[0].strip()
    s = " ".join(s.split())
    s = re.sub(r"(?i)^(to|that i|i need to|for me to)\s+", "", s).strip()
    s = re.sub(r"(?i)\s+(thanks|thank you|thx|cheers|appreciate it)[.!?\s]*$", "", s).strip()
    return (s[:200] or "").strip() or "Task"


def _looks_like_task_creation_request(text: str) -> bool:
    t = (text or "").lower()
    if len(t) < 8 or len(t) > 900:
        return False
    # Calendar meeting shortcut — let calendar handler win, but not when the user
    # explicitly asked for a *task* that merely mentions scheduling a meeting.
    explicit_task_phrase = bool(
        re.search(rf"\b{_TASK_VERB}\s+{_TASK_ART}{_TASK_NOUN}", t)
        or re.search(_SCHEDULE_TASK, t)
        or re.search(r"\bnew\s+task\b", t)
    )
    if (
        re.search(r"\b(meeting|appointment|video call)\b", t)
        and re.search(r"\b(schedule|book|set up|create|add|reserve)\b", t)
        and not explicit_task_phrase
    ):
        return False
    if re.search(rf"\b{_TASK_VERB}\s+{_TASK_ART}{_TASK_NOUN}", t):
        return True
    if re.search(rf"\b(?:throw|stick)\s+(?:this\s+)?(?:on|in)\s+(?:my\s+)?(?:task\s+)?list\b", t):
        return True
    if re.search(r"\bnew\s+task\b", t):
        return True
    if re.search(_SCHEDULE_TASK, t):
        return True
    if re.search(r"\bremind\s+me\s+to\b", t):
        return True
    if re.search(r"\bremember\s+to\b", t):
        return True
    if re.search(r"\bi\s+need\s+(?:a\s+|an\s+)?(?:new\s+)?(?:task|todo)\b", t):
        return True
    if re.search(r"\bcan\s+you\s+(?:please\s+)?(?:add|create|make)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:task|todo)\b", t):
        return True
    if re.search(r"\bplease\s+(?:add|create|make)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:task|todo)\b", t):
        return True
    if re.search(r"\bgive\s+me\s+(?:a\s+|an\s+)?(?:new\s+)?(?:task|todo)\b", t):
        return True
    return False


def _extract_task_title(text: str) -> str | None:
    """
    Pull the human description of the work item. Intentionally allows titles that
    contain the words \"create a task\" (e.g. meta reminders) as long as a deadline
    phrase follows later in the message.

    If the user gives no date (e.g. \"add a task to do the dishes\"), we still
    extract a title and create a task without a due datetime.
    """
    with_deadline: list[str] = [
        # create/make/... a task to <title> by|before|...
        rf"(?i)\b{_TASK_VERB}\s+{_TASK_ART}{_TASK_NOUN}\s+to\s+(.+?){_DEADLINE_BOUNDARY}",
        # ... task for <title> ...
        rf"(?i)\b{_TASK_VERB}\s+{_TASK_ART}{_TASK_NOUN}\s+for\s+(.+?){_DEADLINE_BOUNDARY}",
        # ... task: <title> ...
        rf"(?i)\b{_TASK_VERB}\s+{_TASK_ART}{_TASK_NOUN}\s*:\s*(.+?){_DEADLINE_BOUNDARY}",
        # new task to|for <title> ...
        rf"(?i)\bnew\s+task\s+(?:to|for)\s+(.+?){_DEADLINE_BOUNDARY}",
        # I need a task to <title> ...
        rf"(?i)\bi\s+need\s+(?:a\s+|an\s+)?(?:new\s+)?(?:task|todo)\s+(?:to|for)\s+(.+?){_DEADLINE_BOUNDARY}",
        # can you / please add a task ...
        rf"(?i)\b(?:can\s+you\s+(?:please\s+)?|please\s+)(?:add|create|make)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:task|todo)\s+(?:to|for)\s+(.+?){_DEADLINE_BOUNDARY}",
        # give me a task to ...
        rf"(?i)\bgive\s+me\s+(?:a\s+|an\s+)?(?:new\s+)?(?:task|todo)\s+(?:to|for)\s+(.+?){_DEADLINE_BOUNDARY}",
        # schedule a task ...
        r"(?i)\bschedule\s+(?:me\s+)?(?:a\s+)?task\s+(?:for\s+)?to\s+(.+?)" + _DEADLINE_BOUNDARY,
        r"(?i)\bschedule\s+(?:me\s+)?(?:a\s+)?task\s+(.+?)" + _DEADLINE_BOUNDARY,
        # remind / remember
        r"(?i)\bremind\s+me\s+to\s+(.+?)" + _DEADLINE_BOUNDARY,
        r"(?i)\bremember\s+to\s+(.+?)" + _DEADLINE_BOUNDARY,
        # put ... on my list by|before|...
        rf"(?i)\bput\s+(.+?)\s+on\s+my\s+(?:task\s+)?list\b{_DEADLINE_BOUNDARY}",
    ]

    for pat in with_deadline:
        m = re.search(pat, text)
        if m:
            return _clean_title(m.group(1))

    # No explicit deadline phrase — title to end of line / message.
    no_deadline: list[str] = [
        rf"(?i)\b{_TASK_VERB}\s+{_TASK_ART}{_TASK_NOUN}\s+to\s+{_TITLE_TO_EOL}",
        rf"(?i)\b{_TASK_VERB}\s+{_TASK_ART}{_TASK_NOUN}\s+for\s+{_TITLE_TO_EOL}",
        rf"(?i)\b{_TASK_VERB}\s+{_TASK_ART}{_TASK_NOUN}\s*:\s*{_TITLE_TO_EOL}",
        rf"(?i)\bnew\s+task\s+(?:to|for)\s+{_TITLE_TO_EOL}",
        rf"(?i)\bi\s+need\s+(?:a\s+|an\s+)?(?:new\s+)?(?:task|todo)\s+(?:to|for)\s+{_TITLE_TO_EOL}",
        rf"(?i)\b(?:can\s+you\s+(?:please\s+)?|please\s+)(?:add|create|make)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:task|todo)\s+(?:to|for)\s+{_TITLE_TO_EOL}",
        rf"(?i)\bgive\s+me\s+(?:a\s+|an\s+)?(?:new\s+)?(?:task|todo)\s+(?:to|for)\s+{_TITLE_TO_EOL}",
        r"(?i)\bschedule\s+(?:me\s+)?(?:a\s+)?task\s+(?:for\s+)?to\s+" + _TITLE_TO_EOL,
        r"(?i)\bschedule\s+(?:me\s+)?(?:a\s+)?task\s+" + _TITLE_TO_EOL,
        r"(?i)\bremind\s+me\s+to\s+" + _TITLE_TO_EOL,
        r"(?i)\bremember\s+to\s+" + _TITLE_TO_EOL,
    ]

    for pat in no_deadline:
        m = re.search(pat, text.strip())
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
    If ``user_message`` is a concrete task request (with or without a due date),
    route it through the unified processor (same path as Gmail / Slack) so project
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

    classification_override: dict[str, Any] = {
        "type": "ACTION",
        "has_action": True,
        "reply_type": "none",
        "title": title,
        "summary": title,
    }
    if due is not None:
        due_iso = due.isoformat()
        classification_override["due_datetime"] = due_iso
        classification_override["due_datetime_iso"] = due_iso

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

    if due is not None:
        when = due.strftime("%A, %B %d, %Y at %H:%M")
        return (
            f'I added "{title}" to your tasks with a due time of {when} (your local time). '
            "You will see it on your home screen and on the weekly schedule."
        )
    return (
        f'I added "{title}" to your tasks (no due date yet). '
        "It appears on your home screen and in the Unscheduled section on the weekly schedule; "
        "you can set a deadline anytime from home or chat."
    )
