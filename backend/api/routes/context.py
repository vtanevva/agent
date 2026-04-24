from __future__ import annotations

from flask import Blueprint, jsonify, request

from services.data_owner_key import data_owner_key_for_session
from storage.sqlite_db import (
    get_client_by_name,
    get_project_by_name,
    get_project_context,
    get_recent_messages_for_client,
    get_recent_messages_for_project,
)


context_bp = Blueprint("context", __name__)


@context_bp.get("/memory/context")
def memory_context():
    """
    Minimal context endpoint.

    This keeps the existing HTTP surface stable; it returns a lightweight
    snapshot from SQLite if client/project exist, otherwise empty context.
    """
    user_id = (request.args.get("user_id") or "").strip() or None
    thread_id = (request.args.get("thread_id") or "").strip() or None
    q = (request.args.get("q") or "").strip() or None

    client_name = (request.args.get("client_name") or "").strip() or None
    project_name = (request.args.get("project_name") or "").strip() or None

    owner_key = data_owner_key_for_session(app_user_id=user_id) if user_id else "__unscoped__"
    client = get_client_by_name(client_name, data_owner_key=owner_key) if client_name else None
    project = None
    project_context = None
    recent_messages: list[dict] = []

    if client and project_name:
        project = get_project_by_name(int(client["id"]), project_name)

    if project:
        project_context = get_project_context(int(project["id"]))
        recent_messages = get_recent_messages_for_project(int(project["id"]), limit=5)
    elif client:
        recent_messages = get_recent_messages_for_client(int(client["id"]), limit=5)

    context = {
        "user_id": user_id,
        "thread_id": thread_id,
        "q": q,
        "client": client,
        "project": project,
        "project_context": project_context,
        "recent_messages": recent_messages,
        # Keep keys that callers commonly expect.
        "profile_summary": "",
        "doc_chunks": [],
    }

    stats = {
        "facts_count": 0,
        "summaries_count": 0,
        "doc_chunks_count": 0,
        "recent_messages_count": len(recent_messages),
    }

    return jsonify({"success": True, "context": context, "stats": stats}), 200


__all__ = ["context_bp"]

