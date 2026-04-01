from __future__ import annotations

import json
from typing import Any

from storage.sqlite_db import (
    get_open_follow_ups_for_client,
    get_open_follow_ups_for_project,
    get_project_context,
    get_recent_messages_for_client,
    get_recent_messages_for_project,
    get_recent_tasks_for_client,
    get_recent_tasks_for_project,
)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def _text_preview(text: Any, limit: int = 160) -> str:
    s = (str(text) if text is not None else "").strip()
    if not s:
        return ""
    return s[:limit] + ("..." if len(s) > limit else "")


def _extract_classification_summary(classification_json: Any) -> str | None:
    if not classification_json:
        return None
    try:
        obj = json.loads(classification_json) if isinstance(classification_json, str) else classification_json
        if isinstance(obj, dict):
            summary = (obj.get("summary") or "").strip()
            return summary or None
    except Exception:
        return None
    return None


def _normalize_recent_message(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": row.get("source"),
        "source_id": row.get("source_id"),
        "text_preview": _text_preview(row.get("text")),
        "classification_type": row.get("classification_type"),
        "ts": row.get("ts"),
        "created_at": row.get("created_at"),
        "summary": _extract_classification_summary(row.get("classification_json")),
    }


def _normalize_recent_task(row: dict[str, Any]) -> dict[str, Any]:
    task_id = row.get("grafik_task_id")
    return {
        "grafik_task_id": task_id,
        "title": row.get("title"),
        "source": row.get("source"),
        "source_id": row.get("source_id"),
        "created_at": row.get("created_at"),
        "summary": _extract_classification_summary(row.get("classification_json")),
    }


def _normalize_open_follow_up(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "type": row.get("type"),
        "status": row.get("status"),
        "due_at": row.get("due_at"),
        "source": row.get("source"),
        "source_id": row.get("source_id"),
        "created_at": row.get("created_at"),
    }


def _empty_context(*, client_id: int | None, project_id: int | None) -> dict[str, Any]:
    return {
        "client_id": client_id,
        "project_id": project_id,
        "project_context": None,
        "recent_messages": [],
        "recent_tasks": [],
        "open_follow_ups": [],
        "summary": {
            "has_project_context": False,
            "has_open_follow_ups": False,
            "recent_message_count": 0,
            "recent_task_count": 0,
            "open_follow_up_count": 0,
        },
    }


def build_continuity_context(
    *,
    client_id: int | None,
    project_id: int | None,
    limit_messages: int = 5,
    limit_tasks: int = 5,
    limit_follow_ups: int = 5,
) -> dict[str, Any]:
    """
    Build lightweight continuity context for a given (client, project) scope.

    Rules:
    - Prefer project-scoped retrieval when project_id exists
    - Else fall back to client-scoped retrieval when client_id exists
    - Else return a safe empty structure (never None)
    """
    cid = _safe_int(client_id)
    pid = _safe_int(project_id)

    if not (pid or cid):
        return _empty_context(client_id=None, project_id=None)

    if pid:
        project_context = get_project_context(pid)
        recent_messages_raw = get_recent_messages_for_project(pid, limit=limit_messages)
        recent_tasks_raw = get_recent_tasks_for_project(pid, limit=limit_tasks)
        open_follow_ups_raw = get_open_follow_ups_for_project(pid, limit=limit_follow_ups)
        # Prefer client_id from project_context when available
        if project_context and project_context.get("client_id"):
            cid = _safe_int(project_context.get("client_id"))
    else:
        project_context = None
        recent_messages_raw = get_recent_messages_for_client(cid, limit=limit_messages) if cid else []
        recent_tasks_raw = get_recent_tasks_for_client(cid, limit=limit_tasks) if cid else []
        open_follow_ups_raw = get_open_follow_ups_for_client(cid, limit=limit_follow_ups) if cid else []

    recent_messages = [_normalize_recent_message(r) for r in (recent_messages_raw or [])]
    recent_tasks = [_normalize_recent_task(r) for r in (recent_tasks_raw or [])]
    open_follow_ups = [_normalize_open_follow_up(r) for r in (open_follow_ups_raw or [])]

    summary = {
        "has_project_context": bool(project_context),
        "has_open_follow_ups": bool(open_follow_ups),
        "recent_message_count": len(recent_messages),
        "recent_task_count": len(recent_tasks),
        "open_follow_up_count": len(open_follow_ups),
    }

    return {
        "client_id": cid,
        "project_id": pid,
        "project_context": project_context,
        "recent_messages": recent_messages,
        "recent_tasks": recent_tasks,
        "open_follow_ups": open_follow_ups,
        "summary": summary,
    }

