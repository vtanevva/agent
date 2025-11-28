"""
CalendarAgent - handles calendar-related requests.

This agent:
1. Detects calendar operations (list, create, update events)
2. Calls calendar tools directly
3. Returns formatted responses
"""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.tools.calendar_manager import (
    detect_calendar_requests,
    parse_datetime_from_text,
    create_calendar_event,
    list_calendar_events
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
                result = list_calendar_events(user_id=user_id)
                return json.dumps(result)
            except Exception as e:
                logger.error(f"Error listing calendar events: {e}", exc_info=True)
                return "Failed to retrieve calendar events. Please make sure you're connected to Google Calendar."
        
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
                        )
                        
                        if result.get("success"):
                            created_events.append({
                                "description": calendar_request["description"],
                                "start": start_time.strftime('%B %d at %I:%M %p')
                            })
                    except Exception as e:
                        logger.error(f"Error creating calendar event: {e}", exc_info=True)
            
            if created_events:
                # Format success message
                if len(created_events) == 1:
                    evt = created_events[0]
                    return f"✅ I've scheduled '{evt['description']}' for {evt['start']}. You can view it in your calendar!"
                else:
                    event_list = "\n".join([f"- {evt['description']} on {evt['start']}" for evt in created_events])
                    return f"✅ I've scheduled {len(created_events)} events:\n{event_list}"
            else:
                return "❌ Sorry, I couldn't schedule the event. Please make sure you're connected to Google Calendar."
        
        # No calendar events detected - provide helpful response
        return "I can help you with your calendar. Try asking me to:\n- Show my calendar\n- Schedule a meeting tomorrow at 2pm\n- Create an event for next Monday"

