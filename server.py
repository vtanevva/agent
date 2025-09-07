import os, uuid, pickle
import ssl
import certifi

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Configure SSL context for better certificate handling
ssl_context = ssl.create_default_context(cafile=certifi.where())
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from datetime import datetime
from email.mime.text import MIMEText
import base64
import json

from flask import Flask, request, jsonify, send_from_directory, redirect, url_for, session
from flask_cors import CORS
from pymongo import MongoClient
from dotenv import load_dotenv

import requests
from requests_oauthlib import OAuth2Session
import psutil  # Add this import at the top

# ──────────────────────────────────────────────────────────────────
# Local modules
# ──────────────────────────────────────────────────────────────────
from app.agent_core.agent import run_agent
from app.chatbot import chat_with_gpt
from app.chat_embeddings import get_user_facts
from app.chat_embeddings import save_chat_to_memory, extract_facts_with_gpt

# Import calendar tools to ensure they're registered
from app.tools.calendar_manager import detect_calendar_requests, parse_datetime_from_text, create_calendar_event, list_calendar_events

# Verify calendar tools are registered
from app.agent_core.tool_registry import all_openai_schemas
available_tools = [tool['function']['name'] for tool in all_openai_schemas()]
print(f"[INIT] Available tools: {available_tools}")



# Google libs
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# ──────────────────────────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="my-chatbot/build", static_url_path="")
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Debug port binding
print(f"[DEBUG] App initialized. PORT env var: {os.getenv('PORT')}")
print(f"[DEBUG] Current working directory: {os.getcwd()}")
print(f"[DEBUG] Available environment variables: {list(os.environ.keys())}")

# Health check removed for Railway deployment

# Memory usage monitoring endpoint
@app.route("/memory")
def memory_usage():
    try:
        # Get current process memory usage
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        # Get system memory info
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

# ──────────────────────────────────────────────────────────────────
# Config / DB
# ──────────────────────────────────────────────────────────────────
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
GOOGLE_JSON = os.getenv("GOOGLE_SECRET_FILE", "google_client_secret.json")

# OAuth scopes
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.events",
]

# Instagram / Facebook OAuth config
IG_APP_ID     = os.getenv("IG_APP_ID")
IG_APP_SECRET = os.getenv("IG_APP_SECRET")
OAUTH_BASE    = "https://www.facebook.com/v19.0/dialog/oauth"
TOKEN_URL     = "https://graph.facebook.com/v19.0/oauth/access_token"
IG_SCOPES     = [
    "pages_show_list",
    "instagram_basic",
    "instagram_manage_messages",
]

# Initialize MongoDB connection with error handling
client = None
db = None
conversations = None
tokens = None

if MONGO_URI:
    try:
        # Add database name if not present in URI
        
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Test the connection
        client.admin.command('ping')
        db = client.get_database()
        conversations = db["conversations"]
        tokens = db["tokens"]
        print(f"[INIT] MongoDB connected successfully. DB={db.name}", flush=True)
    except Exception as e:
        print(f"[WARNING] MongoDB connection failed: {e}", flush=True)
        print("[INFO] Running in offline mode - some features will be limited", flush=True)
else:
    print("[WARNING] MONGO_URI not set. Running in offline mode.", flush=True)

# Flask session secret
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-prod")

# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────


def save_message(user_id, session_id, user_message, bot_reply,
                 emotion=None, suicide_flag=False):
    if conversations is None:
        print(f"[INFO] Skipping message save - MongoDB not available", flush=True)
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


def load_google_credentials(user_id: str) -> Credentials | None:
    """
    Fetch saved Google OAuth2 credentials for `user_id` from MongoDB
    and rehydrate to a Credentials instance.
    Returns None if no creds are found.
    """
    if tokens is None:
        print(f"[INFO] Cannot load Google credentials - MongoDB not available", flush=True)
        return None
    try:
        doc = tokens.find_one({"user_id": user_id}, {"google": 1})
        if not doc or "google" not in doc:
            return None
        return Credentials.from_authorized_user_info(doc["google"])
    except Exception as e:
        print(f"[ERROR] Failed to load Google credentials: {e}", flush=True)
        return None

