"""
Orchestrator agent that routes requests to appropriate domain agents.

This is the main entry point for all chat requests. It:
1. Detects intent (calendar, email, general)
2. Checks auth requirements
3. Routes to appropriate domain agent
4. Returns the response

Architecture:
    /api/chat → Orchestrator → Domain Agents → Services → External APIs
"""

from typing import Tuple, Optional, Dict, Any, Literal, List

from app.agent_core.agent import run_agent
from app.tools.calendar_manager import (
    detect_calendar_requests,
    parse_datetime_from_text,
    create_calendar_event,
)
from app.utils.oauth_utils import require_google_auth
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)

IntentType = Literal["calendar", "email", "general"]

# Intent detection keywords
CALENDAR_KEYWORDS = ["calendar", "events", "schedule", "appointments", "meetings"]
EMAIL_KEYWORDS = ["emails", "email", "inbox", "reply to", "gmail"]


def detect_intent(user_message: str) -> IntentType:
    """
    Lightweight intent detection based on keyword lists and calendar parsing.
    
    - If we detect explicit calendar requests, treat as 'calendar'.
    - Else if email/inbox-related keywords are present, treat as 'email'.
    - Otherwise, default to 'general'.
    """
    text = (user_message or "").lower()
    
    try:
        calendar_requests = detect_calendar_requests(user_message) or []
    except Exception:
        calendar_requests = []
    
    if calendar_requests or any(k in text for k in CALENDAR_KEYWORDS):
        return "calendar"
    
    if any(k in text for k in EMAIL_KEYWORDS):
        return "email"
    
    return "general"


def _handle_calendar_chat(user_id: str, session_id: str, user_message: str) -> str:
    """
    Calendar-oriented handling.
    
    - Try to detect concrete calendar event requests.
    - If found, create events directly via Google Calendar.
    - Otherwise, delegate to the tool-calling agent for richer flows.
    """
    # First, try direct natural-language event creation
    try:
        calendar_requests = detect_calendar_requests(user_message) or []
    except Exception:
        calendar_requests = []
    
    if calendar_requests:
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
                        description=f"Event created from chat: {user_message}",
                    )
                except Exception as e:
                    result = {"success": False, "error": str(e)}
                
                if result.get("success"):
                    logger.info(f"Calendar event created for user {user_id}")
                    return (
                        f"✅ I've scheduled '{calendar_request['description']}' for "
                        f"{start_time.strftime('%B %d at %I:%M %p')}."
                        " You can view it in your calendar!"
                    )
                else:
                    logger.warning(f"Failed to create calendar event: {result.get('error')}")
                    return (
                        "❌ Sorry, I couldn't schedule the event. Please make sure "
                        "you're connected to Google Calendar."
                    )
    
    # Fallback to the tool-calling agent with calendar tools available
    logger.debug("Delegating to tool-calling agent for calendar")
    return run_agent(user_id=user_id, message=user_message, history=[])


