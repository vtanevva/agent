from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal


DueType = Literal["date", "datetime", "relative", "unknown"]
TimePressure = Literal["none", "low", "medium", "high"]


_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


_RE_URGENCY_WORDS = re.compile(
    r"\b(asap|urgent|immediately|today|tomorrow|tonight|this week|next week|deadline|eod|end of day)\b",
    re.IGNORECASE,
)

_RE_DUE_PHRASE = re.compile(
    r"\b(due by|needed by|need it by|need it before|before|by|on)\s+"
    r"(?P<when>"
    r"today|tomorrow|tonight|this week|next week|"
    r"next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r")"
    r"(?P<time>\s+at\s+[^\,\.\;\n]+)?",
    re.IGNORECASE,
)

_RE_NEXT_WEEKDAY = re.compile(r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE)
_RE_WEEKDAY = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE)

_RE_TIME_12H = re.compile(r"\b(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>am|pm)\b", re.IGNORECASE)
_RE_TIME_24H = re.compile(r"\b(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)\b")

_RE_BLOCKED_WORD = re.compile(r"\b(blocked|blocker|blocking)\b", re.IGNORECASE)


def _safe_str(value: Any) -> str:
    return (str(value) if value is not None else "").strip()


def _parse_now(now_utc: str | None) -> datetime:
    if now_utc:
        try:
            s = now_utc.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def _weekday_to_date(now: datetime, weekday: int, *, force_next: bool) -> datetime:
    delta = (weekday - now.weekday()) % 7
    if force_next and delta == 0:
        delta = 7
    return (now + timedelta(days=delta)).replace(hour=0, minute=0, second=0, microsecond=0)


def _extract_time(text: str) -> tuple[int, int] | None:
    t = text or ""

    m24 = _RE_TIME_24H.search(t)
    if m24:
        return int(m24.group("h")), int(m24.group("m"))

    m12 = _RE_TIME_12H.search(t)
    if m12:
        h = int(m12.group("h"))
        minute = int(m12.group("m") or "0")
        ampm = (m12.group("ampm") or "").lower()
        if h == 12:
            h = 0
        if ampm == "pm":
            h += 12
        return h, minute

    return None


@dataclass(frozen=True)
class _NormalizedDue:
    type: DueType
    value: str | None
    confidence: float


def _normalize_due_hint(due_hint_text: str, now: datetime) -> _NormalizedDue:
    hint = (due_hint_text or "").strip().lower()
    if not hint:
        return _NormalizedDue(type="unknown", value=None, confidence=0.0)

    # Strip leading cue words so "by tomorrow" / "due by Friday" normalize like "tomorrow" / "Friday".
    for prefix in (
        "due by ",
        "needed by ",
        "need it by ",
        "need it before ",
        "before ",
        "by ",
        "on ",
    ):
        if hint.startswith(prefix):
            hint = hint[len(prefix) :].strip()
            break

    # Relative anchors
    if hint == "today":
        return _NormalizedDue(type="date", value=now.date().isoformat(), confidence=0.9)
    if hint == "tomorrow":
        return _NormalizedDue(type="date", value=(now.date() + timedelta(days=1)).isoformat(), confidence=0.9)
    if hint.startswith("tonight"):
        # If we have a time, caller will promote to datetime.
        return _NormalizedDue(type="relative", value="tonight", confidence=0.7)
    if hint in {"this week", "next week"}:
        return _NormalizedDue(type="relative", value=hint, confidence=0.5)

    # next weekday
    m_next = _RE_NEXT_WEEKDAY.search(hint)
    if m_next:
        wd = _WEEKDAYS[m_next.group(1).lower()]
        d = _weekday_to_date(now, wd, force_next=True).date().isoformat()
        return _NormalizedDue(type="date", value=d, confidence=0.82)

    # weekday
    m_wd = _RE_WEEKDAY.search(hint)
    if m_wd:
        wd = _WEEKDAYS[m_wd.group(1).lower()]
        d = _weekday_to_date(now, wd, force_next=False).date().isoformat()
        return _NormalizedDue(type="date", value=d, confidence=0.75)

    return _NormalizedDue(type="unknown", value=None, confidence=0.3)


