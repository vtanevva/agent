from typing import List, Dict, Any, Optional, Literal, Tuple

from app.agent_core.agent import run_agent
from app.tools.calendar_manager import (
    detect_calendar_requests,
    parse_datetime_from_text,
    create_calendar_event,
)

from .aivis_core_chat import chat_with_aivis_core


IntentType = Literal["calendar", "email", "general"]


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


def _handle_calendar_chat(
    user_id: str,
    session_id: str,
    user_message: str,
) -> str:
    """
    Calendar-oriented handling that mirrors the previous /api/chat behaviour:

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
                    return (
                        f"✅ I've scheduled '{calendar_request['description']}' for "
                        f"{start_time.strftime('%B %d at %I:%M %p')}."
                        " You can view it in your calendar!"
                    )
                else:
                    return (
                        "❌ Sorry, I couldn't schedule the event. Please make sure "
                        "you're connected to Google Calendar."
                    )

    # Fallback to the tool-calling agent with calendar tools available
    return run_agent(user_id=user_id, message=user_message, history=[])


def _handle_email_chat(
    user_id: str,
    session_id: str,
    user_message: str,
    session_memory: Optional[List[Dict[str, Any]]],
) -> str:
    """
    Email / inbox oriented handling.

    Uses the existing tool-calling agent with recent conversation history.
    """
    history = session_memory or []
    return run_agent(user_id=user_id, message=user_message, history=history)


def handle_chat(
    user_id: str,
    session_id: str,
    user_message: str,
    session_memory: Optional[List[Dict[str, Any]]],
    intent: Optional[IntentType] = None,
) -> str:
    """
    Main orchestrator entrypoint for chat.

    Parameters
    ----------
    user_id: str
        Application-level user identifier.
    session_id: str
        Logical session / conversation id.
    user_message: str
        Latest user utterance.
    session_memory: list | None
        Recent conversation history in OpenAI messages format.
    intent: Optional[str]
        Optional precomputed intent label ("calendar", "email", "general").
        If not provided, it will be inferred from the user_message.

    Returns
    -------
    str
        The assistant reply text.
    """
    intent = intent or detect_intent(user_message)

    if intent == "calendar":
        return _handle_calendar_chat(user_id=user_id, session_id=session_id, user_message=user_message)

    if intent == "email":
        return _handle_email_chat(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            session_memory=session_memory,
        )

    # Default: fall back to the general-purpose Aivis Core chat
    return chat_with_aivis_core(user_message=user_message, session_memory=session_memory)


