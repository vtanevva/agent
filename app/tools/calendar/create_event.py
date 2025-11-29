"""Tool: create_calendar_event — create a new calendar event."""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from app.services.calendar import create_calendar_event as service_create_event
from app.tools.calendar.detect_requests import parse_datetime_from_text
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def create_calendar_event(
    user_id: str,
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    attendees: Optional[List[str]] = None,
    provider: Optional[str] = None,
    natural_language: Optional[str] = None,
) -> str:
    """
    Create a new calendar event.
    
    Parameters
    ----------
    user_id : str
        User identifier
    summary : str
        Event title
    start_time : str
        ISO format start time (e.g., "2024-12-01T14:00:00") OR natural language (e.g., "tomorrow at 2pm")
    end_time : str
        ISO format end time OR natural language (e.g., "tomorrow at 4pm")
    description : str, optional
        Event description
    location : str, optional
        Event location
    attendees : list of str, optional
        Attendee email addresses
    provider : str, optional
        Calendar provider ("google" or "outlook"). Uses default if None.
    natural_language : str, optional
        If provided, will parse start_time and end_time from this text
        
    Returns
    -------
    str
        JSON string with result
    """
    try:
        def _ensure_iso_format(dt_str: str) -> str:
            """Convert datetime string to ISO format with timezone."""
            # If already ISO format, return as-is
            if dt_str.startswith("202") or dt_str.startswith("20"):
                # Check if it has timezone info
                if "Z" in dt_str or "+" in dt_str or dt_str.count("-") >= 3:
                    return dt_str
                # Add Z if missing timezone
                if "T" in dt_str:
                    return dt_str + "Z"
                return dt_str
            
            # Try parsing as natural language
            parsed, _ = parse_datetime_from_text(dt_str)
            if parsed:
                # Ensure timezone-aware (use UTC)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.isoformat()
            
            return dt_str
        
        # If natural_language is provided, try to parse dates from it
        if natural_language:
            parsed_start, parsed_end = parse_datetime_from_text(natural_language)
            if parsed_start and parsed_end:
                # Ensure timezone-aware
                if parsed_start.tzinfo is None:
                    parsed_start = parsed_start.replace(tzinfo=timezone.utc)
                if parsed_end.tzinfo is None:
                    parsed_end = parsed_end.replace(tzinfo=timezone.utc)
                start_time = parsed_start.isoformat()
                end_time = parsed_end.isoformat()
            else:
                # Fallback: try parsing start_time and end_time as natural language
                start_time = _ensure_iso_format(start_time)
                end_time = _ensure_iso_format(end_time)
        else:
            # Parse start_time and end_time if they're natural language
            start_time = _ensure_iso_format(start_time)
            end_time = _ensure_iso_format(end_time)
        
        result = service_create_event(
            user_id=user_id,
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            attendees=attendees or [],
            provider=provider,
        )
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error in create_calendar_event tool: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Failed to create calendar event"
        })

