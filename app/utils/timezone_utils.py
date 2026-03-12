from __future__ import annotations

from typing import Optional

from app.database import get_db
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def _is_valid_iana_tz(tz: str) -> bool:
    if not tz or not isinstance(tz, str):
        return False
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(tz)
        return True
    except Exception:
        return False


def get_user_timezone_setting(user_id: str) -> Optional[str]:
    """
    Read the user's preferred timezone from Mongo (if present).
    Returns an IANA timezone name (e.g. 'Europe/Sofia') or None.
    """
    db = get_db()
    if not (db.is_connected and db.db is not None):
        return None

    try:
        doc = db.db["user_settings"].find_one(
            {"user_id": user_id},
            {"timezone": 1, "time_zone": 1, "tz": 1},
        )
        for key in ("timezone", "time_zone", "tz"):
            val = (doc or {}).get(key)
            if isinstance(val, str):
                val = val.strip()
                if _is_valid_iana_tz(val):
                    return val
    except Exception:
        return None

    return None


def set_user_timezone_setting_if_missing(user_id: str, tz: str) -> None:
    """
    Persist timezone if user has no explicit timezone set yet.
    Never overwrites an existing value.
    """
    if not user_id:
        return
    tz = (tz or "").strip()
    if not _is_valid_iana_tz(tz):
        return

    existing = get_user_timezone_setting(user_id)
    if existing:
        return

    db = get_db()
    if not (db.is_connected and db.db is not None):
        return

    try:
        db.db["user_settings"].update_one(
            {"user_id": user_id},
            {"$set": {"timezone": tz, "user_id": user_id}},
            upsert=True,
        )
    except Exception as e:
        logger.debug(f"Failed to persist user timezone: {e}")


def get_effective_user_timezone(user_id: str) -> str:
    """
    Best-effort timezone for interpreting natural-language times like "tomorrow at 8:30".

    Priority:
    1) Explicit user_settings timezone
    2) Google Calendar primary calendar timezone (if connected)
    3) Fallback: UTC
    """
    tz = get_user_timezone_setting(user_id)
    if tz:
        return tz

    # Try to infer from Google Calendar if connected
    try:
        from app.services.calendar.google_provider import GoogleCalendarProvider
        from app.services.calendar.unified_service import check_user_calendar_connections

        connections = check_user_calendar_connections(user_id)
        if connections.get("google_connected"):
            prov = GoogleCalendarProvider(user_id)
            cal_tz = prov.get_calendar_timezone(calendar_id="primary")
            cal_tz = (cal_tz or "").strip()
            if _is_valid_iana_tz(cal_tz):
                set_user_timezone_setting_if_missing(user_id, cal_tz)
                return cal_tz
    except Exception:
        pass

    return "UTC"

