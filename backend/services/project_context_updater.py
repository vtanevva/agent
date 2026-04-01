from __future__ import annotations

from typing import Any

from storage.sqlite_db import (
    get_project_by_id,
    get_project_context_fields,
    update_project_context_fields,
)


CONFIDENCE_THRESHOLD = 0.70
SUPPORTED_FIELDS = {
    "summary",
    "current_status",
    "current_priorities",
    "blockers",
    "next_steps",
}

_BAD_VALUES = {"unknown", "n/a", "na", "none", "null", "nil"}


def _clean_value(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.lower() in _BAD_VALUES:
        return None
    return s


def update_project_context_from_candidate(
    project_id: int | None,
    candidate: dict[str, Any] | None,
    *,
    updated_by: str = "system",
) -> dict[str, Any]:
    """
    Safely update project_context from an extracted candidate.
    """
    if not project_id:
        return {
            "updated": False,
            "changed_fields": [],
            "skipped_reason": "missing_project_id",
            "before": None,
            "after": None,
        }

    if not get_project_by_id(project_id):
        return {
            "updated": False,
            "changed_fields": [],
            "skipped_reason": "project_not_found",
            "before": None,
            "after": None,
        }

    cand = candidate or {}
    if not bool(cand.get("has_project_update")):
        before = get_project_context_fields(project_id)
        return {
            "updated": False,
            "changed_fields": [],
            "skipped_reason": "no_project_update",
            "before": before,
            "after": before,
        }

    try:
        confidence = float(cand.get("confidence", 0.0))
    except Exception:
        confidence = 0.0

    if confidence < CONFIDENCE_THRESHOLD:
        before = get_project_context_fields(project_id)
        return {
            "updated": False,
            "changed_fields": [],
            "skipped_reason": f"low_confidence:{confidence:.2f}",
            "before": before,
            "after": before,
        }

    fields = cand.get("fields") if isinstance(cand.get("fields"), dict) else {}
    to_update: dict[str, str] = {}
    for k, v in fields.items():
        if k not in SUPPORTED_FIELDS:
            continue
        clean = _clean_value(v)
        if clean is None:
            continue
        to_update[k] = clean

    if not to_update:
        before = get_project_context_fields(project_id)
        return {
            "updated": False,
            "changed_fields": [],
            "skipped_reason": "no_valid_fields",
            "before": before,
            "after": before,
        }

    changed_fields, before, after = update_project_context_fields(
        project_id=project_id,
        fields_to_update=to_update,
        updated_by=updated_by,
    )

    if not changed_fields:
        return {
            "updated": False,
            "changed_fields": [],
            "skipped_reason": "no_changes",
            "before": before,
            "after": after,
        }

    return {
        "updated": True,
        "changed_fields": changed_fields,
        "skipped_reason": None,
        "before": before,
        "after": after,
    }

