# 📅 Multi-Provider Calendar Setup Guide

## What's New?

Your calendar service has been upgraded to support **both Google Calendar and Outlook Calendar** with a unified interface!

## Architecture Overview

```
app/services/
├── calendar_service.py          # ✅ Backward compatible wrapper
└── calendar/                     # 🆕 New multi-provider system
    ├── __init__.py              # Public API
    ├── base_provider.py         # Abstract provider interface
    ├── google_provider.py       # Google Calendar
    ├── outlook_provider.py      # Outlook/Microsoft Graph
    ├── unified_service.py       # Aggregates all providers
    └── README.md                # Detailed documentation
```

## ✅ Backward Compatibility

**Your existing code continues to work!** The old `calendar_service.py` now wraps the new system.

```python
# This still works exactly as before:
from app.services.calendar_service import create_calendar_event, list_calendar_events
```

## 🆕 New Features

### 1. Multi-Provider Support

```python
from app.services.calendar import (
    create_calendar_event,
    list_calendar_events,
    check_user_calendar_connections,
)

# Check what's connected
connections = check_user_calendar_connections("user123")
# {'google_connected': True, 'outlook_connected': False, 'default_provider': 'google'}

# Create event on specific provider
create_calendar_event(
    user_id="user123",
    summary="Meeting",
    start_time="2024-12-01T14:00:00",
    end_time="2024-12-01T15:00:00",
    provider="google"  # or "outlook"
)
```

### 2. Unified Calendar View

```python
# Get events from ALL calendars (Google + Outlook)
events = list_calendar_events(
    user_id="user123",
    unified=True,  # ⭐ Magic flag!
    max_results=50
)

# Returns events from both providers, sorted by time
for event in events['events']:
    print(f"{event['provider']}: {event['summary']}")
    # google: Team Meeting
    # outlook: Doctor Appointment
    # google: Lunch with Client
```

### 3. Smart Scheduling

```python
from app.services.calendar import get_upcoming_events, get_today_events

# Today's agenda across all calendars
today = get_today_events("user123", unified=True)

# Next week's schedule
week = get_upcoming_events("user123", days_ahead=7, unified=True)
```

### 4. User Preferences

```python
from app.services.calendar import set_default_calendar_provider

# Set which calendar to use by default for new events
set_default_calendar_provider("user123", "outlook")
```

## 🔧 Setup Instructions

### Google Calendar (Already Working)

No changes needed! Your existing Google OAuth setup continues to work.

### Outlook Calendar (New)

#### 1. Register App in Azure Portal