class Orchestrator:
    """
    Main orchestrator for routing chat requests to domain agents.
    
    Routes based on intent:
    - "general" → AivisCoreAgent (productivity, chat, tasks)
    - "calendar" → CalendarAgent (via tool-calling agent)
    - "email" → GmailAgent (via tool-calling agent)
    - "contacts" → ContactsAgent (future)
    """
    
    def __init__(
        self,
        aivis_core_agent,
        llm_service,
        memory_service,
        gmail_agent=None,
        calendar_agent=None,
        contacts_agent=None,
    ):
        """
        Initialize the orchestrator with domain agents.
        
        Parameters
        ----------
        aivis_core_agent : AivisCoreAgent
            Agent for general productivity and chat
        llm_service : LLMService
            LLM service (for shared access)
        memory_service : MemoryService
            Memory service (for shared access)
        gmail_agent : GmailAgent, optional
            Agent for email operations (stub for now)
        calendar_agent : CalendarAgent, optional
            Agent for calendar operations (stub for now)
        contacts_agent : ContactsAgent, optional
            Agent for contact management (stub for now)
        """
        self.aivis_core = aivis_core_agent
        self.llm_service = llm_service
        self.memory_service = memory_service
        self.gmail_agent = gmail_agent
        self.calendar_agent = calendar_agent
        self.contacts_agent = contacts_agent
    
    def handle_chat(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        """
        Handle a chat message and route to appropriate agent.
        
        Parameters
        ----------
        user_id : str
            User identifier
        session_id : str
            Session identifier
        user_message : str
            User's message
        metadata : dict, optional
            Additional metadata (emotion, flags, etc.)
            
        Returns
        -------
        Tuple[str, str]
            (intent, reply) where intent is "calendar", "email", or "general"
        """
        # Detect intent
        intent = detect_intent(user_message)
        
        # Check auth requirements
        if intent in ("calendar", "email"):
            auth_response = require_google_auth(user_id)
            if auth_response:
                # Return error message if auth required
                return intent, "Please connect your Google account to use this feature."
        
        # Load session history from memory
        session_memory = self.memory_service.get_session_history(
            user_id=user_id,
            session_id=session_id,
            limit=20
        )
        
        # Route to appropriate agent based on intent
        if intent == "calendar":
            # Calendar intent - use calendar handling (legacy tool-calling)
            logger.info(f"Routing to calendar handler for user {user_id}")
            reply = _handle_calendar_chat(
                user_id=user_id,
                session_id=session_id,
                user_message=user_message,
            )
            return intent, reply
        
        elif intent == "email":
            # Email intent - use GmailAgent
            logger.info(f"Routing to GmailAgent for user {user_id}")
            if self.gmail_agent:
                reply = self.gmail_agent.handle_chat(
                    user_id=user_id,
                    message=user_message,
                    session_memory=session_memory,
                    metadata=metadata,
                )
            else:
                logger.warning("GmailAgent not available, using fallback")
                reply = run_agent(user_id=user_id, message=user_message, history=session_memory or [])
            return intent, reply
        
        else:
            # General intent - use AivisCoreAgent
            logger.info(f"Routing to AivisCoreAgent for user {user_id}")
            result = self.aivis_core.handle_chat(
                user_id=user_id,
                session_id=session_id,
                user_message=user_message,
                session_memory=session_memory,
                metadata=metadata,
            )
            reply = result.get("reply", "")
            return intent, reply


def build_orchestrator() -> Orchestrator:
    """
    Factory method to build orchestrator with all dependencies.
    
    This is the recommended way to create an orchestrator instance.
    It constructs all required services and agents with proper dependency injection.
    
    Returns
    -------
    Orchestrator
        Configured orchestrator instance
    """
    from app.services.llm_service import get_llm_service
    from app.services.memory_service import get_memory_service
    from app.services.nodes_service import NodesService
    from app.agents.aivis_core_agent import AivisCoreAgent
    from app.agents.gmail_agent import GmailAgent
    from app.agents.calendar_agent import CalendarAgent
    from app.agents.contacts_agent import ContactsAgent
    
    # Build services
    llm_service = get_llm_service()
    memory_service = get_memory_service()
    nodes_service = NodesService()  # Stub for now
    
    # Build agents
    aivis_core_agent = AivisCoreAgent(
        llm_service=llm_service,
        memory_service=memory_service,
        nodes_service=nodes_service,
    )
    
    gmail_agent = GmailAgent(
        llm_service=llm_service,
        memory_service=memory_service,
    )
    
    # Calendar and Contacts agents are stubs
    calendar_agent = CalendarAgent()
    contacts_agent = ContactsAgent()
    
    # Build orchestrator
    orchestrator = Orchestrator(
        aivis_core_agent=aivis_core_agent,
        llm_service=llm_service,
        memory_service=memory_service,
        gmail_agent=gmail_agent,
        calendar_agent=calendar_agent,
        contacts_agent=contacts_agent,
    )
    
    print("[INIT] ✅ Orchestrator built with AivisCoreAgent + GmailAgent + services")
    return orchestrator


# Singleton instance
_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    """
    Get the singleton orchestrator instance.
    
    Returns
    -------
    Orchestrator
        The singleton orchestrator (builds on first call)
    """
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_orchestrator()
    return _orchestrator

