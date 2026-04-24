"""Link provider identities (Slack team, optional Slack user) to an Expo ``user_id`` for ingest stamping."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from storage.sqlite_db import upsert_profile_link_slack
from utils.logger import get_logger

log = get_logger("profile_link")

profile_link_bp = Blueprint("profile_link", __name__)


@profile_link_bp.post("/api/profile-link/slack")
def link_slack_team():
    """
    Associate a Slack workspace (``team_id`` / ``T…``) with an app profile.

    - If only one profile is linked to this team, all Slack events on that team stamp
      ``app_user_id`` to that profile.
    - If multiple profiles share a team, set ``slack_user_id`` to each member's Slack id
      (message ``user``) so events disambiguate.

    Body JSON::
        { "user_id": "deya", "slack_team_id": "T01234567", "slack_user_id": "U012…" (optional) }
    """
    body = request.get_json(silent=True) or {}
    user_id = (body.get("user_id") or "").strip().lower()
    team = (body.get("slack_team_id") or body.get("team_id") or "").strip()
    su = (body.get("slack_user_id") or body.get("slack_user") or "").strip() or None
    if not user_id or not team:
        return jsonify({"success": False, "error": "missing_user_id_or_slack_team_id"}), 400
    try:
        upsert_profile_link_slack(user_id=user_id, slack_team_id=team, slack_user_id=su)
    except Exception as e:
        log.exception("profile_link slack upsert failed: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": True, "user_id": user_id, "slack_team_id": team}), 200
