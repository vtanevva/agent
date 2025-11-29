"""Tool: detect_calendar_requests — detect calendar event requests in user text.

Helper functions for parsing natural language calendar requests.
"""

import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

def detect_calendar_requests(text: str) -> List[Dict]:
    """
    Detect calendar event requests in user text.
    
    Supports various natural language patterns like:
    - "schedule a meeting tomorrow at 2pm"
    - "create event for team standup next Monday at 9am"
    - "remind me to call John tomorrow at 3pm"
    - "meeting tomorrow at 2pm"
    - "2pm tomorrow for team meeting"
    
    Parameters
    ----------
    text : str
        User's message
        
    Returns
    -------
    list of dict
        Detected calendar requests with description and time info
    """
    text_lower = text.lower()
    detected_events = []
    
    # Pattern 1: "schedule/book/create/add [event] [description] [time]"
    pattern1 = r'(?:schedule|book|set\s+up|create|add|save|plan)\s+(?:a\s+)?(?:meeting|appointment|event|call|session|reminder)?\s*(?:for|about|called)?\s*(.+?)\s+(?:tomorrow|today|next\s+\w+|on\s+\w+|\d{1,2}[/-]\d{1,2}|(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2})\s+(?:at\s+)?(\d{1,2}):?(\d{2})?\s*(am|pm)?'
    matches = re.finditer(pattern1, text_lower)
    for match in matches:
        description = match.group(1).strip()
        if description and len(description) > 2:
            detected_events.append({
                'description': description,
                'full_match': match.group(0),
                'start_pos': match.start(),
                'end_pos': match.end()
            })
    
    # Pattern 2: "[event] [time] [date]" - e.g., "meeting tomorrow at 2pm"
    pattern2 = r'(?:meeting|appointment|event|call|appointment|reminder)\s+(?:tomorrow|today|next\s+\w+|on\s+\w+|\d{1,2}[/-]\d{1,2})\s+(?:at\s+)?(\d{1,2}):?(\d{2})?\s*(am|pm)?(?:\s+(?:for|about)\s+(.+?))?'
    matches = re.finditer(pattern2, text_lower)
    for match in matches:
        description = match.group(4) if match.lastindex >= 4 and match.group(4) else "Meeting"
        if description and len(description) > 2:
            detected_events.append({
                'description': description.strip(),
                'full_match': match.group(0),
                'start_pos': match.start(),
                'end_pos': match.end()
            })
    
    # Pattern 3: "remind me to [action] [date] [time]"
    pattern3 = r'(?:remind\s+me\s+to|i\s+need\s+to|i\s+have\s+to|i\s+want\s+to)\s+(.+?)\s+(?:tomorrow|today|next\s+\w+|on\s+\w+)\s+(?:at\s+)?(\d{1,2}):?(\d{2})?\s*(am|pm)?'
    matches = re.finditer(pattern3, text_lower)
    for match in matches:
        description = match.group(1).strip()
        if description and len(description) > 2:
            detected_events.append({
                'description': description,
                'full_match': match.group(0),
                'start_pos': match.start(),
                'end_pos': match.end()
            })
    
    # Pattern 4: "[time] [date] [for/description]" - e.g., "2pm tomorrow for team meeting"
    pattern4 = r'(\d{1,2}):?(\d{2})?\s*(am|pm)?\s+(?:tomorrow|today|next\s+\w+|on\s+\w+)\s+(?:for|about)?\s*(.+?)(?:\s|$)'
    matches = re.finditer(pattern4, text_lower)
    for match in matches:
        description = match.group(4) if match.lastindex >= 4 and match.group(4) else "Event"
        if description and len(description) > 2:
            detected_events.append({
                'description': description.strip(),
                'full_match': match.group(0),
                'start_pos': match.start(),
                'end_pos': match.end()
            })
    
    # Pattern 5: "[date] [time] [description]" - e.g., "tomorrow at 2pm team standup"
    pattern5 = r'(?:tomorrow|today|next\s+\w+|on\s+\w+)\s+(?:at\s+)?(\d{1,2}):?(\d{2})?\s*(am|pm)?\s+(?:for|about)?\s*(.+?)(?:\s|$)'
    matches = re.finditer(pattern5, text_lower)
    for match in matches:
        description = match.group(4) if match.lastindex >= 4 and match.group(4) else "Event"
        if description and len(description) > 2:
            detected_events.append({
                'description': description.strip(),
                'full_match': match.group(0),
                'start_pos': match.start(),
                'end_pos': match.end()
            })
    
    # Remove duplicates (same description and similar position)
    unique_events = []
    seen = set()
    for event in detected_events:
        key = (event['description'].lower(), event['start_pos'])
        if key not in seen:
            seen.add(key)
            unique_events.append(event)
    
    return unique_events


