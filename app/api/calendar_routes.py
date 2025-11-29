"""Calendar-related API routes."""

import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from flask import Blueprint, request, jsonify

from app.tools.calendar import (
    list_calendar_events,
    create_calendar_event,
)
from app.tools.calendar.detect_requests import detect_calendar_requests, parse_datetime_from_text
from app.utils.oauth_utils import require_google_auth
from app.utils.rate_limiter import enforce_rate_limit, get_rate_limit_key
from app.config import Config
from app.utils.logging_utils import get_logger
import uuid

logger = get_logger(__name__)


def _normalize_user_id(user_id_raw: str) -> str:
    """
    Normalize user_id - ensure it's never "anonymous" or empty.
    Generates unique ID for anonymous users to ensure proper rate limiting.
    """
    if not user_id_raw or user_id_raw.strip().lower() == "anonymous":
        # Generate unique session-based ID
        unique_id = f"anon-{uuid.uuid4().hex[:12]}"
        logger.warning(f"Anonymous user_id detected, generated: {unique_id}")
        return unique_id
    return user_id_raw.strip().lower()

calendar_bp = Blueprint('calendar', __name__, url_prefix='/api/calendar')


def _detect_calendar_intent(message: str) -> str:
    """
    Detect what the user wants to do with calendar.
    
    Returns: "list", "create", or "unknown"
    """
    lower = message.lower()
    
    # List events
    if any(phrase in lower for phrase in [
        "show my calendar", "show calendar", "list events", "what's on my calendar",
        "my schedule", "upcoming events", "calendar events",
        "display calendar", "view calendar", "see calendar",
        "what events", "what meetings", "show meetings",
        "calendar", "events", "schedule"  # Catch-all for calendar-related queries
    ]):
        return "list"
    
    # Create event
    if any(phrase in lower for phrase in [
        "schedule", "create", "add", "book", "set up", "plan",
        "meeting", "appointment", "event", "remind me to",
        "i need to", "i have to"
    ]):
        return "create"
    
    return "unknown"


def _extract_event_details(message: str, llm_service) -> Dict[str, Any]:
    """
    Extract event details from user message using LLM.
    
    Uses LLM to parse:
    - Event summary/title
    - Start time (natural language)
    - End time (optional)
    - Description, location, attendees (optional)
    
    Returns dict with extracted fields.
    """
    prompt = f"""Extract calendar event details from this user message:

"{message}"

Extract:
1. summary: Event title/summary (required)
2. start_time: Start time in natural language like "tomorrow at 2pm", "next Monday at 9am", "December 1st at 3pm" (required)
3. end_time: End time in natural language (optional, if not specified will default to 1 hour after start)
4. description: Event description (optional)
5. location: Event location (optional)
6. attendees: List of attendee names or emails (optional)

Return ONLY a JSON object with these fields. If a field is not mentioned, omit it or use null.
Example: {{"summary": "Team meeting", "start_time": "tomorrow at 2pm"}}"""

    try:
        response = llm_service.chat_completion_text(
            messages=[
                {"role": "system", "content": "You are a calendar event parser. Extract event details and return ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=200
        )
        
        # Try to parse JSON from response
        # LLM might wrap it in markdown or add text, so extract JSON
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            extracted = json.loads(json_match.group(0))
            return extracted
        else:
            # Try parsing whole response
            return json.loads(response)
    except Exception as e:
        logger.error(f"Error extracting event details: {e}", exc_info=True)
        return {}


@calendar_bp.route("/events", methods=["POST"])
def calendar_events():
    """Get calendar events for a user."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    max_results = data.get("max_results", 10)
    
    # Check rate limit (cost control for Calendar API)
    if Config.RATE_LIMIT_ENABLED:
        rate_limit_key = get_rate_limit_key(request, user_id)
        enforce_rate_limit(
            key=rate_limit_key,
            max_requests=10,
            window_seconds=60,
            endpoint_name="calendar_events"
        )
    
    # Check auth
    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response
    
    try:
        # New tools return JSON string, parse it
        result_json = list_calendar_events(
            user_id=user_id,
            max_results=max_results,
            days_ahead=30,  # Use days_ahead instead of time_min/time_max
            unified=True,  # Fetch from all connected calendars
        )
        result = json.loads(result_json)
        status = 200 if result.get("success", True) else 500
        return jsonify(result), status
    except Exception as e:
        logger.error(f"Error listing calendar events: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@calendar_bp.route("/create", methods=["POST"])
def create_calendar_event_endpoint():
    """Create a calendar event."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    summary = data.get("summary")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    description = data.get("description", "")
    location = data.get("location", "")
    attendees = data.get("attendees", [])
    provider = data.get("provider")  # "google" or "outlook"
    natural_language = data.get("natural_language")  # Original user message for parsing
    
    # Check rate limit (cost control for create operations)
    if Config.RATE_LIMIT_ENABLED:
        rate_limit_key = get_rate_limit_key(request, user_id)
        enforce_rate_limit(
            key=rate_limit_key,
            max_requests=10,
            window_seconds=60,
            endpoint_name="calendar_create"
        )
    
    # Check auth
    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response
    
    # If natural_language is provided but summary/start_time are missing, extract them
    if natural_language and (not summary or not start_time):
        try:
            from app.services.llm_service import get_llm_service
            llm_service = get_llm_service()
            event_details = _extract_event_details(natural_language, llm_service)
            
            # Use extracted details if original fields are missing
            if not summary and event_details.get("summary"):
                summary = event_details.get("summary")
            if not start_time and event_details.get("start_time"):
                start_time = event_details.get("start_time")
            if not end_time and event_details.get("end_time"):
                end_time = event_details.get("end_time")
            if not description and event_details.get("description"):
                description = event_details.get("description")
            if not location and event_details.get("location"):
                location = event_details.get("location")
            if not attendees and event_details.get("attendees"):
                attendees = event_details.get("attendees")
        except Exception as e:
            logger.error(f"Error extracting event details: {e}", exc_info=True)
    
    # Fallback: try detect_calendar_requests if still missing
    if (not summary or not start_time) and natural_language:
        try:
            calendar_requests = detect_calendar_requests(natural_language) or []
            if calendar_requests:
                calendar_request = calendar_requests[0]
                parsed_start, parsed_end = parse_datetime_from_text(calendar_request["full_match"])
                
                if parsed_start and parsed_end:
                    # Ensure timezone-aware
                    if parsed_start.tzinfo is None:
                        parsed_start = parsed_start.replace(tzinfo=timezone.utc)
                    if parsed_end.tzinfo is None:
                        parsed_end = parsed_end.replace(tzinfo=timezone.utc)
                    
                    if not summary:
                        summary = calendar_request["description"]
                    if not start_time:
                        start_time = parsed_start.isoformat()
                    if not end_time:
                        end_time = parsed_end.isoformat()
        except Exception as e:
            logger.error(f"Error parsing calendar request: {e}", exc_info=True)
    
    if not summary:
        return jsonify({"error": "Missing summary"}), 400
    if not start_time:
        return jsonify({"error": "Missing start_time"}), 400
    
    try:
        # New tools return JSON string, parse it
        result_json = create_calendar_event(
            user_id=user_id,
            summary=summary,
            start_time=start_time,
            end_time=end_time or start_time,  # Default to same as start if not provided
            description=description,
            location=location,
            attendees=attendees,
            provider=provider,
            natural_language=natural_language or data.get("message"),  # Pass original message if available
        )
        result = json.loads(result_json)
        status = 200 if result.get("success", True) else 500
        return jsonify(result), status
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

