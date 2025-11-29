"""
Multi-provider calendar service package.

Supports Google Calendar and Outlook Calendar with a unified interface.
"""

from .unified_service import (
    create_calendar_event,
    list_calendar_events,
    get_event_detail,
    update_calendar_event,
    delete_calendar_event,
    search_calendar_events,
    get_free_busy,
    list_calendars,
    quick_add_event,
    get_upcoming_events,
    get_today_events,
    sync_calendar_events,
    get_all_calendars_unified,
    check_user_calendar_connections,
    set_default_calendar_provider,
)

__all__ = [
    "create_calendar_event",
    "list_calendar_events",
    "get_event_detail",
    "update_calendar_event",
    "delete_calendar_event",
    "search_calendar_events",
    "get_free_busy",
    "list_calendars",
    "quick_add_event",
    "get_upcoming_events",
    "get_today_events",
    "sync_calendar_events",
    "get_all_calendars_unified",
    "check_user_calendar_connections",
    "set_default_calendar_provider",
]

