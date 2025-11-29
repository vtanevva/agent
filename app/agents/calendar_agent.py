"""
CalendarAgent - handles calendar-related requests.

This agent:
1. Detects calendar operations (list, create, update events)
2. Calls calendar services (supports Google & Outlook)
3. Returns formatted responses
"""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

# Use new unified calendar service
from app.services.calendar import (
    list_calendar_events,
    create_calendar_event,
    check_user_calendar_connections,
)

# Keep old tools for event parsing
from app.tools.calendar_manager import (
    detect_calendar_requests,
    parse_datetime_from_text,
)

from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


class CalendarAgent:
    """
    Agent for handling calendar operations.
    
    Directly calls calendar tools based on user intent.
    """
    
    def __init__(self, llm_service, memory_service):
        """
        Initialize CalendarAgent.
        
        Parameters
        ----------
        llm_service : LLMService
            LLM service for text generation
        memory_service : MemoryService
            Memory service for conversation history
        """
        self.llm_service = llm_service
        self.memory_service = memory_service
    
    def handle_chat(
        self,
        user_id: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Handle a calendar-related chat message.
        
        Parameters
        ----------
        user_id : str
            User identifier
        message : str
            User's message
        metadata : dict, optional
            Additional metadata
            
        Returns
        -------
        str
            Response (may be JSON for UI to parse)
        """
        lower = message.lower()
        
        # Check if user wants to list events
        if any(phrase in lower for phrase in [
            "show my calendar", "list events", "what's on my calendar",
            "my schedule", "upcoming events", "calendar events"
        ]):
            try:
                # Fetch events from ALL connected calendars (Google + Outlook)
                logger.info(f"Fetching calendar events for user_id: {user_id}")
                result = list_calendar_events(
                    user_id=user_id,
                    unified=True,  # ⭐ Auto-fetches from all connected calendars
                    max_results=50,
                    time_min=datetime.utcnow().isoformat() + "Z",
                    time_max=(datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"
                )
                
                if not result.get("success"):
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"Failed to fetch events: {error_msg}")
                    
                    # Check if it's the Calendar API not enabled error
                    if "Calendar API is not enabled" in error_msg:
                        user_message = (
                            "⚠️ Google Calendar API needs to be enabled in your Google Cloud project.\n\n"
                            "📋 Quick fix:\n"
                            "1. Go to: https://console.developers.google.com/apis/api/calendar-json.googleapis.com/overview\n"
                            "2. Click 'ENABLE'\n"
                            "3. Wait 1-2 minutes\n"
                            "4. Try again!\n\n"
                            "See ENABLE_GOOGLE_CALENDAR_API.md for detailed instructions."
                        )
                    else:
                        user_message = f"Failed to retrieve calendar events: {error_msg}"
                    
                    # Return JSON for UI to handle
                    return json.dumps({
                        "success": False,
                        "error": error_msg,
                        "message": user_message
                    })
                
                events = result.get("events", [])
                logger.info(f"Successfully fetched {len(events)} events")
                
                # Check which calendars are connected based on events received
                connections = check_user_calendar_connections(user_id)
                
                # Add provider info to result for UI
                result["connections"] = {
                    "google_connected": connections.get("google_connected", False),
                    "outlook_connected": connections.get("outlook_connected", False),
                    "default_provider": connections.get("default_provider", "google")
                }
                
                # Return JSON for the calendar UI to display
                return json.dumps(result)
                
            except Exception as e:
                logger.error(f"Error listing calendar events: {e}", exc_info=True)
                return json.dumps({
                    "success": False,
                    "error": str(e),
                    "message": "Failed to retrieve calendar events. Please try again later."
                })
        
        # Try to detect and create calendar events
        try:
            calendar_requests = detect_calendar_requests(message) or []
        except Exception as e:
            logger.error(f"Error detecting calendar requests: {e}", exc_info=True)
            calendar_requests = []
        
        if calendar_requests:
            # Create events
            created_events = []
            for calendar_request in calendar_requests:
                try:
                    start_time, end_time = parse_datetime_from_text(calendar_request["full_match"])
                except Exception:
                    start_time, end_time = None, None
                
                if start_time and end_time:
                    try:
                        result = create_calendar_event(
                            user_id=user_id,
                            summary=calendar_request["description"],
                            start_time=start_time.isoformat(),
                            end_time=end_time.isoformat(),
                            description=f"Event created from chat: {message}",
                            # Provider is auto-selected based on user's default
                        )
                        
                        if result.get("success"):
                            provider = result.get("provider", "google")
                            provider_icon = "🔵" if provider == "google" else "🟠"
                            created_events.append({
                                "description": calendar_request["description"],
                                "start": start_time.strftime('%B %d at %I:%M %p'),
                                "provider": provider,
                                "provider_icon": provider_icon
                            })
                    except Exception as e:
                        logger.error(f"Error creating calendar event: {e}", exc_info=True)
            
            if created_events:
                # Format success message with provider info
                if len(created_events) == 1:
                    evt = created_events[0]
                    return f"✅ {evt['provider_icon']} I've scheduled '{evt['description']}' for {evt['start']} on your {evt['provider'].title()} Calendar!"
                else:
                    event_list = "\n".join([
                        f"{evt['provider_icon']} {evt['description']} on {evt['start']} ({evt['provider'].title()})"
                        for evt in created_events
                    ])
                    return f"✅ I've scheduled {len(created_events)} events:\n{event_list}"
            else:
                return "❌ Sorry, I couldn't schedule the event. Please make sure you have at least one calendar connected."
        
        # No calendar events detected - provide helpful response
        return "I can help you with your calendar. Try asking me to:\n- Show my calendar\n- Schedule a meeting tomorrow at 2pm\n- Create an event for next Monday"

