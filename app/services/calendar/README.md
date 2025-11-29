# Multi-Provider Calendar Service

A unified calendar service that supports both **Google Calendar** and **Outlook Calendar** with a single, consistent interface.

## Architecture

```
app/services/calendar/
├── __init__.py              # Public API exports
├── base_provider.py         # Abstract base class for all providers
├── google_provider.py       # Google Calendar implementation
├── outlook_provider.py      # Outlook/Microsoft Graph implementation
└── unified_service.py       # Aggregates all providers
```

## Features

✅ **Multi-Provider Support**
- Google Calendar (via Google Calendar API v3)
- Outlook Calendar (via Microsoft Graph API)
- Extensible design for adding more providers

✅ **Unified Interface**
- Single API for all calendar operations
- View events from all calendars in one place
- Provider-agnostic event format

✅ **Smart Features**
- Automatic caching in MongoDB
- Background sync for performance
- Cross-provider conflict detection
- User-configurable default provider

## Usage

### Basic Setup

```python
from app.services.calendar import (
    create_calendar_event,
    list_calendar_events,
    check_user_calendar_connections,
)

# Check which calendars the user has connected
connections = check_user_calendar_connections(user_id)
# Returns: {'google_connected': True, 'outlook_connected': False, 'default_provider': 'google'}
```

### Creating Events

```python
# Create event using default provider
result = create_calendar_event(
    user_id="user123",
    summary="Team Meeting",
    start_time="2024-12-01T14:00:00",
    end_time="2024-12-01T15:00:00",
    description="Quarterly planning session",
    location="Conference Room A",
    attendees=["colleague@example.com"],
)

# Create event on specific provider
result = create_calendar_event(
    user_id="user123",
    summary="Doctor Appointment",
    start_time="2024-12-05T10:00:00",
    end_time="2024-12-05T11:00:00",
    provider="outlook",  # Force Outlook Calendar
)
```

### Listing Events

```python
# List from default provider
events = list_calendar_events(
    user_id="user123",
    max_results=20,
)

# List from ALL connected providers (unified view)
events = list_calendar_events(
    user_id="user123",
    max_results=50,
    unified=True,  # Combines Google + Outlook events
)

# Get upcoming week from specific provider
from datetime import datetime, timedelta
events = list_calendar_events(
    user_id="user123",
    time_min=datetime.utcnow().isoformat() + "Z",
    time_max=(datetime.utcnow() + timedelta(days=7)).isoformat() + "Z",
    provider="google",
)
```

### Helper Functions

```python
# Get today's events across all calendars
today = get_today_events(user_id="user123", unified=True)

# Get upcoming events for next 7 days
upcoming = get_upcoming_events(user_id="user123", days_ahead=7, unified=True)

# Search events across all calendars
results = search_calendar_events(
    user_id="user123",
    query="meeting",
    unified=True,
)
```

### Updating and Deleting Events

```python
# Update event
update_calendar_event(
    user_id="user123",
    event_id="abc123",
    summary="Updated: Team Meeting",
    start_time="2024-12-01T15:00:00",
    provider="google",  # Specify provider if known
)

# Delete event
delete_calendar_event(
    user_id="user123",
    event_id="abc123",
    provider="google",
)
```

### Managing User Preferences

```python
from app.services.calendar import set_default_calendar_provider

# Set user's preferred calendar for new events
set_default_calendar_provider(user_id="user123", provider="outlook")
```

## Event Format

All events are returned in a unified format regardless of provider:

```python
{
    "id": "abc123",
    "provider": "google",  # or "outlook"
    "provider_event_id": "original_id_from_provider",
    "summary": "Meeting Title",
    "description": "Event description",
    "location": "Conference Room",
    "start": "2024-12-01T14:00:00Z",
    "end": "2024-12-01T15:00:00Z",
    "html_link": "https://calendar.google.com/...",
    "status": "confirmed",
    "attendees": [
        {
            "email": "user@example.com",
            "response_status": "accepted"
        }
    ],
    "creator": "organizer@example.com",
    "organizer": "organizer@example.com",
}
```

## Provider-Specific Features

### Google Calendar Only

```python
# Quick add using natural language (Google Calendar only)
from app.services.calendar import quick_add_event

result = quick_add_event(
    user_id="user123",
    text="Coffee with John tomorrow at 3pm",
)
```

### Outlook Calendar Notes

