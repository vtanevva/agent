from __future__ import annotations

import re
from typing import Any, Literal


ReplyMode = Literal["none", "suggestion_only", "draft_ready"]


_RE_EXPLICIT_RESPONSE = re.compile(
    r"\b(let me know|please confirm|please reply|can you confirm|could you confirm|do you have|did you|any update|any updates|follow up)\b",
    re.IGNORECASE,
)

_RE_LOW_VALUE_INFO = re.compile(
    r"^\s*(fyi|for your information|note|just letting you know|status update)\b",
    re.IGNORECASE,
)


def _safe_text(value: Any) -> str:
    return (str(value) if value is not None else "").strip()


def _is_question(text: str) -> bool:
    t = _safe_text(text)
    return ("?" in t) or bool(re.match(r"^\s*(what|when|where|why|how|who)\b", t, re.IGNORECASE))


def _expects_response(text: str) -> bool:
    t = _safe_text(text)
    if not t:
        return False
    if _is_question(t):
        return True
    return bool(_RE_EXPLICIT_RESPONSE.search(t))


def _is_low_value_info(text: str) -> bool:
    t = _safe_text(text)
    if not t:
        return False
    if _RE_LOW_VALUE_INFO.search(t) and not _expects_response(t):
        return True
    return False


def decide_reply_policy(
    *,
    channel: str,  # "slack" or "gmail"
    classification: dict,
    clean_text: str,
    project_context: dict | None = None,
    follow_up_candidate: dict | None = None,
    project_update_candidate: dict | None = None,
) -> dict[str, Any]:
    channel = (channel or "").strip().lower()
    cls = classification or {}

    reply_type = _safe_text(cls.get("reply_type") or "none").lower()
    has_action = bool(cls.get("has_action"))
    try:
        conf = float(cls.get("confidence", 0.0))
    except Exception:
        conf = 0.0

    is_follow_up = bool((follow_up_candidate or {}).get("is_follow_up"))
    has_project_update = bool((project_update_candidate or {}).get("has_project_update"))
    expects_response = _expects_response(clean_text)
    low_value_info = _is_low_value_info(clean_text)

    # A) Global suppressions
    if reply_type == "none":
        return {
            "should_reply": False,
            "reply_mode": "none",
            "reason": "reply_type_none",
            "confidence": conf,
            "needs_review": False,
        }

    if conf <= 0.10:
        return {
            "should_reply": False,
            "reply_mode": "none",
            "reason": "low_classifier_confidence",
            "confidence": conf,
            "needs_review": True,
        }

    # D) Project update messages are often informative; be conservative.
    if has_project_update and (not has_action) and (not is_follow_up) and (not expects_response):
        if channel == "gmail":
            return {
                "should_reply": True,
                "reply_mode": "suggestion_only",
                "reason": "project_update_informational",
                "confidence": conf,
                "needs_review": False,
            }
        return {
            "should_reply": False,
            "reply_mode": "none",
            "reason": "project_update_informational_slack_suppress",
            "confidence": conf,
            "needs_review": False,
        }

    # B) Slack policy
    if channel == "slack":
        if low_value_info and (not is_follow_up) and (not has_action) and (not expects_response):
            return {
                "should_reply": False,
                "reply_mode": "none",
                "reason": "low_value_info_slack",
                "confidence": conf,
                "needs_review": False,
            }

        if reply_type in {"short", "time_relevant", "context_relevant"}:
            # Slack replies are suggestions only; never auto-send.
            return {
                "should_reply": True,
                "reply_mode": "suggestion_only",
                "reason": "slack_suggest",
                "confidence": conf,
                "needs_review": False,
            }

        return {
            "should_reply": False,
            "reply_mode": "none",
            "reason": "slack_unknown_reply_type",
            "confidence": conf,
            "needs_review": True,
        }

    # C) Gmail policy
    if channel == "gmail":
        if low_value_info and (not is_follow_up) and (not has_action) and (not expects_response):
            return {
                "should_reply": False,
                "reply_mode": "none",
                "reason": "low_value_info_gmail",
                "confidence": conf,
                "needs_review": False,
            }

        allow_draft_ready = bool(expects_response or is_follow_up or has_action or reply_type == "time_relevant")
        if allow_draft_ready:
            return {
                "should_reply": True,
                "reply_mode": "draft_ready",
                "reason": "gmail_draft_allowed",
                "confidence": conf,
                "needs_review": False,
            }

        return {
            "should_reply": True,
            "reply_mode": "suggestion_only",
            "reason": "gmail_suggestion_only",
            "confidence": conf,
            "needs_review": False,
        }

    # Unknown channel: safest fallback
    return {
        "should_reply": False,
        "reply_mode": "none",
        "reason": "unknown_channel",
        "confidence": conf,
        "needs_review": True,
    }

