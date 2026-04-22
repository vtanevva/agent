from __future__ import annotations

from typing import Any

from storage.sqlite_db import (
    log_event,
    set_gmail_draft_result,
    try_acquire_gmail_draft_lock,
)
from utils.logger import get_logger

log = get_logger("reply_service")


def maybe_create_gmail_draft(
    *,
    ingest_source: str,
    workspace_id: str | None,
    source_id: str,
    thread_id: str | None,
    message_id: str | None,
    sender: str | None,
    subject: str | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a Gmail draft when orchestration requested one.
    Returns {"draft_status": str, "draft_id": str|None}.
    """
    draft_id = None
    draft_status = "skipped"

    if result.get("reply_policy", {}).get("should_reply") and result.get("reply_policy", {}).get("reply_mode") == "draft_ready" and not result.get("should_create_draft"):
        log.info(
            f"[GMAIL_DRAFT_SKIP:{ingest_source}] source_id={source_id} "
            f"reason=missing_real_gmail_ids_or_forced_skip "
            f"thread_id={thread_id} message_id={message_id}"
        )

    if result.get("should_create_draft") and result.get("reply_text"):
        try:
            from services.gmail_auth import get_gmail_service
            from services.gmail_draft import create_gmail_draft

            gmail_service = get_gmail_service()

            draft_subject = subject
            if subject and not subject.lower().startswith("re:"):
                draft_subject = f"Re: {subject}"
            elif not subject:
                draft_subject = "Re:"

            if not try_acquire_gmail_draft_lock(
                message_id=str(message_id),
                source_id=source_id,
                thread_id=thread_id,
            ):
                return {"draft_status": "skipped", "draft_id": None}

            draft_id = create_gmail_draft(
                service=gmail_service,
                to_email=sender,
                subject=draft_subject,
                reply_text=result.get("reply_text"),
                thread_id=thread_id,
                message_id=message_id,
            )
            set_gmail_draft_result(message_id=str(message_id), draft_id=str(draft_id), status="ok")

            draft_status = "created"

            log.info(
                f"[GMAIL_DRAFT:{ingest_source}] source_id={source_id} "
                f"draft_id={draft_id} thread_id={thread_id}"
            )

            log_event(
                source=ingest_source,
                source_id=source_id,
                step="gmail_draft_create",
                status="ok",
                data={
                    "workspace_id": workspace_id,
                    "draft_id": draft_id,
                    "thread_id": thread_id,
                    "reply_type": (result.get("classification") or {}).get("reply_type"),
                },
            )

        except Exception as err:
            set_gmail_draft_result(message_id=str(message_id), draft_id=None, status="error", error=str(err))
            draft_status = "error"

            log.exception(
                f"[GMAIL_DRAFT_ERROR:{ingest_source}] source_id={source_id} -> {err}"
            )

            log_event(
                source=ingest_source,
                source_id=source_id,
                step="gmail_draft_create",
                status="error",
                data={
                    "workspace_id": workspace_id,
                    "thread_id": thread_id,
                    "reply_type": (result.get("classification") or {}).get("reply_type"),
                    "error": str(err),
                },
            )

    return {"draft_status": draft_status, "draft_id": draft_id}

