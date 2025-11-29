"""Tool: list_calendar_events — show the user's calendar events.

Returns JSON with events from all connected calendars (Google + Outlook).
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from app.services.calendar import list_calendar_events as service_list_events
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def list_calendar_events(
    user_id: str,
    max_results: int = 50,
    days_ahead: int = 30,
    unified: bool = True,
) -> str:
    """
    List calendar events from all connected calendars.
    
    Parameters
    ----------
    user_id : str
        User identifier
    max_results : int, optional
        Maximum number of events to return (default: 50)
    days_ahead : int, optional
        Number of days to look ahead (default: 30)
    unified : bool, optional
        If True, fetch from all connected calendars (default: True)
        
    Returns
    -------
    str
        JSON string with events and metadata
    """
    try:
        time_min = datetime.utcnow().isoformat() + "Z"
        time_max = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"
        
        result = service_list_events(
            user_id=user_id,
            max_results=max_results,
            time_min=time_min,
            time_max=time_max,
            unified=unified,
        )
        
        # Return as JSON string (for consistency with other tools)
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error in list_calendar_events tool: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Failed to retrieve calendar events"
        })