def parse_datetime_from_text(text: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Parse datetime information from text using improved natural language parsing.
    
    Supports:
    - "tomorrow at 2pm"
    - "next Monday at 3pm"
    - "December 1st at 2pm"
    - "today at 2pm"
    - "2pm tomorrow"
    - "2pm - 4pm tomorrow"
    
    Parameters
    ----------
    text : str
        Text containing date/time information
        
    Returns
    -------
    tuple
        (start_time, end_time) or (None, None) if parsing fails
    """
    text_lower = text.lower().strip()
    now = datetime.now()
    
    # Step 1: Determine target date
    target_date = None
    
    # Check for relative dates
    if "tomorrow" in text_lower:
        target_date = now + timedelta(days=1)
    elif "today" in text_lower:
        target_date = now
    elif "next week" in text_lower:
        target_date = now + timedelta(weeks=1)
    elif "next month" in text_lower:
        target_date = now + relativedelta(months=1)
    elif "next" in text_lower:
        # Try to parse "next Monday", "next Friday", etc.
        days_of_week = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6
        }
        for day_name, day_num in days_of_week.items():
            if day_name in text_lower:
                days_ahead = (day_num - now.weekday()) % 7
                if days_ahead == 0:  # If today is that day, get next week's
                    days_ahead = 7
                target_date = now + timedelta(days=days_ahead)
                break
    
    # If no relative date found, try to parse absolute date
    if target_date is None:
        try:
            # Try using dateutil parser for dates like "December 1st", "Dec 1", etc.
            # Extract date-like patterns
            date_patterns = [
                r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?',
                r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\.?\s+\d{1,2}(?:st|nd|rd|th)?',
                r'\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?',  # MM/DD or MM/DD/YYYY
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    try:
                        parsed_date = date_parser.parse(match.group(0), default=now)
                        target_date = parsed_date.replace(hour=0, minute=0, second=0, microsecond=0)
                        break
                    except:
                        continue
        except:
            pass
    
    # Default to today if no date found
    if target_date is None:
        target_date = now
    
    # Step 2: Extract time information with better AM/PM handling
    # Pattern to match times with AM/PM indicators
    time_pattern = r'(\d{1,2}):?(\d{2})?\s*(am|pm)?'
    time_matches = re.finditer(time_pattern, text_lower)
    
    times = []
    for match in time_matches:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        am_pm = match.group(3)
        
        # Handle AM/PM
        if am_pm == "pm" and hour < 12:
            hour += 12
        elif am_pm == "am" and hour == 12:
            hour = 0
        
        # Get the context around this time to check for AM/PM
        start_pos = max(0, match.start() - 10)
        end_pos = min(len(text_lower), match.end() + 10)
        context = text_lower[start_pos:end_pos]
        
        # If no explicit AM/PM but hour > 12, assume 24-hour format
        # Otherwise, if hour <= 12 and no AM/PM, check context
        if not am_pm:
            if hour > 12:
                # Already 24-hour format
                pass
            elif hour <= 12:
                # Check if there's an AM/PM nearby that we might have missed
                if "pm" in context and "am" not in context:
                    hour += 12
                # Default to PM for afternoon hours (2pm-11pm range), AM for morning
                elif hour >= 2 and hour < 12:
                    # Could be either, but default to PM for common usage
                    hour += 12
        
        times.append((hour, minute))
    
    # Step 3: Build start and end times
    if len(times) >= 2:
        # Two times found - start and end
        start_hour, start_min = times[0]
        end_hour, end_min = times[1]
        
        start_time = target_date.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
        end_time = target_date.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
        
        # If end time is before start time, assume it's next day
        if end_time <= start_time:
            end_time += timedelta(days=1)
        
        return start_time, end_time
    elif len(times) == 1:
        # One time found - assume 1 hour duration
        hour, minute = times[0]
        
        start_time = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=1)
        
        return start_time, end_time
    
    # If no time found but we have a date, try to extract just the date and use default times
    if target_date != now:
        # Default to 9am - 10am if only date is specified
        start_time = target_date.replace(hour=9, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=1)
        return start_time, end_time
    
    return None, None

