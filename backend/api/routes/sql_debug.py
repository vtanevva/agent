from flask import Blueprint, jsonify, request
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
    projects = list_projects_overview(tasks_per_project=tasks_per_project)
    return jsonify({"tasks_per_project": tasks_per_project, "projects": projects}), 200