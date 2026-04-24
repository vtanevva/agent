from flask import Blueprint, jsonify, request

from services.data_owner_key import data_owner_key_for_session
from storage.sqlite_db import list_projects_overview, list_recent_tasks

sql_debug_bp = Blueprint("sql_debug", __name__)

@sql_debug_bp.get("/debug/sql/tasks")
def debug_sql_tasks():
    limit = int(request.args.get("limit", 20))
    limit = max(1, min(limit, 200))
    return jsonify({"limit": limit, "tasks": list_recent_tasks(limit)}), 200


@sql_debug_bp.get("/debug/sql/projects-overview")
def debug_sql_projects_overview():
    raw = int(request.args.get("tasks_per_project", 30))
    tasks_per_project = max(1, min(raw, 100))
    user_id = (request.args.get("user_id") or "").strip()
    if not user_id:
        return (
            jsonify(
                {
                    "error": "user_id is required for per-user project data",
                    "tasks_per_project": tasks_per_project,
                    "projects": [],
                }
            ),
            400,
        )
    dk = data_owner_key_for_session(app_user_id=user_id)
    projects = list_projects_overview(
        tasks_per_project=tasks_per_project, data_owner_key=dk
    )
    return jsonify({"tasks_per_project": tasks_per_project, "projects": projects}), 200