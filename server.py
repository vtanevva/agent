"""Main Flask server for the mental health AI assistant"""

import os
import json
import uuid
import pickle
import logging
from datetime import datetime

import certifi
import psutil
import requests
from dotenv import load_dotenv
from flask import (
    Flask, request, jsonify, send_from_directory, 
    redirect, session, render_template_string
)
from flask_cors import CORS
from requests_oauthlib import OAuth2Session
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# Local modules
from app.agent_core.agent import run_agent
from app.agent_core.tool_registry import all_openai_schemas
from app.chatbot import chat_with_gpt
from app.chat_embeddings import (
    get_user_facts, save_chat_to_memory, extract_facts_with_gpt
)
from app.tools.calendar_manager import (
    detect_calendar_requests, parse_datetime_from_text, 
    create_calendar_event, list_calendar_events
)
from app.database import init_database
from app.utils.db_utils import get_conversations_collection, get_tokens_collection
from app.utils.oauth_utils import (
    load_google_credentials, save_google_credentials, get_gmail_profile,
    require_google_auth, build_google_flow, parse_expo_state,
    GOOGLE_SCOPES, IG_SCOPES, OAUTH_BASE, TOKEN_URL
)
from app.config import Config

# Environment setup
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# App setup
app = Flask(__name__, static_folder="my-chatbot/build", static_url_path="")
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
app.secret_key = Config.FLASK_SECRET_KEY or "change-me-in-prod"

# Initialize database
db_connected = init_database()
if db_connected:
    print("[INIT] ✅ MongoDB connected successfully")
else:
    print("[INIT] ⚠️ MongoDB not connected - running in offline mode")

# Instagram OAuth config
IG_APP_ID = Config.IG_APP_ID
IG_APP_SECRET = Config.IG_APP_SECRET

# Verify calendar tools are registered
available_tools = [tool['function']['name'] for tool in all_openai_schemas()]
print(f"[INIT] Available tools: {available_tools}")


# ──────────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────────

def save_message(user_id, session_id, user_message, bot_reply,
                 emotion=None, suicide_flag=False):
    """Save a message pair (user + bot) to MongoDB"""
    conversations = get_conversations_collection()
    if conversations is None:
        return
    try:
        message_pair = {
            "timestamp": datetime.utcnow().isoformat(),
            "role": "user",
            "text": user_message,
            "emotion": emotion,
            "suicide_flag": suicide_flag,
        }
        bot_response = {
            "timestamp": datetime.utcnow().isoformat(),
            "role": "bot",
            "text": bot_reply,
        }
        conversations.update_one(
            {"user_id": user_id, "session_id": session_id},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "session_id": session_id,
                    "created_at": datetime.utcnow(),
                },
                "$push": {"messages": {"$each": [message_pair, bot_response]}},
            },
            upsert=True,
        )
    except Exception as e:
        print(f"[ERROR] Failed to save message: {e}", flush=True)


def _build_flow(redirect_uri: str, state: str | None = None):
    """Return a google-auth Flow object with the common settings."""
    return build_google_flow(redirect_uri, state)


def _get_redirect_uri():
    """Get the appropriate redirect URI based on environment."""
    if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https':
        return "https://web-production-0b6ce.up.railway.app/google/oauth2callback"
    return "http://localhost:10000/google/oauth2callback"


def _get_success_page_template(display_email: str):
    """Return the success page HTML template for OAuth."""
    return f"""
      <!doctype html>
      <html>
        <head>
          <title>Google Connected - Return to App</title>
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <style>
            @keyframes checkmark {{
              0% {{ transform: scale(0); }}
              50% {{ transform: scale(1.2); }}
              100% {{ transform: scale(1); }}
            }}
            .checkmark {{
              animation: checkmark 0.6s ease-in-out;
            }}
          </style>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; margin: 0;">
          <div style="background: rgba(255,255,255,0.95); padding: 50px 30px; border-radius: 25px; backdrop-filter: blur(10px); max-width: 400px; width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,0.3);">
            <div class="checkmark" style="font-size: 80px; margin-bottom: 20px;">✅</div>
            <h1 style="font-size: 2em; margin-bottom: 15px; color: #333; font-weight: 700;">Successfully Logged In!</h1>
            <p style="font-size: 1.1em; margin-bottom: 30px; color: #666; line-height: 1.6;">
              Your Google account has been connected successfully.
            </p>
            <div style="background: #f0f0f0; padding: 20px; border-radius: 15px; margin-bottom: 30px;">
              <p style="font-size: 1.3em; margin: 0; color: #333; font-weight: 600;">
                👉 Return to the App
              </p>
              <p style="font-size: 0.95em; margin-top: 10px; color: #666;">
                Close this browser tab and go back to your app. You're all set!
              </p>
            </div>
            <p style="font-size: 0.9em; color: #999; margin-top: 20px;">
              Connected as: <strong style="color: #667eea;">{display_email}</strong>
            </p>
          </div>
        </body>
      </html>
    """


