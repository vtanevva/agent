"""Tool: create_calendar_event — create a new calendar event."""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.services.calendar import create_calendar_event as service_create_event
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
        ISO format start time (e.g., "2024-12-01T14:00:00")
    end_time : str
        ISO format end time
    description : str, optional
        Event description
    location : str, optional
        Event location
    attendees : list of str, optional
        Attendee email addresses
    provider : str, optional
        Calendar provider ("google" or "outlook"). Uses default if None.
        
    Returns
    -------
    str
        JSON string with result
    """
    try:
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