# ──────────────────────────────────────────────────────────────────
# OAuth Flow Builder
# ──────────────────────────────────────────────────────────────────
def _build_flow(redirect_uri: str, state: str | None = None):
    """Return a google-auth Flow object with the common settings."""
    # Try to use environment variables first, fallback to file
    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    if google_client_id and google_client_secret:
        # Use environment variables
        google_project_id = os.getenv("GOOGLE_PROJECT_ID", "gmail-agent-466700")
        google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "https://web-production-0b6ce.up.railway.app/google/oauth2callback/demo")
        
        client_config = {
            "web": {
                "client_id": google_client_id,
                "project_id": google_project_id,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": google_client_secret,
                "redirect_uris": [google_redirect_uri]
            }
        }
        flow = Flow.from_client_config(
            client_config,
            scopes=GOOGLE_SCOPES,
            redirect_uri=redirect_uri,
            state=state,
        )
    else:
        # Fallback to file
        flow = Flow.from_client_secrets_file(
            GOOGLE_JSON,
            scopes=GOOGLE_SCOPES,
            redirect_uri=redirect_uri,
            state=state,
        )
    
    # Configure SSL for the flow
    flow.redirect_uri = redirect_uri
    return flow

# ──────────────────────────────────────────────────────────────────
# /api/chat  – now tries tool-calling first, falls back to plain chat
# ──────────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat():
    data         = request.get_json(force=True, silent=True) or {}
    user_message = (data.get("message") or "").strip()
    user_id      = (data.get("user_id") or "anonymous").strip().lower()
    session_id   = data.get("session_id") or f"{user_id}-{uuid.uuid4().hex[:8]}"

    if not user_message:
        return jsonify({"reply": "No message received. Please enter something."}), 400

    # 📅 Detect calendar requests first
    calendar_requests = detect_calendar_requests(user_message)
    if calendar_requests:
        # Handle calendar event creation
        try:
            for calendar_request in calendar_requests:
                start_time, end_time = parse_datetime_from_text(calendar_request['full_match'])
                if start_time and end_time:
                    from app.tools.calendar_manager import create_calendar_event
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
                    
                    emotion = None
                    suicide_flag = False
                    
                    # Save the conversation
                    save_message(user_id, session_id, user_message, reply, emotion, suicide_flag)
                    return jsonify({"reply": reply})
        except Exception as e:
            reply = f"❌ Error creating calendar event: {str(e)}"
            emotion = None
            suicide_flag = False
            
            # Save the conversation
            save_message(user_id, session_id, user_message, reply, emotion, suicide_flag)
            return jsonify({"reply": reply})

    # 📅 Detect calendar viewing requests
    calendar_keywords = ["calendar", "events", "schedule", "appointments", "meetings"]
    if any(keyword in user_message.lower() for keyword in calendar_keywords):
        creds = load_google_credentials(user_id)
        if not creds:
            # Tell front‑end to connect Google
            return jsonify({
                "action":      "connect_google",
                "connect_url": url_for("google_auth", user_id=user_id, _external=True)
            })
        # Call your agent to handle calendar
        reply = run_agent(user_id=user_id, message=user_message, history=[])
        emotion = None
        suicide_flag = False

    # 📚 Load recent session history for RAG
    session_memory = []
    if conversations is not None:
        try:
            chat_doc = conversations.find_one({"user_id": user_id, "session_id": session_id})
            if chat_doc and "messages" in chat_doc:
                for msg in chat_doc["messages"][-20:]:
                    role = "assistant" if msg["role"] == "bot" else msg["role"]
                    session_memory.append({"role": role, "content": msg["text"]})
        except Exception as e:
            print(f"[ERROR] Failed to load session history: {e}", flush=True)
    else:
        print(f"[INFO] Cannot load session history - MongoDB not available", flush=True)

    # 🗄️ Always load & log your long‑term memory
    memory = get_user_facts(user_id)
    print(f"\n--- FACT MEMORY for {user_id} ({len(memory)} facts) ---")
    for fact in memory:
        print(f"- {fact}")
    print("------------------------------------------\n")

    # ✉️ Detect email queries and use your agent’s Gmail tool first
    lm = user_message.lower()
    if any(kw in lm for kw in ["emails", "email", "inbox", "reply to"]):
        creds = load_google_credentials(user_id)
        if not creds:
            # Tell front‑end to connect Google
            return jsonify({
                "action":      "connect_google",
                "connect_url": url_for("google_auth", user_id=user_id, _external=True)
            })
        # Call your agent to handle email
        reply = run_agent(user_id=user_id, message=user_message, history=session_memory)
        emotion = None
        suicide_flag = False

    else:
        # 🤖 Default: GPT chat with memory
        reply, emotion, suicide_flag = chat_with_gpt(
            user_message,
            user_id=user_id,
            session_id=session_id,
            return_meta=True,
            session_memory=session_memory
        )

    # 💾 Save conversation to MongoDB
    save_message(user_id, session_id, user_message, reply, emotion, suicide_flag)

    # 📌 Extract & save any new facts
    extracted = extract_facts_with_gpt(user_message)
    for line in extracted.split("\n"):
        line = line.strip("- ").strip()
        if line and line.lower() != "none":
            fact = line.removeprefix("FACT:").strip()
            save_chat_to_memory(fact, session_id, user_id=user_id, emotion=emotion)

    return jsonify({"reply": reply})