- Quick add is not supported (use `create_calendar_event` instead)
- Uses Microsoft Graph API
- Requires Azure AD app registration

## Database Schema

Events are cached in MongoDB for offline access:

```javascript
// calendar_events collection
{
  user_id: "user123",
  provider: "google",  // or "outlook"
  provider_event_id: "abc123",
  event_id: "abc123",
  summary: "Meeting",
  description: "Description",
  location: "Location",
  start: "2024-12-01T14:00:00Z",
  end: "2024-12-01T15:00:00Z",
  html_link: "https://...",
  status: "confirmed",
  created_at: ISODate("2024-11-29T..."),
  updated_at: ISODate("2024-11-29T...")
}

// user_settings collection
{
  user_id: "user123",
  default_calendar_provider: "google",  // or "outlook"
  google_primary_calendar_id: "primary",
  outlook_primary_calendar_id: "primary",
}

// tokens collection (OAuth tokens)
{
  user_id: "user123",
  provider: "outlook",
  access_token: "...",
  refresh_token: "...",
  expires_at: ISODate("2024-11-29T...")
}
```

## OAuth Setup

### Google Calendar

1. Google Cloud Console → Create OAuth 2.0 Client
2. Add scopes: `calendar.events`, `calendar.readonly`
3. Store credentials in `google_client_secret.json`
4. Use `app.utils.oauth_utils.load_google_credentials(user_id)`

### Outlook Calendar

1. Azure Portal → App Registrations → New registration
2. Add Microsoft Graph permissions:
   - `Calendars.ReadWrite`
   - `Calendars.ReadWrite.Shared`
   - `User.Read`
3. Set environment variables:
   ```env
   MICROSOFT_CLIENT_ID=your_client_id
   MICROSOFT_CLIENT_SECRET=your_client_secret
   MICROSOFT_TENANT_ID=common  # or specific tenant
   ```

4. Store tokens in MongoDB `tokens` collection

## Adding New Providers

To add a new calendar provider (e.g., Apple Calendar, Exchange):

1. Create new provider class inheriting from `CalendarProvider`:
   ```python
   from app.services.calendar.base_provider import CalendarProvider
   
   class AppleCalendarProvider(CalendarProvider):
       def _get_provider_name(self) -> str:
           return "apple"
       
       def create_event(self, ...):
           # Implement Apple Calendar API integration
           pass
       
       # Implement other required methods...
   ```

2. Update `unified_service.py` to include the new provider:
   ```python
   def _get_all_providers(user_id: str) -> List[CalendarProvider]:
       providers = []
       
       if connections.get("google_connected"):
           providers.append(GoogleCalendarProvider(user_id))
       
       if connections.get("outlook_connected"):
           providers.append(OutlookCalendarProvider(user_id))
       
       if connections.get("apple_connected"):  # NEW
           providers.append(AppleCalendarProvider(user_id))
       
       return providers
   ```

3. Update `check_user_calendar_connections()` to detect the new provider

## API Reference

See docstrings in:
- `unified_service.py` - Main API functions
- `base_provider.py` - Provider interface requirements
- `google_provider.py` - Google Calendar specifics
- `outlook_provider.py` - Outlook Calendar specifics

## Testing

```python
# Test connectivity
from app.services.calendar import check_user_calendar_connections

connections = check_user_calendar_connections("user123")
print(f"Google: {connections['google_connected']}")
print(f"Outlook: {connections['outlook_connected']}")

# Test unified view
from app.services.calendar import get_upcoming_events

events = get_upcoming_events("user123", unified=True)
for event in events['events']:
    print(f"{event['provider']}: {event['summary']} at {event['start']}")
```

## Performance Considerations

- Events are cached in MongoDB for fast retrieval
- Background threads update cache without blocking API calls
- Unified views may be slower (multiple API calls) but provide complete picture
- Use `provider` parameter when you know which calendar to use

## Error Handling

All functions return standardized result format:

```python
# Success
{
    "success": True,
    "events": [...],
    # ... other data
}

# Failure
{
    "success": False,
    "error": "Error message",
    "provider": "google"
}
```

## Future Enhancements

- [ ] Conflict detection across providers
- [ ] Smart scheduling suggestions
- [ ] Bulk operations
- [ ] Recurring event handling improvements
- [ ] Real-time sync via webhooks
- [ ] Calendar sharing and delegation

