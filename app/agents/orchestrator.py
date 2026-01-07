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
# NOTE: Removed ambiguous words like "meetings" to prevent false positives
# Now we use action-based patterns in detect_intent() instead
CALENDAR_KEYWORDS = ["calendar", "schedule"]  # Kept minimal, using action patterns instead

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
    Smart intent detection that distinguishes between:
    - Calendar actions (create/view events) vs questions about scheduling
    - Email actions (send/check) vs questions about contacts
    - General chat/advice vs domain-specific actions
    """
    from app.services.llm_service import get_llm_service
    
    text = (user_message or "").lower()
    
    # Quick heuristic: If asking "when/what/how/should/can I" → likely general advice
    advice_questions = ["when should", "what time", "how should", "can i schedule", "should i", "should we"]
    if any(q in text for q in advice_questions):
        logger.info(f"Detected advice question pattern, routing to general: {user_message[:50]}...")
        return "general"
    
    # Use LLM for nuanced detection (with caching)
    try:
        llm_service = get_llm_service()
        
        prompt = f"""Classify this user message into ONE category:

Message: "{user_message}"

Categories:
- **calendar**: User wants to CREATE, VIEW, or MANAGE calendar events. Examples: "Schedule a meeting for 3pm", "Show my calendar", "Add event for tomorrow"
- **email**: User wants to SEND, READ, or MANAGE emails. Examples: "Send email to John", "Check my inbox", "Reply to Sarah"
- **general**: User is asking for advice, chatting, or discussing topics. Examples: "When should we meet?", "I prefer morning meetings", "What's the weather?"

IMPORTANT:
- Questions like "When should I..." or "How should I..." are GENERAL (advice), NOT calendar actions
- Simply mentioning "meeting" or "schedule" doesn't mean calendar action
- Only choose calendar/email if there's a CLEAR ACTION to perform

Return ONLY one word: calendar, email, or general

Category:"""
        
        response = llm_service.chat_completion_text(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        
        intent = response.strip().lower()
        if intent in ["calendar", "email", "general"]:
            logger.info(f"LLM detected intent: {intent} for message: {user_message[:50]}...")
            return intent
            
    except Exception as e:
        logger.warning(f"LLM intent detection failed: {e}")
    
    # Fallback: keyword-based detection
    # Check for explicit calendar actions (not just questions)
    calendar_action_patterns = [
        "create event",
        "add event",
        "book a",
        "set up a meeting for",
        "add to calendar",
        "check my calendar",
        "show my calendar",
        "view calendar",
        "list events",
        "my events",
    ]
    
    is_calendar_action = any(pattern in text for pattern in calendar_action_patterns)
    
    # Also check the calendar detector (which looks for dates/times)
    try:
        calendar_requests = detect_calendar_requests(user_message) or []
    except Exception:
        calendar_requests = []
    
    # Only route to calendar if there's an action OR explicit calendar requests detected
    if calendar_requests or is_calendar_action:
        logger.info(f"Keyword-based calendar detection for: {user_message[:50]}...")
        return "calendar"
    
    if any(k in text for k in EMAIL_KEYWORDS):
        logger.info(f"Email keywords detected for: {user_message[:50]}...")
        return "email"
    
    logger.info(f"Defaulting to general for: {user_message[:50]}...")
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
    from app.agents.aivis_core_agent import AivisCoreAgent
    from app.agents.gmail_agent import GmailAgent
    from app.agents.calendar_agent import CalendarAgent
    from app.agents.contacts_agent import ContactsAgent
    
    # Build services
    llm_service = get_llm_service()
    memory_service = get_memory_service()
    
    # Build agents
    aivis_core_agent = AivisCoreAgent(
        llm_service=llm_service,
        memory_service=memory_service,
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

