"""
Unified calendar service that aggregates Google Calendar and Outlook Calendar.

Provides a single interface for calendar operations across multiple providers.
"""

import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.database import get_db
from app.db.collections import get_calendar_events_collection, get_tokens_collection
from app.utils.logging_utils import get_logger
from .google_provider import GoogleCalendarProvider
from .outlook_provider import OutlookCalendarProvider
from .base_provider import CalendarProvider

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────
# User Settings & Provider Management
# ──────────────────────────────────────────────────────────────────────


def check_user_calendar_connections(user_id: str) -> Dict[str, Any]:
    """
    Check which calendar providers the user has connected.
    
    Parameters
    ----------
    user_id : str
        User identifier
        
    Returns
    -------
    dict
        Connection status for each provider
    """
    try:
        tokens_col = get_tokens_collection()
        if tokens_col is None:
            return {
                "google_connected": False,
                "outlook_connected": False,
                "default_provider": "google",
            }
        
        # Check for Google credentials
        google_connected = False
        try:
            from app.utils.oauth_utils import load_google_credentials
            creds = load_google_credentials(user_id)
            # Check if credentials exist (even if expired, they can be refreshed)
            if creds is not None:
                google_connected = True
                logger.info(f"Google credentials found for user {user_id}, valid={creds.valid if hasattr(creds, 'valid') else 'unknown'}")
        except Exception as e:
            logger.warning(f"Could not load Google credentials for user {user_id}: {e}")
            google_connected = False
        
        # Check for Outlook token
        outlook_token = tokens_col.find_one({
            "user_id": user_id,
            "provider": "outlook"
        })
        outlook_connected = outlook_token is not None
        
        # Get user settings for default provider
        db = get_db()
        user_settings = None
        if db.is_connected:
            settings_col = db.db["user_settings"]
            user_settings = settings_col.find_one({"user_id": user_id})
        
        default_provider = "google"
        if user_settings:
            default_provider = user_settings.get("default_calendar_provider", "google")
        
        return {
            "google_connected": google_connected,
            "outlook_connected": outlook_connected,
            "default_provider": default_provider,
        }
        
    except Exception as e:
        logger.error(f"Error checking calendar connections: {e}", exc_info=True)
        return {
            "google_connected": False,
            "outlook_connected": False,
            "default_provider": "google",
        }


