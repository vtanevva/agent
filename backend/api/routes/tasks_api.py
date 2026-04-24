from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, jsonify, request

from storage.sqlite_db import (
    complete_local_task,
    get_task_by_id,
    list_local_tasks,
    mark_thread_answered,
)
from utils.logger import get_logger


log = get_logger("tasks_api")
tasks_api_bp = Blueprint("tasks_api", __name__)


def _safe_json_loads(v: Any) -> dict:
    if not v:
        return {}
    if isinstance(v, dict):
        return v
    if not isinstance(v, str):
        return {}
    try:
        obj = json.loads(v)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _row_to_api(row: dict) -> dict:
    """
    Shape a ``tasks`` row for both HomePage and WeeklySchedule. The UI already
    understands ``due_datetime`` / ``priority`` fields (from the legacy pipeline
    shape), so we flatten useful bits out of ``classification_json`` for it.
    """
    cls = _safe_json_loads(row.get("classification_json"))
    due = (
        cls.get("due_datetime")
        or cls.get("due_datetime_iso")
        or cls.get("normalized_due", {}).get("iso")
        if isinstance(cls.get("normalized_due"), dict)
        else None
    )

    ctype = str(row.get("classification_type") or "").upper()
    if "URGENT" in ctype or "NOW" in ctype or "P0" in ctype:
        priority = "NOW"
    elif "SOON" in ctype or "P1" in ctype or "MEDIUM" in ctype:
        priority = "SOON"
    else:
        priority = "LATER"

    return {
        "id": row.get("id"),
        "source": row.get("source") or "",
        "source_id": row.get("source_id") or "",
        "thread_id": row.get("thread_id"),
        "workspace_id": row.get("workspace_id"),
        "client_id": row.get("client_id"),
        "project_id": row.get("project_id"),
        "client_name": row.get("client_name"),
        "project_name": row.get("project_name"),
        "title": row.get("title") or "",
        "description": row.get("description") or "",
        "classification_type": row.get("classification_type") or "",
        "classification": cls,
        "status": row.get("status") or "pending",
        "due_datetime": due,
        "priority": priority,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "completed_at": row.get("completed_at"),
        # Keep legacy alias so the scheduler/home code that still inspects
        # ``_id`` or ``grafik_task_id`` keeps working.
        "_id": str(row.get("id")),
        "grafik_task_id": row.get("grafik_task_id"),
    }


@tasks_api_bp.get("/api/tasks")
def list_tasks():
    """
    List local tasks for the Home / Week views. Not scoped per-user yet because
    the task table does not carry an app user id; filter by ``workspace_id``
    (Gmail mailbox email, Slack team id) if the caller provides it.
    """
    try:
        limit = int(request.args.get("limit") or "200")
    except Exception:
        limit = 200
    limit = max(1, min(limit, 500))
    include_completed = str(request.args.get("include_completed") or "").strip().lower() in (
        "1", "true", "yes",
    )
    workspace_filter = (request.args.get("workspace_id") or "").strip().lower()

    try:
        rows = list_local_tasks(limit=limit, include_completed=include_completed)
    except Exception as e:
        log.exception(f"[TASKS] list failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

    items = [_row_to_api(r) for r in rows]
    if workspace_filter:
        items = [
            it for it in items
            if not it.get("workspace_id") or it.get("workspace_id") == workspace_filter
        ]

    return jsonify({"success": True, "total": len(items), "tasks": items}), 200


@tasks_api_bp.post("/api/tasks/<int:task_id>/complete")
def complete_task(task_id: int):
    """
    Mark a task completed. For email/slack-sourced tasks we also record the
    thread as answered so the Home list hides the original inbound message.
    """
    row = get_task_by_id(task_id)
    if not row:
        return jsonify({"success": False, "error": "task_not_found"}), 404

    try:
        updated = complete_local_task(task_id)
    except Exception as e:
        log.exception(f"[TASKS] complete failed task_id={task_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

    src = str(row.get("source") or "").strip().lower()
    thread_id = str(row.get("thread_id") or "").strip()
    workspace_id = str(row.get("workspace_id") or "").strip().lower()

    if src in ("gmail", "slack") and thread_id and workspace_id:
        try:
            mark_thread_answered(
                source=src,
                workspace_id=workspace_id,
                thread_id=thread_id,
            )
        except Exception as e:
            log.warning(f"[TASKS] mark_thread_answered failed task_id={task_id}: {e}")

    return jsonify({"success": True, "task": _row_to_api(updated or row)}), 200


__all__ = ["tasks_api_bp"]
