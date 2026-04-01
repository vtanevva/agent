import re
from typing import Any


_RE_ANY_UPDATE = re.compile(
    r"\b(any update|any updates|update on that|update on this|any news|what'?s the update|status update)\b",
    re.IGNORECASE,
)

_RE_STATUS_CHECK = re.compile(
    r"\b(what'?s the status|status\?|where are we on|where do we stand|did we send|did you send|did we hear back|did you hear back)\b",
    re.IGNORECASE,
)

_RE_FOLLOW_UP = re.compile(
    r"\b(follow up on|follow-up on|can you follow up|please follow up|check in on|check on this)\b",
    re.IGNORECASE,
)

_RE_PROGRESS_CHECK = re.compile(
    r"\b(still in progress\?|is this done\?|is that done\?|done yet\?|sent yet\?|finished yet\?)\b",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    return " ".join((text or "").strip().split())


def detect_follow_up_candidate(text: str) -> dict[str, Any]:
    """
    Detect whether the message looks like a follow-up to existing work.
    LOG ONLY for now. Do not auto-link tasks yet.
    """
    clean_text = _clean(text)

    if not clean_text:
        return {
            "is_follow_up": False,
            "confidence": 0.0,
            "reason": "empty_text",
            "matched_pattern": None,
            "needs_task_link_review": False,
            "linked_task_id": None,
        }

    matched_pattern = None
    confidence = 0.0

    if _RE_ANY_UPDATE.search(clean_text):
        matched_pattern = "any_update"
        confidence = 0.84
    elif _RE_STATUS_CHECK.search(clean_text):
        matched_pattern = "status_check"
        confidence = 0.82
    elif _RE_FOLLOW_UP.search(clean_text):
        matched_pattern = "follow_up_request"
        confidence = 0.86
    elif _RE_PROGRESS_CHECK.search(clean_text):
        matched_pattern = "progress_check"
        confidence = 0.78

    is_follow_up = matched_pattern is not None

    return {
        "is_follow_up": is_follow_up,
        "confidence": confidence if is_follow_up else 0.0,
        "reason": "matched_follow_up_pattern" if is_follow_up else "no_match",
        "matched_pattern": matched_pattern,
        "needs_task_link_review": is_follow_up,
        "linked_task_id": None,
    }