1. Go to [Azure Portal](https://portal.azure.com/)
2. Navigate to **Azure Active Directory** → **App registrations** → **New registration**
3. Set application name: "Your App - Calendar"
4. Redirect URI: `https://yourdomain.com/oauth/outlook/callback` or `http://localhost:5000/oauth/outlook/callback`
5. Click **Register**

#### 2. Configure API Permissions

1. Go to **API permissions** → **Add a permission**
2. Select **Microsoft Graph** → **Delegated permissions**
3. Add these permissions:
   - `Calendars.ReadWrite`
   - `Calendars.ReadWrite.Shared`
   - `User.Read`
   - `offline_access`
4. Click **Grant admin consent**

#### 3. Create Client Secret

1. Go to **Certificates & secrets** → **New client secret**
2. Add description: "Calendar API"
3. Set expiry (e.g., 24 months)
4. **Copy the secret value immediately** (you won't see it again!)

#### 4. Update Environment Variables

Add to your `.env` file:

```env
# Outlook/Microsoft Calendar
MICROSOFT_CLIENT_ID=your_client_id_from_azure
MICROSOFT_CLIENT_SECRET=your_client_secret_from_azure
MICROSOFT_TENANT_ID=common  # or your specific tenant ID
```

#### 5. Implement OAuth Flow

Create route in your Flask app:

```python
from flask import redirect, request, session
from app.db.collections import get_tokens_collection
import requests
from datetime import datetime, timedelta

@app.route("/oauth/outlook/authorize")
def outlook_authorize():
    """Initiate Outlook OAuth flow"""
    auth_url = (
        f"https://login.microsoftonline.com/{Config.MICROSOFT_TENANT_ID}/oauth2/v2.0/authorize"
        f"?client_id={Config.MICROSOFT_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri=http://localhost:5000/oauth/outlook/callback"
        f"&scope=Calendars.ReadWrite Calendars.ReadWrite.Shared User.Read offline_access"
    )
    return redirect(auth_url)

@app.route("/oauth/outlook/callback")
def outlook_callback():
    """Handle Outlook OAuth callback"""
    code = request.args.get("code")
    
    # Exchange code for token
    token_url = f"https://login.microsoftonline.com/{Config.MICROSOFT_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": Config.MICROSOFT_CLIENT_ID,
        "client_secret": Config.MICROSOFT_CLIENT_SECRET,
        "code": code,
        "redirect_uri": "http://localhost:5000/oauth/outlook/callback",
        "grant_type": "authorization_code",
    }
    
    response = requests.post(token_url, data=data)
    tokens = response.json()
    
    # Store tokens in database
    tokens_col = get_tokens_collection()
    user_id = session.get("user_id")  # Get from your session
    
    tokens_col.insert_one({
        "user_id": user_id,
        "provider": "outlook",
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "expires_at": datetime.utcnow() + timedelta(seconds=tokens["expires_in"]),
        "created_at": datetime.utcnow(),
    })
    
    return redirect("/calendar")
```

## 🎯 Usage Examples

### For the Calendar Agent

Update `app/agents/calendar_agent.py`:

```python
from app.services.calendar import (
    list_calendar_events,
    create_calendar_event,
    get_today_events,
    check_user_calendar_connections,
)

class CalendarAgent:
    def handle_chat(self, user_id: str, message: str, metadata=None) -> str:
        lower = message.lower()
        
        # Show unified calendar
        if "show my calendar" in lower or "my schedule" in lower:
            # Get from ALL calendars
            result = list_calendar_events(
                user_id=user_id,
                unified=True,  # ⭐ Include both Google & Outlook
                max_results=20
            )
            
            if result.get("success"):
                events = result.get("events", [])
                
                # Group by provider
                google_events = [e for e in events if e["provider"] == "google"]
                outlook_events = [e for e in events if e["provider"] == "outlook"]
                
                response = "📅 **Your Schedule**\n\n"
                
                if google_events:
                    response += f"**Google Calendar** ({len(google_events)} events)\n"
                    for event in google_events[:5]:
                        response += f"• {event['summary']} - {event['start']}\n"
                
                if outlook_events:
                    response += f"\n**Outlook Calendar** ({len(outlook_events)} events)\n"
                    for event in outlook_events[:5]:
                        response += f"• {event['summary']} - {event['start']}\n"
                
                return response
        
        # Create event (uses default provider)
        if "schedule" in lower or "create event" in lower:
            # ... your existing event creation logic
            result = create_calendar_event(
                user_id=user_id,
                summary="Meeting",
                start_time=start_time,
                end_time=end_time,
                # provider automatically determined by user's default
            )
```

### For the Frontend

```javascript
// Check which calendars are connected
const checkCalendars = async () => {
  const response = await fetch('/api/calendar/connections');
  const data = await response.json();
  
  console.log('Google:', data.google_connected);
  console.log('Outlook:', data.outlook_connected);
  console.log('Default:', data.default_provider);
};

// Get unified calendar view
const getUnifiedCalendar = async () => {
  const response = await fetch('/api/calendar/events?unified=true&max_results=50');
  const data = await response.json();
  
  // data.events contains events from all providers
  data.events.forEach(event => {
    console.log(`[${event.provider}] ${event.summary}`);
  });
};

// Let user choose calendar for new event
const createEvent = async (eventData, provider) => {
  const response = await fetch('/api/calendar/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...eventData,
      provider: provider  // 'google' or 'outlook'
    })
  });
};
```

## 🗄️ Database Collections

### `calendar_events` Collection

```javascript
{
  _id: ObjectId("..."),
  user_id: "user123",
  provider: "google",  // or "outlook"
  provider_event_id: "abc123",
  event_id: "abc123",
  summary: "Team Meeting",
  description: "Quarterly planning",
  location: "Conference Room A",
  start: "2024-12-01T14:00:00Z",
  end: "2024-12-01T15:00:00Z",
  html_link: "https://calendar.google.com/...",
  status: "confirmed",
  created_at: ISODate("2024-11-29..."),
  updated_at: ISODate("2024-11-29...")
}
```

### `user_settings` Collection

```javascript
{
  _id: ObjectId("..."),
  user_id: "user123",
  default_calendar_provider: "google",  // or "outlook"
}
```

### `tokens` Collection (for Outlook)

```javascript
{
  _id: ObjectId("..."),
  user_id: "user123",
  provider: "outlook",
  access_token: "eyJ0eXAi...",
  refresh_token: "M.R3_BAY...",
  expires_at: ISODate("2024-12-29..."),
  created_at: ISODate("2024-11-29...")
}
```

## 🧪 Testing

```python
# Test Google Calendar
from app.services.calendar import list_calendar_events

result = list_calendar_events("user123", provider="google")
print(result)

# Test Outlook Calendar (after OAuth setup)
result = list_calendar_events("user123", provider="outlook")
print(result)

# Test unified view
result = list_calendar_events("user123", unified=True)
print(f"Total events: {result['count']}")
for event in result['events']:
    print(f"[{event['provider']}] {event['summary']}")
```

## 🚀 Next Steps

1. **Test Google Calendar** - Should work immediately
2. **Set up Azure App** - Follow steps above for Outlook
3. **Add OAuth routes** - Implement authorization flow
4. **Update Calendar Agent** - Use unified view
5. **Update Frontend** - Show multi-calendar UI
6. **Test end-to-end** - Create/view events on both calendars

## 📚 Documentation

- Full API reference: `app/services/calendar/README.md`
- Provider interface: `app/services/calendar/base_provider.py`
- Google implementation: `app/services/calendar/google_provider.py`
- Outlook implementation: `app/services/calendar/outlook_provider.py`

## 🎨 UI Ideas

```
┌─────────────────────────────────────────┐
│  📅 My Calendar                         │
├─────────────────────────────────────────┤
│  Connected: [🟢 Google] [🟢 Outlook]   │
│  Default: Google  [Change]              │
├─────────────────────────────────────────┤
│  Today's Events (All Calendars)         │
│                                         │
│  🔵 9:00 AM - Team Standup (Google)    │
│  🟠 2:00 PM - Client Call (Outlook)    │
│  🔵 4:00 PM - Code Review (Google)     │
│                                         │
│  [+ New Event]  📥 Sync All            │
└─────────────────────────────────────────┘
```

## ⚠️ Important Notes

1. **Backward Compatibility**: All existing calendar code continues to work
2. **OAuth Tokens**: Outlook tokens expire and need refresh logic (TODO)
3. **Rate Limits**: Be mindful of API rate limits for each provider
4. **Timezones**: All times are in ISO format with timezone info
5. **Permissions**: Ensure users understand which calendar they're authorizing

## 🐛 Troubleshooting

### "Not connected to Outlook"
- Check OAuth setup is complete
- Verify tokens are stored in database
- Check MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET in .env

### Events not showing
- Check `unified=True` flag is set
- Verify both providers return `success: true`
- Check time range parameters

### Token expired errors
- Implement token refresh logic using refresh_token
- Check `expires_at` field in tokens collection

## 💡 Pro Tips

1. Use `unified=True` for user-facing calendar views
2. Use specific `provider` when you know the event source
3. Cache aggressively - events are synced in background
4. Let users choose default provider in settings
5. Show provider badges in UI (Google 🔵, Outlook 🟠)

---

**Need help?** Check the detailed documentation in `app/services/calendar/README.md`

