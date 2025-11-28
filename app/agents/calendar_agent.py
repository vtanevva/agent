"""
Calendar Agent - handles calendar-related tasks and scheduling.

This agent is responsible for:
- Creating calendar events
- Listing upcoming events
- Managing schedules
- Natural language date/time parsing
"""

from typing import Dict, Any, Optional, List
from datetime import datetime

from app.tools.calendar_manager import (
    detect_calendar_requests,
    parse_datetime_from_text,
    create_calendar_event,
    list_calendar_events,
)
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


class CalendarAgent:
    """
    Agent for calendar operations and scheduling.
    
    Handles both:
    - Direct operations (create event, list events)
    - Natural language scheduling (via NLP parsing)
    """
    
    def __init__(self, llm_service, memory_service):
        """
        Initialize the Calendar agent.
        
        Parameters
        ----------
        llm_service : LLMService
            Service for LLM operations
        memory_service : MemoryService
            Service for conversation memory
        """
        self.llm_service = llm_service
        self.memory_service = memory_service
        logger.info("CalendarAgent initialized")
    
    def handle_chat(
        self,
        user_id: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Handle calendar-related chat messages.
        
        Detects calendar requests in natural language and creates events.
        
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
            Response message
        """
        logger.info(f"CalendarAgent handling request for user {user_id}")
        
        # Try to detect calendar event requests
        try:
            calendar_requests = detect_calendar_requests(message) or []
        except Exception as e:
            logger.error(f"Error detecting calendar requests: {e}", exc_info=True)
            calendar_requests = []
        
        # If we found calendar requests, process them
        if calendar_requests:
            return self._handle_calendar_creation(user_id, message, calendar_requests)
        
        # Otherwise, check if they want to list events
        message_lower = message.lower()
        if any(keyword in message_lower for keyword in ["list", "show", "what", "upcoming", "schedule"]):
            return self._handle_list_events(user_id, message)
        
        # Fallback: use LLM to understand intent
        return self._handle_with_llm(user_id, message)
    
    def _handle_calendar_creation(
        self,
        user_id: str,
        message: str,
        calendar_requests: List[Dict[str, Any]],
    ) -> str:
        """Handle creating calendar events from natural language."""
        logger.debug(f"Processing {len(calendar_requests)} calendar request(s)")
        
        results = []
        
        for request in calendar_requests:
            try:
                # Parse the datetime
                start_time, end_time = parse_datetime_from_text(request["full_match"])
                
                if not start_time or not end_time:
                    results.append(f"❌ Couldn't parse date/time for: {request['description']}")
                    continue
                
                # Create the event
                result = create_calendar_event(
                    user_id=user_id,
                    summary=request["description"],
                    start_time=start_time.isoformat(),
                    end_time=end_time.isoformat(),
                    description=f"Event created from chat: {message}",
                )
                
                if result.get("success"):
                    formatted_time = start_time.strftime('%B %d at %I:%M %p')
                    results.append(
                        f"✅ I've scheduled '{request['description']}' for {formatted_time}. "
                        "You can view it in your calendar!"
                    )
                    logger.info(f"Calendar event created: {request['description']}")
                else:
                    error_msg = result.get("error", "Unknown error")
                    results.append(
                        f"❌ Sorry, I couldn't schedule '{request['description']}'. "
                        f"Error: {error_msg}"
                    )
                    logger.warning(f"Failed to create event: {error_msg}")
                    
            except Exception as e:
                logger.error(f"Error creating calendar event: {e}", exc_info=True)
                results.append(
                    f"❌ Sorry, I couldn't schedule '{request['description']}'. "
                    "Please make sure you're connected to Google Calendar."
                )
        
        if results:
            return "\n\n".join(results)
        
        return (
            "I detected you want to schedule something, but couldn't parse the date/time. "
            "Try something like: 'Schedule a meeting with John tomorrow at 3pm'"
        )
    
    def _handle_list_events(self, user_id: str, message: str) -> str:
        """Handle listing calendar events."""
        logger.debug(f"Listing calendar events for user {user_id}")
        
        try:
            result = list_calendar_events(user_id=user_id, max_results=10)
            
            if not result.get("success"):
                return (
                    "❌ Sorry, I couldn't retrieve your calendar events. "
                    "Please make sure you're connected to Google Calendar."
                )
            
            events = result.get("events", [])
            
            if not events:
                return "📅 You have no upcoming events in your calendar."
            
            # Format events nicely
            response_lines = [f"📅 You have {len(events)} upcoming event(s):\n"]
            
            for i, event in enumerate(events, 1):
                summary = event.get("summary", "Untitled Event")
                start = event.get("start", {})
                
                # Format the time
                start_str = start.get("dateTime", start.get("date", ""))
                if start_str:
                    try:
                        dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                        time_str = dt.strftime('%B %d at %I:%M %p')
                    except Exception:
                        time_str = start_str
                else:
                    time_str = "No time specified"
                
                response_lines.append(f"{i}. **{summary}** - {time_str}")
            
            return "\n".join(response_lines)
            
        except Exception as e:
            logger.error(f"Error listing calendar events: {e}", exc_info=True)
            return (
                "❌ Sorry, I encountered an error retrieving your calendar events. "
                "Please try again later."
            )
    
    def _handle_with_llm(self, user_id: str, message: str) -> str:
        """Use LLM to understand and respond to calendar requests."""
        logger.debug("Using LLM to handle calendar request")
        
        system_prompt = """You are a calendar assistant. Help the user with scheduling and calendar management.

If they want to create an event, ask for:
- Event title/description
- Date and time
- Duration (optional)

If they want to see events, offer to show their upcoming schedule.

Be helpful and concise."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]
        
        try:
            response = self.llm_service.chat_completion_text(
                messages=messages,
                temperature=0.5,
            )
            return response
        except Exception as e:
            logger.error(f"LLM error in calendar agent: {e}", exc_info=True)
            return (
                "I can help you with calendar management. "
                "Try asking me to 'schedule a meeting' or 'show my upcoming events'."
            )
    
    # ──────────────────────────────────────────────────────────────────
    # Direct Calendar Operations (wrapper methods)
    # ──────────────────────────────────────────────────────────────────
    
    def create_event(
        self,
        user_id: str,
        summary: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
        attendees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a calendar event directly.
        
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
            List of attendee emails
            
        Returns
        -------
        dict
            Result with success status
        """
        logger.info(f"Creating calendar event: {summary}")
        return create_calendar_event(
            user_id=user_id,
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            attendees=attendees,
        )
    
    def list_events(
        self,
        user_id: str,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        List upcoming calendar events.
        
        Parameters
        ----------
        user_id : str
            User identifier
        max_results : int
            Maximum number of events to return
            
        Returns
        -------
        dict
            Result with events list
        """
        logger.info(f"Listing calendar events for user {user_id}")
        return list_calendar_events(user_id=user_id, max_results=max_results)
