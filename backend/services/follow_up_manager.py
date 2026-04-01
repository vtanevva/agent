from __future__ import annotations

from typing import Any

from storage.sqlite_db import insert_follow_up_if_new


CONFIDENCE_THRESHOLD = 0.80


def _map_type(candidate: dict[str, Any]) -> str:
    matched = (candidate.get("matched_pattern") or "").strip().lower()
    # Keep it simple for now.
    if matched in {"follow_up_request"}:
        return "follow_up"
    if matched in {"any_update", "status_check", "progress_check"}:
        return "awaiting_response"
    return "follow_up"


def create_follow_up_from_candidate(
    *,
    source: str,
    source_id: str,
    client_id: int | None,
    project_id: int | None,
    candidate: dict[str, Any] | None,
    due_at: str | None = None,
) -> dict[str, Any]:
    cand = candidate or {}

    if not bool(cand.get("is_follow_up")):
        return {
            "created": False,
            "follow_up_id": None,
            "type": None,
            "skipped_reason": "not_follow_up",
        }

    try:
        confidence = float(cand.get("confidence", 0.0))
    except Exception:
        confidence = 0.0

    if confidence < CONFIDENCE_THRESHOLD:
        return {
            "created": False,
            "follow_up_id": None,
            "type": None,
            "skipped_reason": f"low_confidence:{confidence:.2f}",
        }

    fu_type = _map_type(cand)
    created, fu_id = insert_follow_up_if_new(
        source=source,
        source_id=source_id,
        client_id=client_id,
        project_id=project_id,
        type=fu_type,
        status="open",
        due_at=due_at,
    )

    return {
        "created": bool(created),
        "follow_up_id": fu_id,
        "type": fu_type,
        "skipped_reason": None if created else "duplicate",
        "confidence": confidence,
        "matched_pattern": cand.get("matched_pattern"),
    }

