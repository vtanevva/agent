"""Calendar listing for the Expo scheduler (same Google account as Gmail OAuth)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from flask import Blueprint, jsonify, request

from api.routes.google_oauth import default_oauth_frontend_return_url
from googleapiclient.errors import HttpError

from application.services.calendar_meeting_action import create_event_from_api_payload
from services.data_owner_key import data_owner_key_for_session
from services.google_calendar_client import list_primary_calendar_events
from storage.sqlite_db import list_calendar_events_in_range
from utils.logger import get_logger

log = get_logger("google_calendar")

google_calendar_bp = Blueprint("google_calendar", __name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_time_range() -> tuple[str, str]:
    now = _utc_now()
    t_min = (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_max = (now + timedelta(days=42)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return t_min, t_max


def _connect_url(username: str) -> str:
    base = (request.url_root or "").rstrip("/")
    user = (username or "me").strip().lower() or "me"
    if len(user) > 256:
        user = "me"
    q = urlencode({"expo_redirect": default_oauth_frontend_return_url()})
    return f"{base}/google/auth/{quote(user, safe='')}?{q}"


def _sqlite_row_to_event(row: dict) -> dict:
    rid = row.get("external_id")
    if not rid and row.get("id") is not None:
        rid = f"sqlite-cal-{row['id']}"
    return {
        "id": rid or "",
        "summary": row.get("title") or "(Untitled)",
        "start": row.get("start_at"),
        "end": row.get("end_at"),
        "location": "",
        "description": row.get("notes") or "",
        "html_link": "",
        "provider": row.get("source") or "sqlite",
    }


def _merge_calendar_sources(google_events: list[dict], sqlite_rows: list[dict]) -> list[dict]:
    """Prefer Google copies; skip SQLite rows that duplicate a Google event (by id or time+title)."""
    out: list[dict] = []
    seen: set[str] = set()
    google_ids = {str(e.get("id") or "") for e in google_events if e.get("id")}

    for ev in google_events:
        eid = str(ev.get("id") or "")
        key = f"g:{eid}" if eid else f"g:{ev.get('start')}:{ev.get('summary')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)

    for row in sqlite_rows:
        ui = _sqlite_row_to_event(row)
        ext = str(ui.get("id") or "")
        if ext and ext in google_ids:
            continue
        key = f"s:{ui.get('start')}:{ui.get('summary')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(ui)

    out.sort(key=lambda x: str(x.get("start") or ""))
    return out


@google_calendar_bp.post("/api/calendar/events")
def api_calendar_events():
    """
    Body: { user_id, time_min?, time_max?, max_results? }
    Returns: { success, events: [...] } or { success: false, action: connect_google, connect_url }
    """
    body = request.get_json(silent=True) or {}
    user_id = (body.get("user_id") or body.get("userId") or "").strip()
    max_results = int(body.get("max_results") or 250)
    max_results = max(1, min(max_results, 500))

    t_min, t_max = _default_time_range()
    if isinstance(body.get("time_min"), str) and body["time_min"].strip():
        t_min = body["time_min"].strip()
    if isinstance(body.get("time_max"), str) and body["time_max"].strip():
        t_max = body["time_max"].strip()

    if not user_id:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "user_id is required for per-user schedule data",
                    "events": [],
                }
            ),
            400,
        )

    data_owner = data_owner_key_for_session(app_user_id=user_id)
    g_user = (user_id or "").strip() or None

    sqlite_rows: list[dict] = []
    try:
        sqlite_rows = list_calendar_events_in_range(
            t_min, t_max, limit=500, data_owner_key=data_owner
        )
    except Exception as e:
        log.warning("[calendar] sqlite range read failed: %s", e)

    google_events: list[dict] = []
    connect_url = ""
    connect_action = ""
    try:
        google_events = list_primary_calendar_events(
            time_min=t_min,
            time_max=t_max,
            max_results=max_results,
            user_id=g_user,
        )
    except FileNotFoundError:
        connect_action = "connect_google"
        connect_url = _connect_url(user_id or "me")
    except HttpError as e:
        status = getattr(e.resp, "status", None) or 0
        if status in (401, 403):
            log.warning("[calendar] Google Calendar HTTP %s: %s", status, e)
            connect_action = "connect_google"
            connect_url = _connect_url(user_id or "me")
        else:
            log.exception("[calendar] Google Calendar API error")
            return jsonify({"success": False, "error": "calendar_api_error", "detail": str(e)}), 502
    except Exception as e:
        err = str(e).lower()
        if "invalid_grant" in err or "invalid_scope" in err or "invalid_google_credentials" in err:
            connect_action = "connect_google"
            connect_url = _connect_url(user_id or "me")
        else:
            log.exception("[calendar] unexpected error")
            return jsonify({"success": False, "error": "calendar_failed", "detail": str(e)}), 500

    merged = _merge_calendar_sources(google_events, sqlite_rows)
    payload: dict = {
        "success": True,
        "events": merged,
        "sources": {"google": len(google_events), "sqlite": len(sqlite_rows)},
    }
    if connect_action and connect_url:
        payload["action"] = connect_action
        payload["connect_url"] = connect_url
    return jsonify(payload), 200


@google_calendar_bp.post("/api/calendar/create")
def api_calendar_create():
    """
    Body: { user_id, summary, start_time, end_time, description?, timezone?, attendees?, add_google_meet? }
    Creates a Google Calendar event when OAuth is available; otherwise SQLite (weekly schedule merge).
    """
    body = request.get_json(silent=True) or {}
    user_id = (body.get("user_id") or body.get("userId") or "").strip() or "me"
    result = create_event_from_api_payload(body, user_id=user_id)
    if not result.get("success"):
        err = str(result.get("error") or "failed")
        if err == "connect_google":
            return (
                jsonify(
                    {
                        "success": False,
                        "action": "connect_google",
                        "connect_url": _connect_url(user_id),
                        "error": err,
                        "detail": result.get("detail"),
                    }
                ),
                401,
            )
        code = 400 if err in {"missing_start_or_end", "invalid_datetime"} else 502
        return jsonify({"success": False, "error": err, "detail": result.get("detail")}), code

    payload = {"success": True, **{k: v for k, v in result.items() if k != "success"}}
    return jsonify(payload), 200
