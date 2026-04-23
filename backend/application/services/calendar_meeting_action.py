"""
Detect simple \"schedule a meeting …\" chat messages and create a calendar event
(Google Calendar when OAuth is available, otherwise SQLite so the weekly grid still shows it).
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from googleapiclient.errors import HttpError


def _ensure_backend_import_path() -> None:
    """``services.*`` / ``storage.*`` resolve from ``backend/`` even when cwd is repo root."""
    backend_dir = Path(__file__).resolve().parents[2]
    if backend_dir.is_dir() and (backend_dir / "services").is_dir():
        s = str(backend_dir)
        if s not in sys.path:
            sys.path.insert(0, s)


_ensure_backend_import_path()

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_RE_NEXT_WEEKDAY = re.compile(r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
_RE_WEEKDAY = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_RE_DURATION_MIN = re.compile(r"\b(\d{1,2})\s*(?:minutes?|mins?)\b", re.I)
_RE_DURATION_HOUR = re.compile(r"\b(\d{1,2})\s*(?:hours?|hrs?|h)\b", re.I)
_RE_TOPIC_ABOUT = re.compile(r"(?i)\b(?:about|to discuss)\s+(.+?)(?:\.|$|,|;)")
_RE_TOPIC_PROJECT = re.compile(r"(?i)\b([A-Za-z][A-Za-z0-9 _-]{2,80}\s+project)\b")
_RE_WITH_PERSON = re.compile(r"(?i)\bwith\s+([A-Za-z][A-Za-z .'-]{1,40})(?:,|;|\bon\b|\bat\b|$)")
_RE_PLATFORM = re.compile(r"(?i)\b(on|via)\s+(teams|microsoft teams|zoom|google meet|meet)\b")


def _tz_name(metadata: dict[str, Any] | None) -> str:
    if isinstance(metadata, dict):
        z = str(metadata.get("timezone") or metadata.get("timeZone") or "").strip()
        if z:
            return z
    return (os.getenv("AIVIS_DEFAULT_TIMEZONE") or "UTC").strip() or "UTC"


def _weekday_to_date(now_local: datetime, weekday: int, *, force_next: bool) -> datetime:
    delta = (weekday - now_local.weekday()) % 7
    if force_next and delta == 0:
        delta = 7
    d = (now_local + timedelta(days=delta)).date()
    z = now_local.tzinfo
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=z)


def _anchor_local_midnight(text: str, now_local: datetime) -> datetime | None:
    tl = text.lower()
    if re.search(r"\btomorrow\b", tl):
        d = (now_local.date() + timedelta(days=1))
        z = now_local.tzinfo
        return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=z)
    if re.search(r"\b(today|tonight)\b", tl):
        d = now_local.date()
        z = now_local.tzinfo
        return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=z)
    m = _RE_NEXT_WEEKDAY.search(tl)
    if m:
        wd = _WEEKDAYS[m.group(1).lower()]
        return _weekday_to_date(now_local, wd, force_next=True)
    m = _RE_WEEKDAY.search(tl)
    if m:
        wd = _WEEKDAYS[m.group(1).lower()]
        return _weekday_to_date(now_local, wd, force_next=False)
    return None


def _clock_from_text(text: str) -> tuple[int, int] | None:
    from services.scheduling_awareness import _extract_time

    t = _extract_time(text)
    if t:
        return t
    m = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\b(?!\s*(?:am|pm)\b)", text, re.I)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or "0")
    if m.group(2) is None:
        # Bare hours are ambiguous; keep prior PM heuristic for 1..7, but
        # also accept explicit 24-hour clocks like "at 18".
        if 1 <= h <= 7:
            h = h + 12
        elif h == 12:
            pass
        elif 8 <= h <= 23:
            pass
        else:
            return None
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    return h, mi


def _default_duration_minutes(text: str) -> int:
    m = _RE_DURATION_MIN.search(text)
    if m:
        return max(5, min(24 * 60, int(m.group(1))))
    m = _RE_DURATION_HOUR.search(text)
    if m:
        return max(5, min(24 * 60, int(m.group(1)) * 60))
    return 60


def _meeting_title(text: str) -> str:
    m = _RE_TOPIC_ABOUT.search(text)
    if m:
        topic = (m.group(1) or "").strip()
        if len(topic) >= 2:
            return topic[:120]
    m2 = _RE_TOPIC_PROJECT.search(text)
    if m2:
        return m2.group(1).strip()[:120]
    return "Meeting"


def _looks_like_meeting_schedule_request(text: str) -> bool:
    t = (text or "").lower()
    if not re.search(r"\b(meeting|video call|appointment)\b", t):
        return False
    if not re.search(r"\b(schedule|book|set up|create|add|put|reserve)\b", t):
        return False
    if re.search(r"\b(should i|could i|would i|how do i|why did|i had|i have had)\b", t):
        return False
    return True


def _parse_start_local(text: str, tz_name: str) -> datetime | None:
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        # Windows/Python can miss IANA tzdata; always keep a safe built-in UTC fallback.
        tz = timezone.utc

    now_local = datetime.now(tz)
    day0 = _anchor_local_midnight(text, now_local)
    if day0 is None:
        return None

    clock = _clock_from_text(text)
    if clock is None:
        clock = (9, 0)

    y, mth, d = day0.year, day0.month, day0.day
    h, mi = clock
    return datetime(y, mth, d, h, mi, 0, tzinfo=tz)


def persist_timed_event(
    *,
    summary: str,
    description: str,
    start: datetime,
    end: datetime,
    time_zone: str,
    attendees: list[str] | None,
    add_google_meet: bool = True,
) -> dict[str, Any]:
    """Try Google Calendar first; on any failure fall back to SQLite ``calendar_events`` (weekly grid)."""
    from services.google_calendar_client import create_primary_timed_event
    from storage.sqlite_db import create_calendar_event

    if start.tzinfo is None or end.tzinfo is None:
        return {"success": False, "error": "internal", "detail": "start/end require tzinfo"}

    google_exc: Exception | None = None
    try:
        ev = create_primary_timed_event(
            summary=summary,
            start=start,
            end=end,
            description=description,
            attendees=attendees,
            time_zone=time_zone,
            add_google_meet=add_google_meet,
        )
        return {"success": True, "provider": "google_calendar", **ev}
    except (HttpError, FileNotFoundError, OSError, RuntimeError, ValueError) as e:
        google_exc = e
    except Exception as e:
        google_exc = e

    start_utc = start.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    end_utc = end.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        rid = create_calendar_event(
            title=summary,
            start_at=start_utc,
            end_at=end_utc,
            source="chat",
            notes=description or "",
        )
    except Exception as e:
        return {
            "success": False,
            "error": "persist_failed",
            "detail": str(e),
            "google_detail": str(google_exc) if google_exc else None,
        }

    out: dict[str, Any] = {
        "success": True,
        "provider": "sqlite",
        "sqlite_row_id": rid,
        "summary": summary,
        "start": start_utc,
        "end": end_utc,
    }
    if google_exc is not None:
        out["google_error"] = str(google_exc)
    return out


def try_create_meeting_from_chat(user_message: str, metadata: dict[str, Any] | None) -> str | None:
    """
    If ``user_message`` is a concrete meeting-scheduling request with a date anchor, create an event
    and return a user-facing reply. Otherwise return ``None`` so normal chat can run.
    """
    text = (user_message or "").strip()
    if len(text) < 8 or len(text) > 800:
        return None
    if not _looks_like_meeting_schedule_request(text):
        return None

    tz_name = _tz_name(metadata)
    start = _parse_start_local(text, tz_name)
    if start is None:
        return None

    duration_m = _default_duration_minutes(text)
    end = start + timedelta(minutes=duration_m)
    title = _meeting_title(text)
    attendees = list(dict.fromkeys(_RE_EMAIL.findall(text)))
    person = ""
    m_person = _RE_WITH_PERSON.search(text)
    if m_person:
        person = (m_person.group(1) or "").strip()
        if person.lower() in {"me", "myself"}:
            person = ""
    platform = ""
    m_platform = _RE_PLATFORM.search(text)
    if m_platform:
        platform = (m_platform.group(2) or "").strip()

    desc_parts = [f"Scheduled from chat ({duration_m} min)."]
    if person:
        desc_parts.append(f"Participant: {person}.")
    if platform:
        desc_parts.append(f"Platform: {platform}.")
    if attendees:
        desc_parts.append("Invitees: " + ", ".join(attendees))
    description = " ".join(desc_parts)

    result = persist_timed_event(
        summary=title,
        description=description,
        start=start,
        end=end,
        time_zone=tz_name,
        attendees=attendees or None,
        add_google_meet=True,
    )

    if not result.get("success"):
        return (
            "Something went wrong creating the calendar event ("
            + str(result.get("detail") or result.get("error") or "unknown")
            + "). You can try again in a moment."
        )

    when = start.strftime("%A, %B %d, %Y at %H:%M")

    prov = result.get("provider")
    link = str(result.get("html_link") or "").strip()
    meet = str(result.get("hangout_link") or "").strip()

    lines = [
        f'I added "{title}" to your schedule for {when} ({duration_m} minutes, your local time).',
    ]
    if prov == "google_calendar":
        if attendees:
            lines.append("Calendar invitations were sent to: " + ", ".join(attendees) + ".")
        elif person:
            lines.append(f'Participant noted: "{person}". Share their email to auto-send an invitation next time.')
        else:
            lines.append("It is on your Google Calendar with a Google Meet link.")
        if meet:
            lines.append(f"Meet: {meet}")
        elif link:
            lines.append(f"Open in Calendar: {link}")
    else:
        ge = str(result.get("google_error") or "").lower()
        if any(x in ge for x in ("403", "401", "invalid_grant", "invalid_scope", "invalid_google", "no_google")):
            lines.append(
                "Google Calendar sign-in is missing or expired, so I stored this on your in-app weekly schedule. "
                "Reconnect Google Calendar (re-consent scopes) to sync to Google and send email invites."
            )
        else:
            lines.append(
                "I stored this on your in-app weekly schedule. "
                "Connect or fix Google Calendar if you also want it in Google and Meet links."
            )

    return "\n".join(lines)


def create_event_from_api_payload(body: dict[str, Any]) -> dict[str, Any]:
    """
    Shared handler for ``POST /api/calendar/create`` — body matches SchedulerPage:
    ``summary``, ``start_time``, ``end_time`` (ISO UTC strings), optional ``description``, ``attendees``.
    """
    summary = str(body.get("summary") or "Event").strip() or "Event"
    description = str(body.get("description") or "").strip()
    start_raw = body.get("start_time") or body.get("startTime")
    end_raw = body.get("end_time") or body.get("endTime")
    if not start_raw or not end_raw:
        return {"success": False, "error": "missing_start_or_end"}

    try:
        s = str(start_raw).strip()
        e = str(end_raw).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        if e.endswith("Z"):
            e = e[:-1] + "+00:00"
        start = datetime.fromisoformat(s)
        end = datetime.fromisoformat(e)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
    except Exception:
        return {"success": False, "error": "invalid_datetime"}

    tz_name = _tz_name(body if isinstance(body, dict) else None)
    try:
        from zoneinfo import ZoneInfo

        start_local = start.astimezone(ZoneInfo(tz_name))
        end_local = end.astimezone(ZoneInfo(tz_name))
    except Exception:
        start_local = start.astimezone(timezone.utc)
        end_local = end.astimezone(timezone.utc)
        tz_name = "UTC"

    attendees_raw = body.get("attendees") or body.get("attendee_emails")
    attendees: list[str] | None = None
    if isinstance(attendees_raw, list):
        attendees = [str(x).strip() for x in attendees_raw if str(x).strip()]
    elif isinstance(attendees_raw, str) and attendees_raw.strip():
        attendees = [e.strip() for e in attendees_raw.split(",") if e.strip()]

    add_meet = bool(body.get("add_google_meet", True))
    return persist_timed_event(
        summary=summary,
        description=description,
        start=start_local,
        end=end_local,
        time_zone=tz_name,
        attendees=attendees,
        add_google_meet=add_meet,
    )
