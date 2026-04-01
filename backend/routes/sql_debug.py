from flask import Blueprint, jsonify, request
from storage.sqlite_db import list_recent_tasks

sql_debug_bp = Blueprint("sql_debug", __name__)

@sql_debug_bp.get("/debug/sql/tasks")
def debug_sql_tasks():
    limit = int(request.args.get("limit", 20))
    limit = max(1, min(limit, 200))
    return jsonify({"limit": limit, "tasks": list_recent_tasks(limit)}), 200