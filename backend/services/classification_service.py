from __future__ import annotations

from typing import Any, Optional, Tuple

from services.classifier_ai import classify
from services.classification_context import build_classification_input
from utils.logger import get_logger

log = get_logger("classification_service")


def allowed_reply_type(value: Any) -> str:
    reply_type = str(value or "none").strip().lower()
    if reply_type not in {"none", "short", "time_relevant", "context_relevant"}:
        return "none"
    return reply_type


def classify_and_enrich(
    *,
    source: str,
    source_id: str,
    raw_text: str,
    text_for_classification: str,
    client_name: Optional[str],
    project_name: Optional[str],
    project_context: dict[str, Any] | None,
    project_resolution_reason: Optional[str],
    project_confidence: Any,
    needs_project_review: bool,
    force_draft_ready: bool,
) -> Tuple[dict[str, Any], Any, str, bool]:
    """
    Build LLM classification input, run classifier, normalize reply_type / has_action,
    and attach project metadata to the classification dict.
    """
    classification_input = build_classification_input(
        raw_message_text=text_for_classification or raw_text,
        client_name=client_name,
        project_name=project_name,
        project_context=project_context,
    )

    log.info(f"[CLASSIFY_INPUT_RAW:{source}] source_id={source_id} text={repr(raw_text)}")
    log.info(
        f"[CLASSIFY_INPUT_CLEAN:{source}] source_id={source_id} "
        f"text={repr(text_for_classification or raw_text)}"
    )
    log.info(
        f"[CLASSIFY_INPUT_CONTEXT:{source}] source_id={source_id} "
        f"text={repr(classification_input)}"
    )

    classification = classify(
        classification_input,
        raw_text=(text_for_classification or raw_text),
    ) or {}

    has_action = bool(classification.get("has_action"))
    reply_type = allowed_reply_type(classification.get("reply_type"))

    classification["has_action"] = has_action
    classification["reply_type"] = reply_type
    classification["client_name"] = client_name
    classification["project_name"] = project_name
    classification["project_resolution_reason"] = project_resolution_reason
    classification["project_confidence"] = project_confidence
    classification["needs_project_review"] = needs_project_review

    if source == "gmail" and force_draft_ready and reply_type == "none":
        reply_type = "short"
        classification["reply_type"] = reply_type

    return classification, classification_input, reply_type, has_action