# ──────────────────────────────────────────────────────────────────
# Google OAuth endpoints
# ──────────────────────────────────────────────────────────────────
@app.get("/google/auth/<user_id>")
def google_auth(user_id):
    """Redirect browser to Google OAuth consent screen."""
    redirect_uri = url_for("google_callback", _external=True)
    flow = _build_flow(redirect_uri)

    auth_url, _ = flow.authorization_url(
        prompt="consent select_account",
        access_type="offline",
        state=user_id,
    )
    print("DEBUG redirect_uri ➜", redirect_uri, flush=True)

    return redirect(auth_url)


from flask import render_template_string

@app.get("/google/oauth2callback")
def google_callback():
    state = request.args.get("state")                # your temp “vani”
    redirect_uri = url_for("google_callback", _external=True)
    flow = _build_flow(redirect_uri, state=state)
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    cred_json = json.loads(creds.to_json())

    # get the real Gmail address
    try:
        service = build("gmail", "v1", credentials=creds)
        real_email = service.users().getProfile(userId="me").execute().get("emailAddress")
    except Exception as e:
        print(f"❌ Error getting Gmail profile: {e}")
        real_email = state  # fallback to state if we can't get the real email

    # save under both your temp key *and* the real address
    if tokens is not None:
        try:
            tokens.update_one({"user_id": state},
                              {"$set": {"google": cred_json}}, upsert=True)
            if real_email and real_email != state:
                tokens.update_one({"user_id": real_email},
                                  {"$set": {"google": cred_json}}, upsert=True)
        except Exception as e:
            print(f"[ERROR] Failed to save Google credentials: {e}", flush=True)
    else:
        print(f"[WARNING] Cannot save Google credentials - MongoDB not available", flush=True)

    # close the popup
    return render_template_string("""
      <!doctype html>
      <html><head><script>window.close();</script></head>
      <body>✅ Connected! This window will close automatically.</body></html>
    """)


# /agent  – calls run_agent which may invoke tools (Gmail, Calendar…)
# ──────────────────────────────────────────────────────────────────
@app.post("/agent")
def agent_endpoint():
    data = request.get_json(force=True)
    reply = run_agent(
        user_id=data.get("user_id", "demo"),
        message=data["message"],
        history=data.get("history", [])
    )
    return jsonify({"reply": reply})