def set_default_calendar_provider(user_id: str, provider: str) -> Dict[str, Any]:
    """
    Set the default calendar provider for a user.
    
    Parameters
    ----------
    user_id : str
        User identifier
    provider : str
        Provider name ("google" or "outlook")
        
    Returns
    -------
    dict
        Result with success status
    """
    if provider not in ["google", "outlook"]:
        return {
            "success": False,
            "error": "Invalid provider. Must be 'google' or 'outlook'",
        }
    
    try:
        db = get_db()
        if not db.is_connected:
            return {"success": False, "error": "Database not available"}
        
        settings_col = db.db["user_settings"]
        settings_col.update_one(
            {"user_id": user_id},
            {"$set": {"default_calendar_provider": provider}},
            upsert=True,
        )
        
        return {
            "success": True,
            "default_provider": provider,
            "message": f"Default calendar provider set to {provider}",
        }
        
    except Exception as e:
        logger.error(f"Error setting default provider: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def _get_provider(user_id: str, provider: Optional[str] = None) -> Optional[CalendarProvider]:
    """
    Get a calendar provider instance.
    
    Parameters
    ----------
    user_id : str
        User identifier
    provider : str, optional
        Provider name ("google" or "outlook"). If None, uses default.
        
    Returns
    -------
    CalendarProvider or None
        Provider instance
    """
    if provider is None:
        connections = check_user_calendar_connections(user_id)
        provider = connections.get("default_provider", "google")
    
    if provider == "google":
        return GoogleCalendarProvider(user_id)
    elif provider == "outlook":
        return OutlookCalendarProvider(user_id)
    else:
        logger.error(f"Unknown provider: {provider}")
        return None


def _get_all_providers(user_id: str) -> List[CalendarProvider]:
    """
    Get all connected calendar providers for a user.
    
    Parameters
    ----------
    user_id : str
        User identifier
        
    Returns
    -------
    list of CalendarProvider
        List of connected provider instances
    """
    connections = check_user_calendar_connections(user_id)
    providers = []
    
    if connections.get("google_connected"):
        providers.append(GoogleCalendarProvider(user_id))
    
    if connections.get("outlook_connected"):
        providers.append(OutlookCalendarProvider(user_id))
    
    return providers


# ──────────────────────────────────────────────────────────────────────
# Unified Calendar Operations
# ──────────────────────────────────────────────────────────────────────


def create_calendar_event(
    user_id: str,
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    attendees: Optional[List[str]] = None,
    timezone: str = "UTC",
    reminders: Optional[Dict[str, Any]] = None,
    provider: Optional[str] = None,
    calendar_id: str = "primary",
) -> Dict[str, Any]:
    """
    Create a calendar event using the specified or default provider.
    
    Parameters
    ----------
    user_id : str
        User identifier
    summary : str
        Event title
    start_time : str
        ISO format start time
    end_time : str
        ISO format end time
    description : str, optional
        Event description
    location : str, optional
        Event location
    attendees : list of str, optional
        Attendee email addresses
    timezone : str, optional
        Timezone (default: UTC)
    reminders : dict, optional
        Reminder settings
    provider : str, optional
        Provider to use ("google" or "outlook"). Uses default if None.
    calendar_id : str, optional
        Calendar ID (default: "primary")
        
    Returns
    -------
    dict
        Result with success status and event details
    """
    try:
        cal_provider = _get_provider(user_id, provider)
        if not cal_provider:
            return {"success": False, "error": "No calendar provider available"}
        
        result = cal_provider.create_event(
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            attendees=attendees,
            timezone=timezone,
            reminders=reminders,
            calendar_id=calendar_id,
        )
        
        # Cache in database
        if result.get("success"):
            _cache_event_in_db(user_id, result)
        
        return result
        
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def list_calendar_events(
    user_id: str,
    max_results: int = 20,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    calendar_id: str = "primary",
    order_by: str = "startTime",
    provider: Optional[str] = None,
    unified: bool = False,
) -> Dict[str, Any]:
    """
    List calendar events from one or all providers.
    
    Parameters
    ----------
    user_id : str
        User identifier
    max_results : int, optional
        Maximum number of events (default: 20)
    time_min : str, optional
        Lower bound for event start time (ISO format)
    time_max : str, optional
        Upper bound for event end time (ISO format)
    calendar_id : str, optional
        Calendar ID (default: "primary")
    order_by : str, optional
        Sort order ("startTime" or "updated")
    provider : str, optional
        Specific provider to use. Ignored if unified=True.
    unified : bool, optional
        If True, fetch from all connected providers (default: False)
        
    Returns
    -------
    dict
        Result with events list
    """
    try:
        if unified:
            # Fetch from all providers
            all_providers = _get_all_providers(user_id)
            all_events = []
            
            for prov in all_providers:
                result = prov.list_events(
                    max_results=max_results,
                    time_min=time_min,
                    time_max=time_max,
                    calendar_id=calendar_id,
                    order_by=order_by,
                )
                
                if result.get("success"):
                    all_events.extend(result.get("events", []))
            
            # Sort all events by start time
            all_events.sort(key=lambda x: x.get("start", ""))
            
            # Limit to max_results
            all_events = all_events[:max_results]
            
            # Cache in background
            threading.Thread(
                target=_cache_events_background,
                args=(user_id, all_events),
                daemon=True,
            ).start()
            
            return {
                "success": True,
                "events": all_events,
                "count": len(all_events),
                "unified": True,
                "time_min": time_min or "",
                "time_max": time_max or "",
            }
        else:
            # Fetch from single provider
            cal_provider = _get_provider(user_id, provider)
            if not cal_provider:
                return {"success": False, "error": "No calendar provider available"}
            
            result = cal_provider.list_events(
                max_results=max_results,
                time_min=time_min,
                time_max=time_max,
                calendar_id=calendar_id,
                order_by=order_by,
            )
            
            if result.get("success"):
                threading.Thread(
                    target=_cache_events_background,
                    args=(user_id, result.get("events", [])),
                    daemon=True,
                ).start()
            
            return result
            
    except Exception as e:
        logger.error(f"Error listing calendar events: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def get_event_detail(
    user_id: str,
    event_id: str,
    calendar_id: str = "primary",
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """Get detailed information about a specific event"""
    try:
        cal_provider = _get_provider(user_id, provider)
        if not cal_provider:
            return {"success": False, "error": "No calendar provider available"}
        
        return cal_provider.get_event(event_id, calendar_id)
        
    except Exception as e:
        logger.error(f"Error getting event detail: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def update_calendar_event(
    user_id: str,
    event_id: str,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    calendar_id: str = "primary",
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """Update an existing calendar event"""
    try:
        cal_provider = _get_provider(user_id, provider)
        if not cal_provider:
            return {"success": False, "error": "No calendar provider available"}
        
        result = cal_provider.update_event(
            event_id=event_id,
            summary=summary,
            description=description,
            start_time=start_time,
            end_time=end_time,
            location=location,
            attendees=attendees,
            calendar_id=calendar_id,
        )
        
        # Update cache
        if result.get("success"):
            _update_event_in_db(user_id, event_id, result)
        
        return result
        
    except Exception as e:
        logger.error(f"Error updating calendar event: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def delete_calendar_event(
    user_id: str,
    event_id: str,
    calendar_id: str = "primary",
    send_updates: str = "all",
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """Delete a calendar event"""
    try:
        cal_provider = _get_provider(user_id, provider)
        if not cal_provider:
            return {"success": False, "error": "No calendar provider available"}
        
        result = cal_provider.delete_event(event_id, calendar_id, send_updates)
        
        # Remove from cache
        if result.get("success"):
            _delete_event_from_db(user_id, event_id)
        
        return result
        
    except Exception as e:
        logger.error(f"Error deleting calendar event: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def search_calendar_events(
    user_id: str,
    query: str,
    max_results: int = 20,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    calendar_id: str = "primary",
    provider: Optional[str] = None,
    unified: bool = False,
) -> Dict[str, Any]:
    """Search for calendar events"""
    try:
        if unified:
            # Search across all providers
            all_providers = _get_all_providers(user_id)
            all_events = []
            
            for prov in all_providers:
                result = prov.search_events(
                    query=query,
                    max_results=max_results,
                    time_min=time_min,
                    time_max=time_max,
                    calendar_id=calendar_id,
                )
                
                if result.get("success"):
                    all_events.extend(result.get("events", []))
            
            # Sort by start time
            all_events.sort(key=lambda x: x.get("start", ""))
            all_events = all_events[:max_results]
            
            return {
                "success": True,
                "events": all_events,
                "count": len(all_events),
                "query": query,
                "unified": True,
            }
        else:
            cal_provider = _get_provider(user_id, provider)
            if not cal_provider:
                return {"success": False, "error": "No calendar provider available"}
            
            return cal_provider.search_events(
                query=query,
                max_results=max_results,
                time_min=time_min,
                time_max=time_max,
                calendar_id=calendar_id,
            )
            
    except Exception as e:
        logger.error(f"Error searching calendar events: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def get_free_busy(
    user_id: str,
    time_min: str,
    time_max: str,
    calendars: Optional[List[str]] = None,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """Get free/busy information"""
    try:
        cal_provider = _get_provider(user_id, provider)
        if not cal_provider:
            return {"success": False, "error": "No calendar provider available"}
        
        return cal_provider.get_free_busy(time_min, time_max, calendars)
        
    except Exception as e:
        logger.error(f"Error getting free/busy info: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def list_calendars(
    user_id: str,
    provider: Optional[str] = None,
    unified: bool = False,
) -> Dict[str, Any]:
    """List all accessible calendars"""
    try:
        if unified:
            all_providers = _get_all_providers(user_id)
            all_calendars = []
            
            for prov in all_providers:
                result = prov.list_calendars()
                if result.get("success"):
                    all_calendars.extend(result.get("calendars", []))
            
            return {
                "success": True,
                "calendars": all_calendars,
                "count": len(all_calendars),
                "unified": True,
            }
        else:
            cal_provider = _get_provider(user_id, provider)
            if not cal_provider:
                return {"success": False, "error": "No calendar provider available"}
            
            return cal_provider.list_calendars()
            
    except Exception as e:
        logger.error(f"Error listing calendars: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def quick_add_event(
    user_id: str,
    text: str,
    calendar_id: str = "primary",
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Quick add an event using natural language.
    Note: Only supported by Google Calendar provider.
    """
    try:
        # Force Google provider for quick add (Outlook doesn't support this)
        if provider == "outlook":
            return {
                "success": False,
                "error": "Quick add is not supported by Outlook. Use create_calendar_event instead.",
            }
        
        cal_provider = GoogleCalendarProvider(user_id)
        result = cal_provider.quick_add_event(text, calendar_id)
        
        if result.get("success"):
            _cache_event_in_db(user_id, result)
        
        return result
        
    except Exception as e:
        logger.error(f"Error quick-adding event: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def get_upcoming_events(
    user_id: str,
    days_ahead: int = 7,
    max_results: int = 20,
    provider: Optional[str] = None,
    unified: bool = True,
) -> Dict[str, Any]:
    """Get upcoming events for the next N days"""
    time_min = datetime.utcnow().isoformat() + "Z"
    time_max = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"
    
    return list_calendar_events(
        user_id=user_id,
        max_results=max_results,
        time_min=time_min,
        time_max=time_max,
        provider=provider,
        unified=unified,
    )


def get_today_events(
    user_id: str,
    provider: Optional[str] = None,
    unified: bool = True,
) -> Dict[str, Any]:
    """Get today's calendar events"""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return list_calendar_events(
        user_id=user_id,
        time_min=today_start.isoformat() + "Z",
        time_max=today_end.isoformat() + "Z",
        provider=provider,
        unified=unified,
    )


def sync_calendar_events(
    user_id: str,
    days_ahead: int = 30,
    provider: Optional[str] = None,
    unified: bool = True,
) -> Dict[str, Any]:
    """Sync calendar events from provider(s) to local database"""
    try:
        result = get_upcoming_events(
            user_id,
            days_ahead=days_ahead,
            max_results=100,
            provider=provider,
            unified=unified,
        )
        
        if result.get("success"):
            return {
                "success": True,
                "synced_count": result.get("count", 0),
                "message": f"Synced {result.get('count', 0)} events",
            }
        else:
            return result
            
    except Exception as e:
        logger.error(f"Error syncing calendar events: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def get_all_calendars_unified(user_id: str) -> Dict[str, Any]:
    """Get all calendars from all connected providers"""
    return list_calendars(user_id, unified=True)


# ──────────────────────────────────────────────────────────────────────
# Database Caching Helpers
# ──────────────────────────────────────────────────────────────────────


def _cache_event_in_db(user_id: str, event_data: Dict[str, Any]) -> None:
    """Cache an event in the database"""
    try:
        calendar_col = get_calendar_events_collection()
        if calendar_col is None:
            return
        
        event_doc = {
            "user_id": user_id,
            "provider": event_data.get("provider", "google"),
            "provider_event_id": event_data.get("provider_event_id", event_data.get("event_id")),
            "event_id": event_data.get("event_id"),
            "summary": event_data.get("summary", ""),
            "description": event_data.get("description", ""),
            "location": event_data.get("location", ""),
            "start": event_data.get("start", ""),
            "end": event_data.get("end", ""),
            "html_link": event_data.get("html_link", ""),
            "status": event_data.get("status", "confirmed"),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        
        calendar_col.insert_one(event_doc)
        
    except Exception as e:
        logger.warning(f"Failed to cache event in database: {e}")


def _update_event_in_db(user_id: str, event_id: str, event_data: Dict[str, Any]) -> None:
    """Update a cached event in the database"""
    try:
        calendar_col = get_calendar_events_collection()
        if calendar_col is None:
            return
        
        calendar_col.update_one(
            {"user_id": user_id, "event_id": event_id},
            {
                "$set": {
                    "summary": event_data.get("summary", ""),
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        
    except Exception as e:
        logger.warning(f"Failed to update cached event: {e}")


def _delete_event_from_db(user_id: str, event_id: str) -> None:
    """Delete a cached event from the database"""
    try:
        calendar_col = get_calendar_events_collection()
        if calendar_col is None:
            return
        
        calendar_col.delete_one({"user_id": user_id, "event_id": event_id})
        
    except Exception as e:
        logger.warning(f"Failed to delete cached event: {e}")


def _cache_events_background(user_id: str, events: List[Dict[str, Any]]) -> None:
    """Cache events in database (runs in background thread)"""
    try:
        calendar_col = get_calendar_events_collection()
        if calendar_col is None:
            return
        
        for event in events:
            try:
                calendar_col.update_one(
                    {
                        "user_id": user_id,
                        "provider": event.get("provider", "google"),
                        "provider_event_id": event.get("provider_event_id", event.get("id")),
                    },
                    {
                        "$set": {
                            "user_id": user_id,
                            "provider": event.get("provider", "google"),
                            "provider_event_id": event.get("provider_event_id", event.get("id")),
                            "event_id": event.get("id"),
                            "summary": event.get("summary", ""),
                            "description": event.get("description", ""),
                            "location": event.get("location", ""),
                            "start": event.get("start", ""),
                            "end": event.get("end", ""),
                            "html_link": event.get("html_link", ""),
                            "status": event.get("status", "confirmed"),
                            "updated_at": datetime.utcnow(),
                        }
                    },
                    upsert=True,
                )
            except Exception as e:
                logger.warning(f"Failed to cache event {event.get('id')}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Background event caching error: {e}", exc_info=True)

