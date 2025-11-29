"""Tool: detect_calendar_requests — detect calendar event requests in user text.

Helper functions for parsing natural language calendar requests.
"""

import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple


def detect_calendar_requests(text: str) -> List[Dict]:
    """
    Detect calendar event requests in user text.
    
    Parameters
    ----------
    text : str
        User's message
        
    Returns
    -------
    list of dict
        Detected calendar requests with description and time info
    """
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
    """
    Parse datetime information from text.
    
    Parameters
    ----------
    text : str
        Text containing date/time information
        
    Returns
    -------
    tuple
        (start_time, end_time) or (None, None) if parsing fails
    """
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

