"""
Orchestrator agent that routes requests to appropriate domain agents.

This is the main entry point for all chat requests. It:
1. Routes based on explicit message_type parameter (preferred) OR detects intent from message content (fallback)
2. Checks auth requirements
3. Routes to appropriate domain agent
4. Returns the response

Architecture:
    /api/chat → Orchestrator → Domain Agents → Services → External APIs

Design:
    - The orchestrator should receive an explicit message_type parameter from the caller
    - This allows the frontend/API to control routing based on context (which page the user is on)
    - If message_type is not provided, it falls back to keyword-based detection for backward compatibility
"""

from typing import Tuple, Optional, Dict, Any, Literal, List

from app.tools.calendar import detect_calendar_requests
from app.utils.oauth_utils import require_google_auth
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)

IntentType = Literal["calendar", "email", "contacts", "general"]

# Intent detection keywords
CALENDAR_KEYWORDS = ["calendar", "events", "schedule", "appointments", "meetings"]
# NOTE: We also treat "send a message to <person>" as an email-compose request
# because this app currently supports messaging via Gmail compose, not SMS/DMs.
EMAIL_KEYWORDS = [
    "emails",
    "email",
    "inbox",
    "reply to",
    "gmail",
    "send a message to",
    "send message to",
]


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
        message_type: Optional[IntentType] = None,
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
        message_type : str, optional
            Explicit message type ("calendar", "email", "contacts", "general").
            If provided, this will be used directly for routing.
            If None, intent will be detected from message content (backward compatibility).
            
        Returns
        -------
        Tuple[str, str]
            (intent, reply) where intent is "calendar", "email", "contacts", or "general"
        """
        # Use explicit message_type if provided, otherwise detect intent
        if message_type:
            intent = message_type
            logger.info(f"Using explicit message_type: {intent} for user {user_id}")
        else:
            # Fallback to keyword-based detection for backward compatibility
            intent = detect_intent(user_message)
            logger.info(f"Detected intent from message: {intent} for user {user_id}")
        
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
        if intent == "contacts":
            # Contacts intent - use ContactsAgent
            logger.info(f"Routing to ContactsAgent for user {user_id}")
            if self.contacts_agent:
                reply = self.contacts_agent.handle_chat(
                    user_id=user_id,
                    message=user_message,
                    metadata=metadata,
                )
            else:
                logger.warning("ContactsAgent not available")
                reply = "Contacts features are not available right now. Please try again later."
            return intent, reply
        
        elif intent == "calendar":
            # Calendar intent - use CalendarAgent
            logger.info(f"Routing to CalendarAgent for user {user_id}")
            if self.calendar_agent:
                reply = self.calendar_agent.handle_chat(
                    user_id=user_id,
                    message=user_message,
                    metadata=metadata,
                )
            else:
                logger.warning("CalendarAgent not available")
                reply = "Calendar features are not available right now. Please try again later."
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
                logger.warning("GmailAgent not available")
                reply = "Gmail features are not available right now. Please try again later."
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
    
    # CalendarAgent now fully implemented
    from app.agents.calendar_agent import CalendarAgent
    calendar_agent = CalendarAgent(
        llm_service=llm_service,
        memory_service=memory_service,
    )
    
    # Contacts agent is still a stub
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
    
    # Avoid unicode output on Windows consoles that can't encode emoji
    print("[INIT] Orchestrator built with AivisCore + Calendar + Gmail agents")
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