# ──────────────────────────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────────────────────────

@app.route("/memory")
def memory_usage():
    """Get current memory usage statistics."""
    try:
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        system_memory = psutil.virtual_memory()
        
        return jsonify({
            "process_memory_mb": round(memory_info.rss / 1024 / 1024, 2),
            "process_memory_percent": round(process.memory_percent(), 2),
            "system_memory_total_gb": round(system_memory.total / 1024 / 1024 / 1024, 2),
            "system_memory_available_gb": round(system_memory.available / 1024 / 1024 / 1024, 2),
            "system_memory_percent": round(system_memory.percent, 2),
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({"error": str(e), "timestamp": datetime.now().isoformat()}), 500


@app.route("/api/chat", methods=["POST"])
def chat():
    """Main chat endpoint that handles user messages."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        user_message = (data.get("message") or "").strip()
        user_id = (data.get("user_id") or "anonymous").strip().lower()
        session_id = data.get("session_id") or f"{user_id}-{uuid.uuid4().hex[:8]}"

        if not user_message:
            return jsonify({"reply": "No message received. Please enter something."}), 400

        # Check Google auth if needed
        auth_response = require_google_auth(user_id)
        if auth_response:
            return auth_response

        # Handle calendar requests
        calendar_requests = detect_calendar_requests(user_message)
        if calendar_requests:
            try:
                for calendar_request in calendar_requests:
                    start_time, end_time = parse_datetime_from_text(calendar_request['full_match'])
                    if start_time and end_time:
                        result = create_calendar_event(
                            user_id=user_id,
                            summary=calendar_request['description'],
                            start_time=start_time.isoformat(),
                            end_time=end_time.isoformat(),
                            description=f"Event created from chat: {user_message}"
                        )
                        
                        if result.get('success'):
                            reply = f"✅ I've scheduled '{calendar_request['description']}' for {start_time.strftime('%B %d at %I:%M %p')}. You can view it in your calendar!"
                        else:
                            reply = f"❌ Sorry, I couldn't schedule the event. Please make sure you're connected to Google Calendar."
                        
                        save_message(user_id, session_id, user_message, reply, None, False)
                        return jsonify({"reply": reply})
            except Exception as e:
                reply = f"❌ Error creating calendar event: {str(e)}"
                save_message(user_id, session_id, user_message, reply, None, False)
                return jsonify({"reply": reply})

        # Handle calendar viewing requests
        calendar_keywords = ["calendar", "events", "schedule", "appointments", "meetings"]
        if any(keyword in user_message.lower() for keyword in calendar_keywords):
            auth_response = require_google_auth(user_id)
            if auth_response:
                return auth_response
            reply = run_agent(user_id=user_id, message=user_message, history=[])
            emotion = None
            suicide_flag = False
        else:
            # Load session history
            session_memory = []
            conversations = get_conversations_collection()
            if conversations is not None:
                try:
                    chat_doc = conversations.find_one({"user_id": user_id, "session_id": session_id})
                    if chat_doc and "messages" in chat_doc:
                        for msg in chat_doc["messages"][-20:]:
                            role = "assistant" if msg["role"] == "bot" else msg["role"]
                            session_memory.append({"role": role, "content": msg["text"]})
                except Exception as e:
                    print(f"[ERROR] Failed to load session history: {e}", flush=True)

            # Handle email queries with agent
            email_keywords = ["emails", "email", "inbox", "reply to"]
            if any(kw in user_message.lower() for kw in email_keywords):
                auth_response = require_google_auth(user_id)
                if auth_response:
                    return auth_response
                reply = run_agent(user_id=user_id, message=user_message, history=session_memory)
                emotion = None
                suicide_flag = False
            else:
                # Default: GPT chat with memory
                reply, emotion, suicide_flag = chat_with_gpt(
                    user_message,
                    user_id=user_id,
                    session_id=session_id,
                    return_meta=True,
                    session_memory=session_memory
                )

        # Save conversation
        save_message(user_id, session_id, user_message, reply, emotion, suicide_flag)

        # Extract and save new facts
        extracted = extract_facts_with_gpt(user_message)
        for line in extracted.split("\n"):
            line = line.strip("- ").strip()
            if line and line.lower() != "none":
                fact = line.removeprefix("FACT:").strip()
                save_chat_to_memory(fact, session_id, user_id=user_id, emotion=emotion)

        return jsonify({"reply": reply})

    except Exception as e:
        print(f"[ERROR] Error in chat endpoint: {e}", flush=True)
        return jsonify({"error": "Invalid request", "message": str(e)}), 400


@app.post("/agent")
def agent_endpoint():
    """Agent endpoint for tool-calling functionality."""
    data = request.get_json(force=True)
    reply = run_agent(
        user_id=data.get("user_id", "demo"),
        message=data["message"],
        history=data.get("history", [])
    )
    return jsonify({"reply": reply})


@app.route("/api/google-profile", methods=["POST"])
def google_profile():
    """Return the Gmail address for a given user_id."""
    data = request.get_json(force=True) or {}
    user_id = data.get("user_id")
    creds = load_google_credentials(user_id)
    if not creds:
        return jsonify({"email": None}), 200

    try:
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        return jsonify({"email": profile.get("emailAddress")}), 200
    except Exception:
        return jsonify({"email": None}), 200


@app.route("/api/sessions-log", methods=["POST"])
def sessions_log():
    """Get session list and memory for a user."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "").strip().lower()
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    conversations = get_conversations_collection()
    if conversations is None:
        return jsonify({"sessions": [], "memory": []})
    
    sessions = conversations.find({"user_id": user_id})
    session_map = {s["session_id"]: s.get("session_name", "") for s in sessions}
    session_list = [
        {"session_id": sid, "name": session_map[sid]}
        for sid in sorted(session_map)
    ]

    memory = get_user_facts(user_id)
    return jsonify({
        "sessions": session_list,
        "memory": memory
    })


@app.route("/api/session_chat", methods=["POST"])
def session_chat():
    """Get chat history for a specific session."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id")
    session_id = data.get("session_id")

    conversations = get_conversations_collection()
    if conversations is None:
        return jsonify({"chat": []})

    entry = conversations.find_one({"user_id": user_id, "session_id": session_id})
    return jsonify({"chat": entry.get("messages", []) if entry else []})


@app.route("/api/calendar/events", methods=["POST"])
def calendar_events():
    """Get calendar events for a user."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id")
    max_results = data.get("max_results", 10)
    time_min = data.get("time_min")
    time_max = data.get("time_max")

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    try:
        result = list_calendar_events(
            user_id=user_id,
            max_results=max_results,
            time_min=time_min,
            time_max=time_max
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/calendar/create", methods=["POST"])
def create_calendar_event_endpoint():
    """Create a calendar event."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id")
    summary = data.get("summary")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    description = data.get("description", "")
    location = data.get("location", "")
    attendees = data.get("attendees", [])

    if not all([user_id, summary, start_time, end_time]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        result = create_calendar_event(
            user_id=user_id,
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            attendees=attendees
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/save-session-name", methods=["POST"])
def save_session_name():
    """Save a name for a session."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id")
    session_id = data.get("session_id")
    name = data.get("name", "")

    conversations = get_conversations_collection()
    if conversations is not None:
        conversations.update_one(
            {"user_id": user_id, "session_id": session_id},
            {"$set": {"session_name": name}},
            upsert=True,
        )

    return jsonify({"status": "ok"})


@app.route("/api/test-mongo")
def test_mongo():
    """Test MongoDB connection."""
    conversations = get_conversations_collection()
    if conversations is not None:
        conversations.insert_one({"msg": "Mongo is working!", "timestamp": datetime.utcnow()})
    return jsonify({"status": "success"})


# ──────────────────────────────────────────────────────────────────
# OAuth Endpoints
# ──────────────────────────────────────────────────────────────────

@app.get("/google/auth/<user_id>")
def google_auth(user_id):
    """Redirect browser to Google OAuth consent screen."""
    try:
        expo_app = request.args.get('expo_app', 'false').lower() == 'true'
        expo_redirect = request.args.get('expo_redirect', 'http://localhost:8081')
        redirect_uri = _get_redirect_uri()
        
        flow = _build_flow(redirect_uri)
        state_with_expo = f"{user_id}|expo:{expo_app}|redirect:{expo_redirect}" if expo_app else user_id
        
        auth_url, _ = flow.authorization_url(
            prompt="consent select_account",
            access_type="offline",
            state=state_with_expo,
        )
        
        if "?" in auth_url:
            auth_url += "&user_agent=web"
        else:
            auth_url += "?user_agent=web"

        return redirect(auth_url)
    except Exception as e:
        print(f"[ERROR] OAuth error: {e}", flush=True)
        return render_template_string("""
        <!doctype html>
        <html>
          <head><title>OAuth Error</title></head>
          <body>
            <h1>OAuth Error</h1>
            <p>Error: {{ error }}</p>
            <a href="/">Back to App</a>
          </body>
        </html>
        """, error=str(e))


@app.route("/google/oauth2callback", methods=["GET", "POST"])
def google_callback():
    """OAuth callback endpoint."""
    try:
        state_raw = request.args.get("state")
        error = request.args.get("error")
        
        if not state_raw:
            return render_template_string("""
            <!doctype html>
            <html>
              <head><title>OAuth Error</title></head>
              <body>
                <h1>OAuth Error</h1>
                <p>Missing state parameter</p>
                <a href="/">Back to App</a>
              </body>
            </html>
            """), 400
        
        state, expo_app, expo_redirect = parse_expo_state(state_raw)
        
        if error:
            return render_template_string("""
            <!doctype html>
            <html>
              <head><title>OAuth Error</title></head>
              <body>
                <h1>OAuth Error</h1>
                <p>Error: {{ error }}</p>
                <a href="/">Back to App</a>
              </body>
            </html>
            """, error=error)
        
        redirect_uri = _get_redirect_uri()
        flow = _build_flow(redirect_uri, state=state_raw)
        
        try:
            flow.fetch_token(authorization_response=request.url)
        except Exception as token_error:
            return render_template_string("""
            <!doctype html>
            <html>
              <head><title>OAuth Token Error</title></head>
              <body>
                <h1>Authentication Error</h1>
                <p>Error: {{ error }}</p>
                <p>This might be due to:</p>
                <ul>
                  <li>Authorization code expired (try again)</li>
                  <li>Authorization code already used</li>
                  <li>Clock synchronization issue</li>
                </ul>
                <a href="/">Back to App</a>
              </body>
            </html>
            """, error=str(token_error))
        
        creds = flow.credentials
        real_email = get_gmail_profile(creds)
        if not real_email:
            real_email = state
        
        save_google_credentials(state, creds, real_email)
            
    except Exception as e:
        print(f"[ERROR] OAuth callback error: {e}", flush=True)
        if "|expo:" in str(state_raw or "").lower():
            user_email = str(state_raw or "unknown").split("|")[0]
            return render_template_string(_get_success_page_template(user_email))
        
        return render_template_string("""
        <!doctype html>
        <html>
          <head><title>OAuth Error</title></head>
          <body>
            <h1>OAuth Error</h1>
            <p>Error: {{ error }}</p>
            <a href="/">Back to App</a>
          </body>
        </html>
        """, error=str(e))

    user_email = real_email if real_email else state
    
    if expo_app:
        display_email = str(user_email) if user_email else str(state)
        return render_template_string(_get_success_page_template(display_email))
    
    # Web app redirect
    frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
    redirect_url = f"{frontend_url}/?username={state}&email={user_email}"
    return render_template_string("""
      <!doctype html>
      <html>
        <head>
          <title>Google Connected</title>
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <script>
            if (window.opener) {
              try {
                window.opener.postMessage({
                  type: 'GOOGLE_AUTH_SUCCESS',
                  userEmail: "{{ user_email }}"
                }, '*');
              } catch (e) {
                console.log('Could not notify parent window:', e);
              }
              window.close();
            } else {
              const redirectUrl = "{{ redirect_url }}";
              window.location.href = redirectUrl;
            }
          </script>
        </head>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; min-height: 100vh; display: flex; flex-direction: column; justify-content: center;">
          <div style="background: rgba(255,255,255,0.1); padding: 40px; border-radius: 20px; backdrop-filter: blur(10px);">
            <h1 style="font-size: 2.5em; margin-bottom: 20px;">✅ Connected to Google!</h1>
            <p style="font-size: 1.2em; margin-bottom: 30px;">You can now use Gmail and Calendar features.</p>
            <p style="font-size: 1em; margin-bottom: 20px;">Redirecting...</p>
            <p><a href="{{ redirect_url }}" style="color: white; text-decoration: none; background: rgba(255,255,255,0.2); padding: 12px 24px; border-radius: 25px; display: inline-block;">Continue to Chat</a></p>
          </div>
        </body>
      </html>
    """, user_email=user_email, username=state, redirect_url=redirect_url)


@app.route("/instagram/auth")
def instagram_auth():
    """Instagram OAuth initiation."""
    user_id = request.args.get("user_id", "demo")
    redirect_uri = request.url_root.rstrip("/") + "/instagram/callback"
    oauth = OAuth2Session(IG_APP_ID, redirect_uri=redirect_uri, scope=IG_SCOPES)

    auth_url, state = oauth.authorization_url(
        OAUTH_BASE,
        auth_type="rerequest",
    )

    session["oauth_state"] = state
    session["oauth_user_id"] = user_id
    return redirect(auth_url)


@app.route("/instagram/callback")
def instagram_callback():
    """Instagram OAuth callback."""
    state = session.pop("oauth_state", None)
    user_id = session.pop("oauth_user_id", "demo")
    redirect_uri = request.url_root.rstrip("/") + "/instagram/callback"

    oauth = OAuth2Session(
        IG_APP_ID,
        state=state,
        redirect_uri=redirect_uri
    )

    token = oauth.fetch_token(
        TOKEN_URL,
        client_secret=IG_APP_SECRET,
        authorization_response=request.url,
    )
    user_token = token.get("access_token")

    # List pages user manages
    pages_resp = requests.get(
        "https://graph.facebook.com/v19.0/me/accounts",
        params={"access_token": user_token},
        timeout=10,
    ).json()

    pages = pages_resp.get("data", [])
    if not pages:
        return "❌ No Facebook Pages found. Make sure you granted the Pages permission.", 400

    # Find page with Instagram Business account
    linked = None
    for p in pages:
        test = requests.get(
            f"https://graph.facebook.com/v19.0/{p['id']}",
            params={
                "fields": "instagram_business_account",
                "access_token": p["access_token"],
            },
            timeout=10,
        ).json()
        if test.get("instagram_business_account", {}).get("id"):
            linked = (p, test["instagram_business_account"])
            break

    if not linked:
        return (
            "❌ None of your Pages are linked to an IG Business/Creator account. "
            "Go into Facebook Page Settings and link your IG profile first."
        ), 400

    page, ig_info = linked
    page_id = page["id"]
    page_token = page["access_token"]
    ig_user_id = ig_info["id"]

    # Persist to MongoDB
    tokens = get_tokens_collection()
    if tokens is not None:
        try:
            tokens.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "instagram": {
                            "page_id": page_id,
                            "ig_user_id": ig_user_id,
                            "access_token": page_token
                        }
                    }
                },
                upsert=True
            )
        except Exception as e:
            print(f"[ERROR] Failed to save Instagram credentials: {e}", flush=True)
            return f"❌ Error saving credentials: {e}", 500
    else:
        # Fallback to file-based storage
        TOK_DIR = os.path.join(os.path.dirname(__file__), "tokens")
        os.makedirs(TOK_DIR, exist_ok=True)
        with open(f"{TOK_DIR}/{user_id}_ig.pkl", "wb") as f:
            pickle.dump(
                {"page_id": page_id, "ig_user_id": ig_user_id, "access_token": page_token},
                f
            )

    return "✅ Instagram connected! You can close this tab."


# ──────────────────────────────────────────────────────────────────
# Frontend Serving
# ──────────────────────────────────────────────────────────────────

@app.route("/chat/<path:chat_path>")
def serve_chat(chat_path):
    """Serve React app for chat routes."""
    return send_from_directory(app.static_folder, "index.html")


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    """Serve React frontend or static files."""
    # Handle API routes
    if path.startswith("api/"):
        return jsonify({"error": "API endpoint not found"}), 404
    
    # Handle static files
    full_path = os.path.join(app.static_folder, path)
    if path and os.path.exists(full_path):
        return send_from_directory(app.static_folder, path)
    
    # Serve React app for all other routes
    return send_from_directory(app.static_folder, "index.html")


# ──────────────────────────────────────────────────────────────────
# Main Entry Point
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port_str = os.getenv("PORT", "10000")
    try:
        port = int(''.join(filter(str.isdigit, port_str)) or "10000")
    except ValueError:
        port = 10000
    
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    