from __future__ import annotations

from typing import Any, Optional, Tuple

from integrations.grafik import create_grafik_task
from services.task_linker import find_existing_task_for_message
from storage.sqlite_db import upsert_task


def _as_bool(value: Any) -> bool:
    return bool(value is True or value == 1 or str(value).strip().lower() in {"true", "1", "yes", "y"})


def run_task_link_phase(
    *,
    payload: dict[str, Any],
    client_id: Optional[int],
    project_id: Optional[int],
    raw_text: str,
    text_for_classification: str,
    classification: dict[str, Any],
    follow_up_candidate: dict[str, Any],
) -> Tuple[dict[str, Any], bool, Optional[str]]:
    """Returns (task_link_result, task_link_skipped, task_link_skip_reason)."""
    skip_task_link = _as_bool(payload.get("skip_task_link", False))
    if skip_task_link:
        return (
            {
                "matched": False,
                "reason": "skipped",
                "task_id": None,
                "grafik_task_id": None,
                "confidence": 0.0,
                "needs_review": False,
            },
            True,
            "payload_skip_task_link",
        )
    task_link_result = find_existing_task_for_message(
        client_id=client_id,
        project_id=project_id,
        raw_text=(text_for_classification or raw_text),
        classification=classification,
        follow_up_candidate=follow_up_candidate,
    )
    return task_link_result, False, None


def build_grafik_task_title_and_description(
    *,
    source: str,
    classification: dict[str, Any],
    subject: Optional[str],
    text_for_classification: str,
    raw_text: str,
    client_name: Optional[str],
    project_name: Optional[str],
    project_resolution_reason: Optional[str],
    project_confidence: Any,
    needs_project_review: bool,
    workspace_id: Optional[str],
    channel: Optional[str],
    channel_type: Optional[str],
    thread_id: Optional[str],
    ts: Optional[str],
    sender: Optional[str],
    recipient: Optional[str],
    user_id: Optional[str],
    project_update_candidate: dict[str, Any],
    follow_up_candidate: dict[str, Any],
    project_context: dict[str, Any] | None,
    classification_input: Any,
) -> Tuple[str, str]:
    base_title = classification.get("title") or (
        f"{source.capitalize()}: {(subject or text_for_classification or raw_text)[:50]}"
        if (subject or text_for_classification or raw_text)
        else f"{source.capitalize()}: (no text)"
    )
    title = f"[{client_name}] {base_title}" if client_name else base_title

    context_block = ""
    if project_context:
        context_block = (
            "\n\nProject Context:\n"
            f"Summary: {project_context.get('summary')}\n"
            f"Current Status: {project_context.get('current_status')}\n"
            f"Current Priorities: {project_context.get('current_priorities')}\n"
            f"Blockers: {project_context.get('blockers')}\n"
            f"Next Steps: {project_context.get('next_steps')}\n"
        )

    description = (
        f"Client: {client_name or 'Unknown'}\n"
        f"Project: {project_name or 'Unknown'}\n"
        f"Project Resolution: {project_resolution_reason or 'unknown'}\n"
        f"Project Confidence: {project_confidence}\n"
        f"Needs Project Review: {needs_project_review}\n"
        f"Source: {source}\n"
        f"Workspace ID: {workspace_id}\n"
        f"Channel: {channel}\n"
        f"Channel Type: {channel_type}\n"
        f"Thread ID: {thread_id}\n"
        f"TS: {ts}\n"
        f"Sender: {sender}\n"
        f"Recipient: {recipient}\n"
        f"User ID: {user_id}\n"
        f"Subject: {subject}\n\n"
        f"Classification:\n{classification}\n"
        f"Project Update Candidate:\n{project_update_candidate}\n"
        f"Follow-up Candidate:\n{follow_up_candidate}\n"
        f"{context_block}\n"
        f"Raw Message:\n{raw_text}\n\n"
        f"Text Used For Heuristics:\n{text_for_classification or raw_text}\n\n"
        f"Text Used For LLM Classification:\n{classification_input}\n"
    )
    return title, description


def create_grafik_task_and_record(
    *,
    source: str,
    source_id: str,
    list_id: str,
    title: str,
    description: str,
    classification: dict[str, Any],
    client_id: Optional[int],
    project_id: Optional[int],
) -> str:
    grafik_task_id = create_grafik_task(list_id, title, description)
    upsert_task(
        source=source,
        source_id=source_id,
        grafik_task_id=grafik_task_id,
        title=title,
        description=description,
        classification=classification,
        client_id=client_id,
        project_id=project_id,
    )
    return str(grafik_task_id)