# ──────────────────────────────────────────────────────────────────
# After google_callback(), add:

@app.route("/api/google-profile", methods=["POST"])
def google_profile():
    """
    Return the Gmail address for a given user_id, if they've already
    completed OAuth.
    """
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
# ------------------------------------------------------------------------------
# /api/sessions-log
# ------------------------------------------------------------------------------
from flask import request, jsonify
from app.chat_embeddings import get_user_facts

@app.route("/api/sessions-log", methods=["POST"])
def sessions_log():
    data    = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "").strip().lower()
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    # Fetch all session IDs
    sessions = conversations.find({"user_id": user_id})
    session_map = {s["session_id"]: s.get("session_name", "") for s in sessions}
    session_list = [
        {"session_id": sid, "name": session_map[sid]}
        for sid in sorted(session_map)
    ]

    # ————————— Load & log memory facts —————————
    memory = get_user_facts(user_id)
    print(f"\n🗄️ Loaded memory for user ‘{user_id}’ ({len(memory)} facts):")
    for i, fact in enumerate(memory, 1):
        print(f"   {i}. {fact}")
    print("")

    return jsonify({
        "sessions": session_list,
        "memory":   memory
    })




# ------------------------------------------------------------------------------
# /api/session_chat
# ------------------------------------------------------------------------------
@app.route("/api/session_chat", methods=["POST"])
def session_chat():
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id")
    session_id = data.get("session_id")

    if conversations is None:
        return jsonify({"chat": []})

    entry = conversations.find_one({"user_id": user_id, "session_id": session_id})
    return jsonify({"chat": entry.get("messages", []) if entry else []})


