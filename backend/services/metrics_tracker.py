from __future__ import annotations

from typing import Any

from storage.sqlite_db import get_metrics_summary as _get_metrics_summary_db


def _safe_bool(value: Any) -> bool:
    return bool(value is True or value == 1 or str(value).strip().lower() in {"true", "1", "yes", "y"})


def build_metrics_event(*, source: str, result: dict) -> dict[str, Any]:
    r = result or {}
    cls = r.get("classification") or {}
    reply_policy = r.get("reply_policy") or {}
    imp = r.get("importance_result") or {}
    sched = r.get("scheduling_result") or {}

    status = str(r.get("status") or "").strip()
    duplicate_delivery = status == "duplicate"
    error_flag = status == "error" or bool(r.get("error"))

    reply_generated = bool(r.get("reply_text"))
    reply_mode = reply_policy.get("reply_mode")

    has_action = _safe_bool(cls.get("has_action"))

    follow_up_created = _safe_bool(r.get("follow_up_created"))

    task_created = status == "created" and bool(r.get("grafik_task_id"))
    task_linked = status == "linked_existing_task" and bool(r.get("linked_grafik_task_id"))

    project_context_update_result = r.get("project_context_update_result") or {}
    project_memory_updated = _safe_bool(project_context_update_result.get("updated"))

    importance_level = imp.get("importance_level")
    importance_score = imp.get("importance_score")

    has_schedule_signal = _safe_bool(sched.get("has_schedule_signal"))
    time_pressure_level = sched.get("time_pressure_level")

    return {
        "source": (source or "").strip().lower(),
        "status": status,
        "has_action": has_action,
        "reply_generated": reply_generated,
        "reply_mode": reply_mode,
        "follow_up_created": follow_up_created,
        "task_created": bool(task_created),
        "task_linked": bool(task_linked),
        "project_memory_updated": project_memory_updated,
        "importance_level": importance_level,
        "importance_score": importance_score,
        "has_schedule_signal": has_schedule_signal,
        "time_pressure_level": time_pressure_level,
        "duplicate_delivery": duplicate_delivery,
        "error": bool(error_flag),
    }


def _estimate_value(summary: dict[str, Any]) -> dict[str, Any]:
    totals = (summary or {}).get("totals") or {}

    task_created_or_linked = int(totals.get("tasks_created") or 0) + int(totals.get("tasks_linked") or 0)
    follow_up_created = int(totals.get("follow_ups_created") or 0)
    project_memory_updated = int(totals.get("project_memory_updates") or 0)

    estimated_saved_actions = task_created_or_linked + follow_up_created + project_memory_updated

    return {
        "estimated_saved_actions": int(estimated_saved_actions),
        "explanation": {
            "task_created_or_linked": int(task_created_or_linked),
            "follow_up_created": int(follow_up_created),
            "project_memory_updated": int(project_memory_updated),
        },
        "note": "Rough operational indicator (not time-saved minutes).",
    }


def get_metrics_summary() -> dict[str, Any]:
    summary = _get_metrics_summary_db()
    summary["value_estimate"] = _estimate_value(summary)
    return summary

