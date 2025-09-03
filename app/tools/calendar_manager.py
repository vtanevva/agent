"""Calendar management tool for the mental health AI assistant"""

import os
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from app.agent_core.tool_registry import register, ToolSchema

# Use the same MongoDB connection as server.py
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

# Initialize MongoDB connection
client = None
tokens = None

if MONGO_URI:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        db = client.get_database()
        tokens = db["tokens"]
    except Exception as e:
        print(f"[WARNING] MongoDB connection failed: {e}")
        tokens = None
else:
    print("[WARNING] MONGO_URI not set.")

def _service(user_id: str):
    """Get Google Calendar service for user"""
    if tokens is None:
        raise RuntimeError("MongoDB is not available. Calendar features are disabled.")
    
    try:
        doc = tokens.find_one({"user_id": user_id}, {"google": 1})
        if not doc or "google" not in doc:
            raise FileNotFoundError(f"Google OAuth token for user '{user_id}' not found.")
        
        creds_info = doc["google"]
        creds = Credentials.from_authorized_user_info(creds_info)
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        raise RuntimeError(f"Failed to load Calendar service: {e}")

def create_calendar_event(
    user_id: str,
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    attendees: List[str] = None
) -> Dict:
    """Create a new calendar event in the app's internal calendar"""
    try:
        # Use the same MongoDB connection as server.py
        if tokens is None:
            return {
                "success": False,
                "error": "Database not available"
            }
        
        # Parse datetime strings
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        except ValueError:
            return {
                "success": False,
                "error": "Invalid datetime format"
            }
        
        # Create event document
        event_doc = {
            'user_id': user_id,
            'summary': summary,
            'description': description,
            'location': location,
            'start': start_dt,
            'end': end_dt,
            'attendees': attendees or [],
            'created_at': datetime.utcnow(),
            'html_link': f"app://calendar/event/{user_id}"
        }
        
        # Insert into database
        calendar_collection = db["calendar_events"]
        result = calendar_collection.insert_one(event_doc)
        
        return {
            "success": True,
            "event_id": str(result.inserted_id),
            "html_link": event_doc['html_link'],
            "summary": summary,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def list_calendar_events(
    user_id: str,
    max_results: int = 10,
    time_min: str = None,
    time_max: str = None
) -> Dict:
    """List upcoming calendar events from app's internal calendar"""
    try:
        # Use the same MongoDB connection as server.py
        if tokens is None:
            return {
                "success": False,
                "error": "Database not available"
            }
        
        # Get events from the app's calendar collection
        calendar_collection = db["calendar_events"]
        
        # Default to next 7 days if no time range specified
        if not time_min:
            time_min = datetime.utcnow()
        else:
            time_min = datetime.fromisoformat(time_min.replace('Z', '+00:00'))
            
        if not time_max:
            time_max = datetime.utcnow() + timedelta(days=7)
        else:
            time_max = datetime.fromisoformat(time_max.replace('Z', '+00:00'))
        
        # Query events for this user within the time range
        events_cursor = calendar_collection.find({
            "user_id": user_id,
            "start": {"$gte": time_min, "$lte": time_max}
        }).sort("start", 1).limit(max_results)
        
        events = list(events_cursor)
        
        formatted_events = []
        for event in events:
            formatted_events.append({
                'id': str(event.get('_id')),
                'summary': event.get('summary', 'No Title'),
                'description': event.get('description', ''),
                'location': event.get('location', ''),
                'start': event.get('start').isoformat() if event.get('start') else None,
                'end': event.get('end').isoformat() if event.get('end') else None,
                'html_link': event.get('html_link', '')
            })
        
        return {
            "success": True,
            "events": formatted_events,
            "count": len(formatted_events)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def detect_calendar_requests(text: str) -> List[Dict]:
    """Detect calendar event requests in user text"""
    patterns = [
        # Meeting/event patterns
        r'(?:schedule|book|set up|create|add|save)\s+(?:a\s+)?(?:meeting|appointment|event|call|session)\s+(?:for\s+)?(.+?)(?:\s+between\s+(\d{1,2}):?(\d{2})?\s*(?:am|pm)?\s*-\s*(\d{1,2}):?(\d{2})?\s*(?:am|pm)?)?',
        r'(?:meeting|appointment|event|call)\s+(?:tomorrow|today|next\s+\w+)\s+(?:at\s+)?(\d{1,2}):?(\d{2})?\s*(?:am|pm)?',
        r'(?:remind\s+me\s+to|i\s+need\s+to)\s+(.+?)\s+(?:tomorrow|today|next\s+\w+)\s+(?:at\s+)?(\d{1,2}):?(\d{2})?\s*(?:am|pm)?',
        # Time-based patterns
        r'(\d{1,2}):?(\d{2})?\s*(?:am|pm)?\s*-\s*(\d{1,2}):?(\d{2})?\s*(?:am|pm)?\s+(?:for\s+)?(.+?)(?:\s+tomorrow|today|next\s+\w+)?',
        # Date patterns
        r'(?:tomorrow|today|next\s+\w+)\s+(?:at\s+)?(\d{1,2}):?(\d{2})?\s*(?:am|pm)?\s+(?:for\s+)?(.+?)',
    ]
    
    detected_events = []
    
    for pattern in patterns:
        matches = re.finditer(pattern, text.lower())
        for match in matches:
            groups = match.groups()
            if len(groups) >= 2:
                # Extract time and description
                time_info = []
                description = ""
                
                for i, group in enumerate(groups):
                    if group and group.isdigit():
                        time_info.append(int(group))
                    elif group and not group.isdigit():
                        description = group.strip()
                
                if time_info and description:
                    detected_events.append({
                        'description': description,
                        'time_info': time_info,
                        'full_match': match.group(0),
                        'start_pos': match.start(),
                        'end_pos': match.end()
                    })
    
    return detected_events

def parse_datetime_from_text(text: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Parse datetime information from text"""
    # Simple parsing for common patterns
    now = datetime.now()
    
    # Check for "tomorrow"
    if "tomorrow" in text.lower():
        target_date = now + timedelta(days=1)
    elif "today" in text.lower():
        target_date = now
    else:
        target_date = now  # Default to today
    
    # Extract time information
    time_pattern = r'(\d{1,2}):?(\d{2})?\s*(?:am|pm)?'
    time_matches = re.findall(time_pattern, text.lower())
    
    if len(time_matches) >= 2:
        # Two times found - start and end
        start_hour, start_min = map(int, time_matches[0])
        end_hour, end_min = map(int, time_matches[1])
        
        # Handle AM/PM
        if "pm" in text.lower() and start_hour < 12:
            start_hour += 12
        if "pm" in text.lower() and end_hour < 12:
            end_hour += 12
        
        start_time = target_date.replace(hour=start_hour, minute=start_min or 0)
        end_time = target_date.replace(hour=end_hour, minute=end_min or 0)
        
        return start_time, end_time
    elif len(time_matches) == 1:
        # One time found - assume 1 hour duration
        hour, minute = map(int, time_matches[0])
        
        if "pm" in text.lower() and hour < 12:
            hour += 12
        
        start_time = target_date.replace(hour=hour, minute=minute or 0)
        end_time = start_time + timedelta(hours=1)
        
        return start_time, end_time
    
    return None, None

# Register the tools
register(
    create_calendar_event,
    ToolSchema(
        name="create_calendar_event",
        description="Create a new calendar event",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "summary": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "description": {"type": "string"},
                "location": {"type": "string"},
                "attendees": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["user_id", "summary", "start_time", "end_time"],
        },
    ),
)

register(
    list_calendar_events,
    ToolSchema(
        name="list_calendar_events",
        description="List upcoming calendar events",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "max_results": {"type": "integer"},
                "time_min": {"type": "string"},
                "time_max": {"type": "string"},
            },
            "required": ["user_id"],
        },
    ),
)