def _derive_time_pressure_level(
    *,
    has_signal: bool,
    urgency: bool,
    normalized_due: _NormalizedDue,
    due_dt: datetime | None,
    now: datetime,
    blocker: bool,
) -> tuple[TimePressure, list[str], bool, bool]:
    if not has_signal:
        return "none", ["no_schedule_signal"], False, False

    reasons: list[str] = []
    overdue_risk = False
    upcoming_risk = False

    # Determine an approximate due datetime for risk.
    if due_dt is None and normalized_due.type == "date" and normalized_due.value:
        try:
            d = datetime.fromisoformat(normalized_due.value).date()
            due_dt = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
        except Exception:
            due_dt = None

    if due_dt is not None:
        delta = due_dt - now
        if delta.total_seconds() < 0:
            overdue_risk = True
            reasons.append("due_in_past")
        else:
            if delta <= timedelta(days=1):
                upcoming_risk = True
                reasons.append("due_within_24h")
            elif delta <= timedelta(days=3):
                upcoming_risk = True
                reasons.append("due_within_3d")
            elif delta <= timedelta(days=7):
                upcoming_risk = True
                reasons.append("due_within_7d")

    if urgency:
        reasons.append("urgency_language")

    if blocker:
        reasons.append("blocker_signal")

    # Base pressure from urgency/due proximity
    pressure: TimePressure = "low"
    if overdue_risk:
        pressure = "high"
    elif urgency:
        pressure = "high"
    elif "due_within_24h" in reasons:
        pressure = "high"
    elif "due_within_3d" in reasons:
        pressure = "medium"
    elif "due_within_7d" in reasons and normalized_due.type in {"date", "datetime"}:
        pressure = "medium"
    elif normalized_due.type in {"date", "datetime"}:
        pressure = "low"
    else:
        pressure = "low"

    # Minimal safe bump: blockers + timing should feel more pressured
    if blocker and pressure in {"low", "medium"}:
        pressure = "medium" if pressure == "low" else "high"

    return pressure, reasons, overdue_risk, upcoming_risk


