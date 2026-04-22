from __future__ import annotations

from typing import Any

from services.continuity_context import build_continuity_context
from services.project_context_updater import update_project_context_from_candidate
from services.reply_writer import generate_reply
from services.task_linker import find_existing_task_for_message


def search_memory(*, client_id: int | None, project_id: int | None) -> dict[str, Any]:
    """Tool-like function for querying recent continuity context."""
    return build_continuity_context(client_id=client_id, project_id=project_id)


def get_thread_context(*, client_id: int | None, project_id: int | None) -> dict[str, Any]:
    """Alias of memory lookup with explicit conversational naming."""
    return build_continuity_context(client_id=client_id, project_id=project_id)


def draft_reply(
    *,
    original_text: str,
    reply_type: str,
    summary: str | None,
    sender: str | None,
    project_name: str | None,
    project_context: dict[str, Any] | None,
    project_update_candidate: dict[str, Any] | None,
    classification: dict[str, Any] | None,
    channel: str,
) -> str:
    return generate_reply(
        original_text=original_text,
        reply_type=reply_type,
        summary=summary,
        sender=sender,
        project_name=project_name,
        project_context=project_context,
        project_update_candidate=project_update_candidate,
        classification=classification or {},
        channel=channel,
    )


def create_task(
    *,
    client_id: int | None,
    project_id: int | None,
    raw_text: str,
    classification: dict[str, Any] | None,
    follow_up_candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    """Conservative helper: first try linking to an existing task."""
    return find_existing_task_for_message(
        client_id=client_id,
        project_id=project_id,
        raw_text=raw_text,
        classification=classification or {},
        follow_up_candidate=follow_up_candidate or {},
    )


def update_project_memory(
    *,
    project_id: int | None,
    candidate: dict[str, Any] | None,
    updated_by: str = "system",
) -> dict[str, Any]:
    return update_project_context_from_candidate(
        project_id=project_id,
        candidate=candidate,
        updated_by=updated_by,
    )

