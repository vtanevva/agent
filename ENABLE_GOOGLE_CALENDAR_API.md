# 🔧 How to Enable Google Calendar API

## The Problem
Your app is trying to access Google Calendar, but the API is not enabled in your Google Cloud project.

## Quick Fix (2 minutes)

### Step 1: Go to Google Cloud Console
Click this link (it has your project ID already):
**https://console.developers.google.com/apis/api/calendar-json.googleapis.com/overview?project=748212545234**

Or manually:
1. Go to https://console.cloud.google.com/
2. Select your project (project ID: 748212545234)
3. Go to **APIs & Services** → **Library**

### Step 2: Enable Calendar API
1. Search for **"Google Calendar API"**
2. Click on **"Google Calendar API"**
3. Click the big blue **"ENABLE"** button
4. Wait 1-2 minutes for it to activate

### Step 3: Verify
1. Go to **APIs & Services** → **Enabled APIs**
2. You should see **"Google Calendar API"** in the list ✅

### Step 4: Test Again
Restart your server and try "show my calendar events" again!

---

## Alternative: Enable via Command Line

If you have `gcloud` CLI installed:

```bash
gcloud services enable calendar-json.googleapis.com --project=748212545234
```

---

## Check Your OAuth Scopes

Also make sure your OAuth credentials include the Calendar scope:

1. Go to **APIs & Services** → **Credentials**
2. Click on your OAuth 2.0 Client ID
3. Check **Authorized redirect URIs** includes your callback URL
4. Make sure the scopes include:
   - `https://www.googleapis.com/auth/calendar.events`
   - `https://www.googleapis.com/auth/calendar.readonly`

---

## Still Not Working?

If events still don't show after enabling:

1. **Wait 2-3 minutes** - API activation can take a moment
2. **Re-authenticate** - User may need to reconnect Google Calendar
3. **Check logs** - Look for any new error messages
4. **Verify credentials** - Make sure OAuth token is still valid

---

## Quick Test

After enabling, you can test directly:

```python
from app.services.calendar import list_calendar_events

result = list_calendar_events("your_user_id", unified=True)
print(result)
```

You should see your events! 🎉

