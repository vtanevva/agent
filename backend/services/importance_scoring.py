from __future__ import annotations

import re
from typing import Any, Literal


ImportanceLevel = Literal["low", "medium", "high", "critical"]


_RE_URGENCY = re.compile(
    r"\b(asap|urgent|today|tomorrow|tonight|deadline|by\s+\w+|by\s+\d{1,2}|eod|end of day)\b",
    re.IGNORECASE,
)


def _safe_bool(value: Any) -> bool:
    return bool(value is True or value == 1 or str(value).strip().lower() in {"true", "1", "yes", "y"})


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _has_urgency(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_RE_URGENCY.search(t))


def _has_blocker(project_update_candidate: dict | None, continuity_context: dict | None) -> bool:
    puc = project_update_candidate or {}
    fields = puc.get("fields") or {}
    if isinstance(fields, dict):
        blocker_text = (fields.get("blockers") or "").strip() if fields.get("blockers") is not None else ""
        if blocker_text:
            return True

    ctx = continuity_context or {}
    project_context = ctx.get("project_context") or {}
    if isinstance(project_context, dict):
        blockers = (project_context.get("blockers") or "").strip()
        if blockers:
            return True
    return False


def _level_from_score(score: int) -> ImportanceLevel:
    s = max(0, min(100, int(score)))
    if s <= 24:
        return "low"
    if s <= 49:
        return "medium"
    if s <= 74:
        return "high"
    return "critical"


def score_message_importance(
    *,
    classification: dict,
    project_update_candidate: dict | None = None,
    follow_up_candidate: dict | None = None,
    task_link_result: dict | None = None,
    continuity_context: dict | None = None,
    clean_text: str = "",
    channel: str = "",
) -> dict[str, Any]:
    """
    Explainable, generic importance scoring (0-100).
    This is advisory only: it must not change behavior directly.
    """
    cls = classification or {}
    reply_type = str(cls.get("reply_type") or "none").strip().lower()
    has_action = _safe_bool(cls.get("has_action"))
    time_relevant = reply_type == "time_relevant"

    follow_up = _safe_bool((follow_up_candidate or {}).get("is_follow_up"))
    has_project_update = _safe_bool((project_update_candidate or {}).get("has_project_update"))

    tlr = task_link_result or {}
    linked_existing_task = _safe_bool(tlr.get("matched"))

    ctx_summary = (continuity_context or {}).get("summary") or {}
    open_follow_up_count = _safe_int(ctx_summary.get("open_follow_up_count"), 0)
    recent_task_count = _safe_int(ctx_summary.get("recent_task_count"), 0)

    urgency = _has_urgency(clean_text)
    blocker = _has_blocker(project_update_candidate, continuity_context)

    features = {
        "has_action": has_action,
        "time_relevant": time_relevant,
        "follow_up": follow_up,
        "has_blocker": blocker,
        "has_project_update": has_project_update,
        "linked_existing_task": linked_existing_task,
        "open_follow_up_count": open_follow_up_count,
        "recent_task_count": recent_task_count,
    }

    score = 0
    reasons: list[str] = []

    # Weighted, conservative signals (generic, explainable)
    if has_action:
        score += 35
        reasons.append("has_action")

    if time_relevant:
        score += 15
        reasons.append("reply_type_time_relevant")

    if urgency:
        score += 15
        reasons.append("urgency_language")

    if follow_up:
        score += 15
        reasons.append("follow_up")

    if blocker:
        score += 20
        reasons.append("blocker_signal")

    if has_project_update:
        score += 5
        reasons.append("project_update_detected")

    if linked_existing_task:
        score += 10
        reasons.append("linked_existing_task")

    if open_follow_up_count > 0:
        score += 5
        reasons.append("has_open_follow_ups_in_context")

    if recent_task_count > 0:
        score += 3
        reasons.append("recent_tasks_in_context")

    # If there are no positive signals, keep it explicitly low and explain why.
    if score == 0:
        reasons.append("no_action_no_follow_up_no_urgency")

    score = max(0, min(100, score))
    level = _level_from_score(score)

    return {
        "importance_score": int(score),
        "importance_level": level,
        "importance_reasons": reasons,
        "features": features,
        "channel": (channel or "").strip().lower() or None,
    }

