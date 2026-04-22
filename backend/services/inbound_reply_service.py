from __future__ import annotations

from typing import Any, Optional

from services.reply_policy import decide_reply_policy
from services.reply_writer import generate_reply


def compute_reply_policy(
    *,
    source: str,
    raw_text: str,
    text_for_classification: str,
    classification: dict[str, Any],
    project_context: dict[str, Any] | None,
    follow_up_candidate: dict[str, Any],
    project_update_candidate: dict[str, Any],
    force_draft_ready: bool,
) -> dict[str, Any]:
    policy_clean_text = (text_for_classification or raw_text) if source == "slack" else raw_text
    reply_policy = decide_reply_policy(
        channel=source,
        classification=classification,
        clean_text=policy_clean_text,
        project_context=project_context,
        follow_up_candidate=follow_up_candidate,
        project_update_candidate=project_update_candidate,
    )
    if source == "gmail" and force_draft_ready:
        reply_policy = {
            "should_reply": True,
            "reply_mode": "draft_ready",
            "reason": "force_draft_ready",
            "confidence": float(classification.get("confidence", 1.0) or 1.0),
            "needs_review": False,
        }
    return reply_policy


def maybe_generate_reply_text(
    *,
    reply_policy: dict[str, Any],
    raw_text: str,
    reply_type: str,
    classification: dict[str, Any],
    sender: Optional[str],
    user_id: Optional[str],
    project_name: Optional[str],
    project_context: dict[str, Any] | None,
    project_update_candidate: dict[str, Any],
    source: str,
) -> Optional[str]:
    if not bool(reply_policy.get("should_reply")):
        return None
    return generate_reply(
        original_text=raw_text,
        reply_type=reply_type,
        summary=classification.get("summary"),
        sender=sender or user_id,
        project_name=project_name,
        project_context=project_context,
        project_update_candidate=project_update_candidate,
        classification=classification,
        channel=source,
    )


def should_create_gmail_draft(
    *,
    source: str,
    reply_policy: dict[str, Any],
    reply_text: Optional[str],
    force_skip_draft: bool,
    thread_id: Optional[str],
    message_id: Optional[str],
) -> bool:
    has_real_gmail_ids = bool(source == "gmail" and thread_id and message_id)
    return bool(
        source == "gmail"
        and reply_policy.get("reply_mode") == "draft_ready"
        and bool(reply_policy.get("should_reply"))
        and (not force_skip_draft)
        and has_real_gmail_ids
        and bool(reply_text)
    )
