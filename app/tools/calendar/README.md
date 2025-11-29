# Calendar Tools

Calendar tools provide a clean interface for agents to interact with calendars.

## Architecture

```
Agent (calendar_agent.py)
    ↓
Tool (app/tools/calendar/*.py)
    ↓
Service (app/services/calendar/*.py)
    ↓
Provider (Google/Outlook API)
```

## Tools

### `list_calendar_events`
Lists events from all connected calendars (Google + Outlook).

**Usage:**
```python
from app.tools.calendar import list_calendar_events

result_json = list_calendar_events(
    user_id="user123",
    max_results=50,
    days_ahead=30,
    unified=True
)

result = json.loads(result_json)
```

### `create_calendar_event`
Creates a new calendar event.

**Usage:**
```python
from app.tools.calendar import create_calendar_event

result_json = create_calendar_event(
    user_id="user123",
    summary="Team Meeting",
    start_time="2024-12-01T14:00:00",
    end_time="2024-12-01T15:00:00",
    description="Quarterly planning",
    location="Conference Room A",
    provider="google"  # or "outlook", or None for default
)

result = json.loads(result_json)
```

### `detect_calendar_requests`
Detects calendar event requests in natural language text.

**Usage:**
```python
from app.tools.calendar import detect_calendar_requests

requests = detect_calendar_requests("Schedule a meeting tomorrow at 2pm")
# Returns list of detected requests
```

### `parse_datetime_from_text`
Parses datetime information from text.

**Usage:**
```python
from app.tools.calendar import parse_datetime_from_text

start, end = parse_datetime_from_text("tomorrow at 2pm")
# Returns (datetime, datetime) or (None, None)
```

## Why Tools?

Tools provide:
- ✅ **Consistent interface** - All agents call tools the same way
- ✅ **Separation of concerns** - Agents don't need to know about services
- ✅ **Easy testing** - Mock tools instead of services
- ✅ **JSON responses** - Standardized format for all tools

## Migration from Services

**Before (calling services directly):**
```python
from app.services.calendar import list_calendar_events

result = list_calendar_events(user_id, unified=True)
```

**After (calling tools):**
```python
from app.tools.calendar import list_calendar_events

result_json = list_calendar_events(user_id, unified=True)
result = json.loads(result_json)
```

## Notes

- Tools return JSON strings (for consistency with other tools like Gmail)
- Tools wrap services, which handle the actual API calls
- Services handle multi-provider logic (Google + Outlook)
- Providers handle provider-specific API interactions