# ------------------------------------------------------------------------------
# /api/calendar/events
# ------------------------------------------------------------------------------
@app.route("/api/calendar/events", methods=["POST"])
def calendar_events():
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id")
    max_results = data.get("max_results", 10)
    time_min = data.get("time_min")
    time_max = data.get("time_max")

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    try:
        from app.tools.calendar_manager import list_calendar_events
        result = list_calendar_events(
            user_id=user_id,
            max_results=max_results,
            time_min=time_min,
            time_max=time_max
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------------------------------------
# /api/calendar/create
# ------------------------------------------------------------------------------
@app.route("/api/calendar/create", methods=["POST"])
def create_calendar_event():
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
        from app.tools.calendar_manager import create_calendar_event
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


# ------------------------------------------------------------------------------
# /api/save-session-name
# ------------------------------------------------------------------------------
@app.route("/api/save-session-name", methods=["POST"])
def save_session_name():
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id")
    session_id = data.get("session_id")
    name = data.get("name", "")

    if conversations is not None:
        db.conversations.update_one(
            {"user_id": user_id, "session_id": session_id},
            {"$set": {"session_name": name}},
            upsert=True,
        )

    return jsonify({"status": "ok"})


# ------------------------------------------------------------------------------
# /api/test-mongo
# ------------------------------------------------------------------------------
@app.route("/api/test-mongo")
def test_mongo():
    if conversations is not None:
        conversations.insert_one({"msg": "Mongo is working!", "timestamp": datetime.utcnow()})
    return jsonify({"status": "success"})


# ─────────────────────────────────────────────────────────────────────────────
# 1) Kick off the OAuth dance (static path, user_id in state)
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/instagram/auth")
def instagram_auth():
    user_id     = request.args.get("user_id", "demo")
    redirect_uri = url_for("instagram_callback", _external=True)
    oauth = OAuth2Session(IG_APP_ID, redirect_uri=redirect_uri, scope=IG_SCOPES)

    # add auth_type="rerequest" to force a full re‑ask of all scopes
    auth_url, state = oauth.authorization_url(
        OAUTH_BASE,
        auth_type="rerequest",
    )

    session["oauth_state"]   = state
    session["oauth_user_id"] = user_id
    return redirect(auth_url)


# ─────────────────────────────────────────────────────────────────────────────
# 2) Handle the callback (static path)
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/instagram/callback")
def instagram_callback():
    # 2a) Reconstruct state & user_id from session
    state   = session.pop("oauth_state", None)
    user_id = session.pop("oauth_user_id", "demo")
    redirect_uri = url_for("instagram_callback", _external=True)

    oauth = OAuth2Session(
        IG_APP_ID,
        state=state,
        redirect_uri=redirect_uri
    )

    # 2b) Exchange code for user access token
    token = oauth.fetch_token(
        TOKEN_URL,
        client_secret=IG_APP_SECRET,
        authorization_response=request.url,
    )
    user_token = token.get("access_token")
    print("⏺ Facebook returned token:", {k: token.get(k) for k in ("access_token","token_type")})

    # 2c) List pages user manages
    pages_resp = requests.get(
        "https://graph.facebook.com/v19.0/me/accounts",
        params={"access_token": user_token},
        timeout=10,
    ).json()
    print("⏺ pages_resp =", json.dumps(pages_resp, indent=2))

    pages = pages_resp.get("data", [])
    if not pages:
        return "❌ No Facebook Pages found. Make sure you granted the Pages permission.", 400

    # 2d) Find the page that has an instagram_business_account
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
        page_id    = page["id"]
        page_token = page["access_token"]
        ig_user_id = ig_info["id"]

        print(f"⏺ selected page {page_id} with ig_business_id {ig_user_id}")

    # 2e) Fetch the page’s IG Business Account link
    ig_resp = requests.get(
        f"https://graph.facebook.com/v19.0/{page_id}",
        params={
            "fields":       "instagram_business_account",
            "access_token": page_token,
        },
        timeout=10,
    ).json()
    print("⏺ ig_resp =", json.dumps(ig_resp, indent=2))

    ig_info = ig_resp.get("instagram_business_account")
    if not ig_info or not ig_info.get("id"):
        return (
            f"❌ Page {page_id} has no instagram_business_account. "
            "Make sure your IG is a Business/Creator account and linked to this Page."
        ), 400

    ig_user_id = ig_info["id"]

    # 2f) Persist to tokens/{user_id}_ig.pkl
    os.makedirs(TOK_DIR, exist_ok=True)
    with open(f"{TOK_DIR}/{user_id}_ig.pkl", "wb") as f:
        pickle.dump(
            {"page_id": page_id, "ig_user_id": ig_user_id, "access_token": page_token},
            f
        )

    return "✅ Instagram connected! You can close this tab."

from googleapiclient.errors import HttpError

@app.get("/debug/token-info")
def debug_token_info():
    """
    For each user_id in tokens, load their creds and hit Gmail's getProfile
    to see which emailAddress is in use.
    """
    results = []
    for doc in tokens.find({}, {"user_id": 1}):
        uid = doc.get("user_id")
        info = {"user_id": uid, "email_address": None, "error": None}
        creds = load_google_credentials(uid)
        if not creds:
            info["error"] = "no credentials"
        else:
            try:
                service = build("gmail", "v1", credentials=creds)
                profile = service.users().getProfile(userId="me").execute()
                info["email_address"] = profile.get("emailAddress")
            except HttpError as e:
                info["error"] = f"Gmail API error: {e.status_code}"
            except Exception as e:
                info["error"] = str(e)
        results.append(info)
    return jsonify(results)



# ------------------------------------------------------------------------------
# Serve built React frontend
# ------------------------------------------------------------------------------
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    full_path = os.path.join(app.static_folder, path)
    if path and os.path.exists(full_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")


# ------------------------------------------------------------------------------
# Local dev (not used in Gunicorn container runtime)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Parse PORT more safely
    port_str = os.getenv("PORT", "10000")
    try:
        # Extract only the numeric part if there's extra text
        port = int(''.join(filter(str.isdigit, port_str)) or "10000")
    except ValueError:
        port = 10000
    
    print(f"[DEBUG] Starting server on port {port}")
    print(f"[DEBUG] PORT env var: {os.getenv('PORT')}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    