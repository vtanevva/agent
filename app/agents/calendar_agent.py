"""
CalendarAgent - handles calendar-related requests using LLM function calling.

This agent:
1. Uses LLM with function calling to understand user intent
2. LLM automatically calls calendar tools based on user request
3. Returns formatted responses

Uses OpenAI function calling pattern: LLM → Tools → Services
"""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone

# Use calendar tools (which wrap services)
from app.tools.calendar import (
    list_calendar_events,
    create_calendar_event,
)
from app.api.calendar_routes import _detect_calendar_intent, _extract_event_details
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


class CalendarAgent:
    """
    Agent for handling calendar operations.
    
    Uses routing to detect intent, then calls tools directly (like GmailAgent pattern).
    LLM is only used for parsing natural language dates when needed.
    """
    
    def __init__(self, llm_service, memory_service):
        """
        Initialize CalendarAgent.
        
        Parameters
        ----------
        llm_service : LLMService
            LLM service for text generation (used for parsing dates)
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
        Handle a calendar-related chat message using routing.
        
        Uses routing to detect intent, then calls tools directly.
        LLM is only used for parsing natural language dates when creating events.
        
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
        intent = _detect_calendar_intent(message)
        logger.info(f"CalendarAgent detected intent: {intent} for message: {message[:50]}")
        
        if intent == "list":
            # List calendar events
            try:
                logger.info(f"Listing calendar events for user_id: {user_id}")
                
                result_json = list_calendar_events(
                    user_id=user_id,
                    unified=True,  # Fetch from all connected calendars
                    max_results=50,
                    days_ahead=30
                )
                
                result = json.loads(result_json)
                
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
                    
                    return json.dumps({
                        "success": False,
                        "error": error_msg,
                        "message": user_message
                    })
                
                events = result.get("events", [])
                logger.info(f"Successfully fetched {len(events)} events")
                
                # Return JSON for the calendar UI to display
                return json.dumps(result)
                
            except Exception as e:
                logger.error(f"Error listing calendar events: {e}", exc_info=True)
                return json.dumps({
                    "success": False,
                    "error": str(e),
                    "message": "Failed to retrieve calendar events. Please try again later."
                })
        
        elif intent == "create":
            # Create calendar event
            try:
                logger.info(f"Creating calendar event for user_id: {user_id}")
                
                # Extract event details using LLM
                event_details = _extract_event_details(message, self.llm_service)
                
                if not event_details.get("summary") or not event_details.get("start_time"):
                    # Fallback: try to parse using detect_requests
                    from app.tools.calendar.detect_requests import detect_calendar_requests, parse_datetime_from_text
                    
                    calendar_requests = detect_calendar_requests(message) or []
                    if calendar_requests:
                        calendar_request = calendar_requests[0]
                        start_time, end_time = parse_datetime_from_text(calendar_request["full_match"])
                        
                        if start_time and end_time:
                            # Ensure timezone-aware
                            if start_time.tzinfo is None:
                                start_time = start_time.replace(tzinfo=timezone.utc)
                            if end_time.tzinfo is None:
                                end_time = end_time.replace(tzinfo=timezone.utc)
                            
                            event_details = {
                                "summary": calendar_request["description"],
                                "start_time": start_time.isoformat(),
                                "end_time": end_time.isoformat(),
                                "natural_language": message
                            }
                        else:
                            return "❌ I couldn't parse the date/time from your message. Try: 'tomorrow at 2pm' or 'next Monday at 9am'"
                    else:
                        return "❌ I couldn't understand what event you want to create. Please specify the event title and time."
                
                # Call create_calendar_event tool
                result_json = create_calendar_event(
                    user_id=user_id,
                    summary=event_details.get("summary", ""),
                    start_time=event_details.get("start_time", ""),
                    end_time=event_details.get("end_time"),
                    description=event_details.get("description", ""),
                    location=event_details.get("location", ""),
                    attendees=event_details.get("attendees", []),
                    provider=event_details.get("provider"),
                    natural_language=message,  # Always pass original message
                )
                
                result = json.loads(result_json)
                
                if result.get("success"):
                    provider = result.get("provider", "google")
                    provider_icon = "🔵" if provider == "google" else "🟠"
                    
                    # Parse start_time for display
                    try:
                        from datetime import datetime
                        if isinstance(event_details.get("start_time"), str):
                            if "T" in event_details["start_time"]:
                                start_dt = datetime.fromisoformat(event_details["start_time"].replace("Z", "+00:00"))
                            else:
                                # Natural language, try parsing
                                from app.tools.calendar.detect_requests import parse_datetime_from_text
                                start_dt, _ = parse_datetime_from_text(event_details["start_time"])
                                if not start_dt:
                                    start_dt = datetime.now()
                            display_time = start_dt.strftime('%B %d at %I:%M %p')
                        else:
                            display_time = "the scheduled time"
                    except:
                        display_time = "the scheduled time"
                    
                    return f"✅ {provider_icon} I've scheduled '{event_details.get('summary')}' for {display_time} on your {provider.title()} Calendar!"
                else:
                    error_msg = result.get("error", "Unknown error")
                    return f"❌ Failed to create calendar event: {error_msg}"
                    
            except Exception as e:
                logger.error(f"Error creating calendar event: {e}", exc_info=True)
                return f"❌ I encountered an error creating the event: {str(e)}. Please try again."
        
        else:
            # Unknown intent
            return "I can help you with your calendar. Try asking me to:\n- Show my calendar\n- Schedule a meeting tomorrow at 2pm\n- Create an event for next Monday"

