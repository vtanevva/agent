"""Google Calendar API using the same OAuth token as Gmail (``token.json``)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from services.gmail_auth import load_google_credentials, save_google_credentials


def _normalize_google_event(ev: dict[str, Any]) -> dict[str, Any]:
    s = ev.get("start") or {}
    e = ev.get("end") or {}
    if "dateTime" in s:
        start_iso = s["dateTime"]
        end_iso = e.get("dateTime") or start_iso
    else:
        sd = s.get("date") or ""
        ed = e.get("date") or sd
        start_iso = f"{sd}T00:00:00"
        end_iso = f"{ed}T00:00:00"
    return {
        "id": ev.get("id") or "",
        "summary": ev.get("summary") or "(Untitled event)",
        "start": start_iso,
        "end": end_iso,
        "location": ev.get("location") or "",
        "description": ev.get("description") or "",
        "html_link": ev.get("htmlLink") or "",
        "provider": "google_calendar",
    }


def list_primary_calendar_events(
    *,
    time_min: str,
    time_max: str,
    max_results: int = 250,
) -> list[dict[str, Any]]:
    """
    List timed and all-day events from the user's primary calendar in [time_min, time_max).

    :raises FileNotFoundError: no stored OAuth token
    :raises HttpError: Google API error (caller may inspect .resp.status)
    """
    creds = load_google_credentials(None)
    if not creds:
        raise FileNotFoundError("no_google_credentials")

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_google_credentials(None, creds)
    if not creds.valid:
        raise RuntimeError("invalid_google_credentials")

    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    items = events_result.get("items") or []
    return [_normalize_google_event(ev) for ev in items]


def create_primary_timed_event(
    *,
    summary: str,
    start: datetime,
    end: datetime,
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
    time_zone: str = "UTC",
    add_google_meet: bool = True,
    send_updates: str | None = None,
) -> dict[str, Any]:
    """
    Create an event on the user's primary calendar.

    :param send_updates: ``all`` | ``externalOnly`` | ``none``; default ``all`` if attendees else ``none``.
    :raises FileNotFoundError: no stored OAuth token
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")

    creds = load_google_credentials(None)
    if not creds:
        raise FileNotFoundError("no_google_credentials")

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_google_credentials(None, creds)
    if not creds.valid:
        raise RuntimeError("invalid_google_credentials")

    tz = (time_zone or "UTC").strip() or "UTC"

    def _fmt_z(dt: datetime) -> str:
        u = dt.astimezone(timezone.utc).replace(microsecond=0)
        return u.strftime("%Y-%m-%dT%H:%M:%SZ")

    # dateTime fields are civil clock in ``timeZone`` (IANA), e.g. America/New_York.
    body: dict[str, Any] = {
        "summary": summary or "Meeting",
        "description": description or "",
        "location": location or "",
        "start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz},
        "end": {"dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz},
    }
    emails = [e.strip() for e in (attendees or []) if isinstance(e, str) and e.strip()]
    if emails:
        body["attendees"] = [{"email": e} for e in emails]

    if add_google_meet:
        body["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }

    if send_updates is None:
        send_updates = "all" if emails else "none"

    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    insert_kw: dict[str, Any] = {
        "calendarId": "primary",
        "body": body,
        "sendUpdates": send_updates,
    }
    if add_google_meet:
        insert_kw["conferenceDataVersion"] = 1

    created = service.events().insert(**insert_kw).execute()
    return {
        "id": created.get("id") or "",
        "summary": created.get("summary") or summary,
        "html_link": created.get("htmlLink") or "",
        "start": (created.get("start") or {}).get("dateTime") or _fmt_z(start),
        "end": (created.get("end") or {}).get("dateTime") or _fmt_z(end),
        "hangout_link": created.get("hangoutLink") or "",
        "provider": "google_calendar",
    }