def analyze_scheduling_signals(
    *,
    clean_text: str,
    classification: dict | None = None,
    project_update_candidate: dict | None = None,
    follow_up_candidate: dict | None = None,
    continuity_context: dict | None = None,
    now_utc: str | None = None,
) -> dict[str, Any]:
    """
    Extract and conservatively normalize time-related signals.

    When a concrete time or calendar day is inferred, ``task_due_datetime`` is an ISO-8601 UTC
    string (``…Z``) stored on the message classification / SQLite task payload for scheduling UIs.
    """
    text = _safe_str(clean_text)
    now = _parse_now(now_utc)

    schedule_signals: list[str] = []
    time_reasons: list[str] = []

    urgency = bool(_RE_URGENCY_WORDS.search(text)) if text else False
    if urgency:
        schedule_signals.append("urgency_word")

    # Use classification hint (non-authoritative)
    reply_type = _safe_str((classification or {}).get("reply_type")).lower()
    if reply_type == "time_relevant":
        schedule_signals.append("time_relevant_reply_type")

    # Extract due hint phrase (prefer explicit due-like phrasing)
    due_hint_text: str | None = None
    m_due = _RE_DUE_PHRASE.search(text)
    if m_due:
        kw = _safe_str(m_due.group(1)).lower()
        when = _safe_str(m_due.group("when"))
        time_part = _safe_str(m_due.group("time"))
        due_hint_text = f"{kw} {when}{time_part}".strip()
        schedule_signals.append("due_phrase")
    else:
        # Fallback: relative words without explicit "by/before"
        for w in ["tomorrow", "today", "tonight", "this week", "next week"]:
            if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE):
                due_hint_text = w
                schedule_signals.append("relative_reference")
                break

        if due_hint_text is None:
            m_next = _RE_NEXT_WEEKDAY.search(text)
            if m_next:
                due_hint_text = f"next {m_next.group(1)}"
                schedule_signals.append("next_weekday_reference")
            else:
                m_wd = _RE_WEEKDAY.search(text)
                if m_wd:
                    due_hint_text = m_wd.group(1)
                    schedule_signals.append("weekday_reference")

    # Time-of-day signal
    time_tuple = _extract_time(text)
    if time_tuple:
        schedule_signals.append("time_of_day")

    # Blocker signal for timing context (keep generic)
    blocker = bool(_RE_BLOCKED_WORD.search(text)) or bool(
        (project_update_candidate or {}).get("fields", {}) and ((project_update_candidate or {}).get("fields") or {}).get("blockers")
    )

    normalized_due = _NormalizedDue(type="unknown", value=None, confidence=0.0)
    due_dt: datetime | None = None

    if due_hint_text:
        normalized_due = _normalize_due_hint(due_hint_text, now)
        if normalized_due.type == "date" and normalized_due.value and time_tuple:
            try:
                d = datetime.fromisoformat(normalized_due.value).date()
                h, m = time_tuple
                due_dt = datetime(d.year, d.month, d.day, h, m, 0, tzinfo=timezone.utc)
                normalized_due = _NormalizedDue(type="datetime", value=due_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z"), confidence=min(0.9, normalized_due.confidence + 0.1))
            except Exception:
                pass
        elif normalized_due.type == "relative" and normalized_due.value == "tonight" and time_tuple:
            h, m = time_tuple
            due_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            normalized_due = _NormalizedDue(type="datetime", value=due_dt.isoformat().replace("+00:00", "Z"), confidence=0.8)

    has_schedule_signal = bool(schedule_signals)

    # Interpret "before <weekday>" as a schedule signal even if normalization is weak.
    if due_hint_text and due_hint_text.lower().startswith("before "):
        schedule_signals.append("before_phrase")
        has_schedule_signal = True
        if normalized_due.type == "unknown":
            # Treat as "by <weekday>" with lower confidence.
            normalized_due = _normalize_due_hint(due_hint_text.lower().replace("before ", ""), now)
            normalized_due = _NormalizedDue(type=normalized_due.type, value=normalized_due.value, confidence=min(0.65, normalized_due.confidence))

    pressure, reasons, overdue_risk, upcoming_risk = _derive_time_pressure_level(
        has_signal=has_schedule_signal,
        urgency=urgency,
        normalized_due=normalized_due,
        due_dt=due_dt,
        now=now,
        blocker=blocker,
    )
    time_reasons.extend(reasons)

    # Single ISO instant for task + scheduler UI (SQLite classification_json / Expo).
    task_due_datetime: str | None = None
    if due_dt is not None:
        task_due_datetime = due_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    elif normalized_due.type == "datetime" and normalized_due.value:
        v = _safe_str(normalized_due.value)
        if v:
            task_due_datetime = v if v.endswith("Z") else v.replace("+00:00", "Z")
    elif normalized_due.type == "date" and normalized_due.value:
        try:
            d = datetime.fromisoformat(normalized_due.value).date()
            # No clock time in text: anchor at noon UTC on that calendar day (week grid + lists).
            noon = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc)
            task_due_datetime = noon.isoformat().replace("+00:00", "Z")
        except Exception:
            task_due_datetime = None

    return {
        "has_schedule_signal": has_schedule_signal,
        "schedule_signals": sorted(list(set(schedule_signals))),
        "due_hint_text": due_hint_text,
        "normalized_due": {
            "type": normalized_due.type if has_schedule_signal else None,
            "value": normalized_due.value if has_schedule_signal else None,
            "confidence": float(normalized_due.confidence if has_schedule_signal else 0.0),
        },
        "time_pressure_level": pressure,
        "time_reasons": sorted(list(set(time_reasons))),
        "overdue_risk": bool(overdue_risk),
        "upcoming_risk": bool(upcoming_risk),
        "task_due_datetime": task_due_datetime,
    }

