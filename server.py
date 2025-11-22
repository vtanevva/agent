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
import openai

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
from app.utils.db_utils import get_conversations_collection, get_tokens_collection, get_contacts_collection
from app.utils.oauth_utils import (
    load_google_credentials, save_google_credentials, get_gmail_profile,
    require_google_auth, build_google_flow, parse_expo_state,
    GOOGLE_SCOPES, IG_SCOPES, OAUTH_BASE, TOKEN_URL
)
from app.config import Config
from app.autogen_agents.gmail_agent import run_gmail_autogen
from app.tools.gmail_style import analyze_email_style, generate_reply_draft
from app.tools.gmail_reply import reply_email as tool_reply_email
from app.tools.gmail_detail import get_thread_detail
from app.utils.oauth_utils import load_google_credentials
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from app.tools.gmail_mail import send_email as tool_send_email
from email.utils import getaddresses

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

        # Detect features that require Google auth
        calendar_requests = detect_calendar_requests(user_message)
        calendar_keywords = ["calendar", "events", "schedule", "appointments", "meetings"]
        email_keywords = ["emails", "email", "inbox", "reply to"]

        if calendar_requests or any(k in user_message.lower() for k in calendar_keywords + email_keywords):
            auth_response = require_google_auth(user_id)
            if auth_response:
                return auth_response

        # Handle calendar event creation
        if calendar_requests:
            try:
                for calendar_request in calendar_requests:
                    start_time, end_time = parse_datetime_from_text(calendar_request["full_match"])
                    if start_time and end_time:
                        result = create_calendar_event(
                            user_id=user_id,
                            summary=calendar_request["description"],
                            start_time=start_time.isoformat(),
                            end_time=end_time.isoformat(),
                            description=f"Event created from chat: {user_message}",
                        )

                        if result.get("success"):
                            reply = (
                                f"✅ I've scheduled '{calendar_request['description']}' for "
                                f"{start_time.strftime('%B %d at %I:%M %p')}."
                                " You can view it in your calendar!"
                            )
                        else:
                            reply = (
                                "❌ Sorry, I couldn't schedule the event. Please make sure "
                                "you're connected to Google Calendar."
                            )

                        save_message(user_id, session_id, user_message, reply, None, False)
                        return jsonify({"reply": reply})
            except Exception as e:
                reply = f"❌ Error creating calendar event: {str(e)}"
                save_message(user_id, session_id, user_message, reply, None, False)
                return jsonify({"reply": reply})

        # Load session history
        session_memory = []
        conversations = get_conversations_collection()
        if conversations is not None:
            try:
                chat_doc = conversations.find_one({"user_id": user_id, "session_id": session_id})
                if chat_doc and "messages" in chat_doc:
                    for msg in chat_doc["messages"][-20:]:
                        role = "assistant" if msg["role"] == "bot" else msg["role"]
                        # Ensure content is a string for model compatibility
                        text = msg.get("text", "")
                        if not isinstance(text, str):
                            try:
                                text = json.dumps(text, ensure_ascii=False)
                            except Exception:
                                text = str(text)
                        session_memory.append({"role": role, "content": text})
            except Exception as e:
                print(f"[ERROR] Failed to load session history: {e}", flush=True)

        # Feature-specific handling
        if any(k in user_message.lower() for k in calendar_keywords):
            reply = run_agent(user_id=user_id, message=user_message, history=[])
            emotion = None
            suicide_flag = False
        elif any(k in user_message.lower() for k in email_keywords):
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
                session_memory=session_memory,
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


@app.route("/api/autogen/gmail", methods=["POST"])
def autogen_gmail():
    """Invoke the AutoGen-based Gmail agent with a user message."""
    data = request.get_json(force=True, silent=True) or {}
    user_message = (data.get("message") or "").strip()
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    history = data.get("history", [])

    if not user_message:
        return jsonify({"reply": "No message received. Please enter something."}), 400

    # Ensure Google OAuth is connected for Gmail features
    email_keywords = ["emails", "email", "inbox", "reply to", "gmail"]
    if any(k in user_message.lower() for k in email_keywords):
        auth_response = require_google_auth(user_id)
        if auth_response:
            return auth_response

    reply = run_gmail_autogen(user_id=user_id, message=user_message, history=history)
    return jsonify({"reply": reply})

@app.route("/api/gmail/analyze-style", methods=["POST"])
def gmail_analyze_style():
    """Analyze user's email writing style from Sent messages."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    max_samples = int(data.get("max_samples", 10))

    # Ensure Google OAuth
    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = analyze_email_style(user_id=user_id, max_samples=max_samples)
    try:
        return jsonify(json.loads(result))
    except Exception:
        return jsonify({"success": False, "error": "Invalid analyzer output"}), 500

@app.route("/api/gmail/draft-reply", methods=["POST"])
def gmail_draft_reply():
    """Generate a reply draft for a given thread, emulating user's style."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    thread_id = data.get("thread_id")
    to = data.get("to")
    user_points = data.get("user_points") or ""
    max_samples = int(data.get("max_samples", 10))

    if not all([thread_id, to]):
        return jsonify({"success": False, "error": "Missing thread_id or to"}), 400

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = generate_reply_draft(
        user_id=user_id,
        thread_id=thread_id,
        to=to,
        user_points=user_points,
        max_samples=max_samples,
    )
    try:
        return jsonify(json.loads(result))
    except Exception:
        return jsonify({"success": False, "error": "Invalid draft output"}), 500

@app.route("/api/gmail/thread-detail", methods=["POST"])
def gmail_thread_detail():
    """Return full plain-text content and headers for the selected email/thread."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    thread_id = data.get("thread_id")
    if not thread_id:
        return jsonify({"success": False, "error": "Missing thread_id"}), 400

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = get_thread_detail(user_id=user_id, thread_id=thread_id)
    try:
        return jsonify(json.loads(result))
    except Exception:
        return jsonify({"success": False, "error": "Invalid detail output"}), 500

@app.route("/api/gmail/reply", methods=["POST"])
def gmail_reply_send():
    """Send a reply inside a Gmail thread with a provided body."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    thread_id = data.get("thread_id")
    to = data.get("to")
    body = data.get("body") or ""
    subj_prefix = data.get("subj_prefix", "Re:")

    if not all([thread_id, to, body]):
        return jsonify({"success": False, "error": "Missing thread_id, to, or body"}), 400

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    try:
        msg = tool_reply_email(user_id=user_id, thread_id=thread_id, to=to, body=body, subj_prefix=subj_prefix)
        return jsonify({"success": True, "message": msg})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/gmail/archive", methods=["POST"])
def gmail_archive_thread():
    """Archive a Gmail thread by removing it from the INBOX."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    thread_id = data.get("thread_id")
    if not thread_id:
        return jsonify({"success": False, "error": "Missing thread_id"}), 400

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    try:
        creds = load_google_credentials(user_id)
        service = build("gmail", "v1", credentials=creds)

        # If a messageId was provided, resolve to threadId
        try:
            meta = service.users().messages().get(userId="me", id=thread_id, format="minimal").execute()
            real_thread_id = meta.get("threadId", thread_id)
        except HttpError as e:
            if e.resp.status in (400, 404):
                real_thread_id = thread_id
            else:
                raise

        service.users().threads().modify(
            userId="me",
            id=real_thread_id,
            body={"removeLabelIds": ["INBOX"]}
        ).execute()
        return jsonify({"success": True, "thread_id": real_thread_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/gmail/mark-handled", methods=["POST"])
def gmail_mark_handled():
    """Apply a 'Handled' label to a thread and mark it as read."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    thread_id = data.get("thread_id")
    if not thread_id:
        return jsonify({"success": False, "error": "Missing thread_id"}), 400

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    try:
        creds = load_google_credentials(user_id)
        service = build("gmail", "v1", credentials=creds)

        # Ensure label exists (create if missing)
        labels = service.users().labels().list(userId="me").execute().get("labels", [])
        handled_label = next((l for l in labels if l.get("name") == "Handled"), None)
        if not handled_label:
            handled_label = service.users().labels().create(
                userId="me",
                body={
                    "name": "Handled",
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                    "type": "user"
                }
            ).execute()
        handled_label_id = handled_label["id"]

        # If a messageId was provided, resolve to threadId
        try:
            meta = service.users().messages().get(userId="me", id=thread_id, format="minimal").execute()
            real_thread_id = meta.get("threadId", thread_id)
        except HttpError as e:
            if e.resp.status in (400, 404):
                real_thread_id = thread_id
            else:
                raise

        service.users().threads().modify(
            userId="me",
            id=real_thread_id,
            body={"addLabelIds": [handled_label_id], "removeLabelIds": ["UNREAD"]}
        ).execute()
        return jsonify({"success": True, "thread_id": real_thread_id, "label": "Handled"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/gmail/list", methods=["POST"])
def gmail_list_threads():
    """List Gmail threads for a given label (default INBOX)."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    label = (data.get("label") or "INBOX").strip()
    max_results = int(data.get("max_results", 50))

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    try:
        creds = load_google_credentials(user_id)
        service = build("gmail", "v1", credentials=creds)
        resp = service.users().threads().list(
            userId="me",
            labelIds=[label] if label else None,
            maxResults=max_results,
        ).execute()
        threads = resp.get("threads", []) or []
        items = []
        for idx, t in enumerate(threads, start=1):
            th = service.users().threads().get(userId="me", id=t["id"], format="metadata").execute()
            first = th.get("messages", [{}])[0]
            headers = {h["name"]: h["value"] for h in first.get("payload", {}).get("headers", [])}
            items.append({
                "idx": idx,
                "threadId": th.get("id"),
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", "(No subject)"),
                "snippet": first.get("snippet", "")[:200],
                "label": label or "",
            })
            if len(items) >= max_results:
                break
        return jsonify({"success": True, "threads": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/gmail/search", methods=["POST"])
def gmail_search_threads():
    """Search Gmail messages and return unique threads for a query."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    query = (data.get("query") or "").strip()
    max_results = int(data.get("max_results", 20))

    if not query:
        return jsonify({"success": False, "error": "Missing query"}), 400

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    try:
        creds = load_google_credentials(user_id)
        service = build("gmail", "v1", credentials=creds)
        resp = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results * 2,
        ).execute()
        msgs = resp.get("messages", []) or []
        seen = set()
        results = []
        for m in msgs:
            meta = service.users().messages().get(
                userId="me", id=m["id"], format="metadata", metadataHeaders=["Subject", "From"]
            ).execute()
            tid = meta.get("threadId")
            if tid in seen:
                continue
            seen.add(tid)
            headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
            results.append({
                "threadId": tid,
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", "(No subject)"),
                "snippet": meta.get("snippet", "")[:200],
            })
            if len(results) >= max_results:
                break
        return jsonify({"success": True, "threads": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/contacts/sync", methods=["POST"])
def contacts_sync():
    """Initialize or refresh user's contacts from last 100 Sent messages (To: only). Idempotent."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    max_sent = int(data.get("max_sent", 100))
    force = bool(data.get("force", False))

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return jsonify({"success": False, "error": "Database not connected"}), 500

    # If already initialized and not forced, return existing
    if not force:
        existing_count = contacts_col.count_documents({"user_id": user_id})
        if existing_count > 0:
            # Run normalization and grouping pass on existing data (no Gmail fetch)
            existing_docs = list(contacts_col.find({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1, "archived": 1}))
            role_set = {
                "info","hr","support","sales","contact","admin","hello","mail","team",
                "office","careers","jobs","billing","help","service","services","enquiries","inquiries",
                "noreply","no reply","no-reply"
            }
            for d in existing_docs:
                em = (d.get("email") or "").lower()
                nm = (d.get("name") or "").strip()
                needs_norm = (not nm) or (nm.lower() == "(no name)") or (nm.lower() in role_set)
                if not needs_norm and nm:
                    # also normalize if name is actually an email string
                    try:
                        if "@" in nm and "." in nm.split("@",1)[1]:
                            needs_norm = True
                        else:
                            needs_norm = False
                    except Exception:
                        pass
                if needs_norm:
                    new_name = _normalized_display_name(nm, em)
                    if new_name and new_name != nm:
                        contacts_col.update_one(
                            {"user_id": user_id, "email": em},
                            {"$set": {"name": new_name}}
                        )
            # Rebuild groups based on person/company for existing (non-archived) contacts
            docs = list(contacts_col.find({"user_id": user_id, "archived": {"$ne": True}}, {"_id": 0, "email": 1, "name": 1}))
            from collections import defaultdict
            by_person = defaultdict(list)
            by_company = defaultdict(list)
            for d in docs:
                em = d.get("email","")
                nm = d.get("name","")
                person = _canonical_person_name(nm, em)
                if person:
                    by_person[person].append(em)
                comp = _company_from_email(em)
                if comp:
                    by_company[comp].append(em)
            for person, emails in by_person.items():
                if len(emails) >= 2:
                    # Ensure groups is an array for all targeted docs
                    contacts_col.update_many(
                        {"user_id": user_id, "email": {"$in": emails}, "groups": {"$exists": False}},
                        {"$set": {"groups": []}}
                    )
                    contacts_col.update_many(
                        {"user_id": user_id, "email": {"$in": emails}, "groups": {"$type": "object"}},
                        {"$set": {"groups": []}}
                    )
                    contacts_col.update_many(
                        {"user_id": user_id, "email": {"$in": emails}},
                        {"$addToSet": {"groups": person}}
                    )
            for comp, emails in by_company.items():
                if len(emails) >= 2:
                    # Ensure groups is an array for all targeted docs
                    contacts_col.update_many(
                        {"user_id": user_id, "email": {"$in": emails}, "groups": {"$exists": False}},
                        {"$set": {"groups": []}}
                    )
                    contacts_col.update_many(
                        {"user_id": user_id, "email": {"$in": emails}, "groups": {"$type": "object"}},
                        {"$set": {"groups": []}}
                    )
                    contacts_col.update_many(
                        {"user_id": user_id, "email": {"$in": emails}},
                        {"$addToSet": {"groups": comp}}
                    )
            items = list(contacts_col.find({"user_id": user_id}, {"_id": 0}).limit(500))
            return jsonify({"success": True, "initialized": True, "contacts": items})

    try:
        creds = load_google_credentials(user_id)
        svc = build("gmail", "v1", credentials=creds)
        resp = svc.users().messages().list(
            userId="me",
            q="in:sent -from:mailer-daemon@googlemail.com",
            maxResults=max_sent,
        ).execute()
        msgs = resp.get("messages", []) or []

        from datetime import datetime
        seen = {}
        for m in msgs:
            meta = svc.users().messages().get(
                userId="me", id=m["id"], format="metadata", metadataHeaders=["To", "Date"]
            ).execute()
            headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
            tos = headers.get("To", "")
            dt = headers.get("Date", "")
            try:
                last_seen = datetime.utcnow().isoformat()
            except Exception:
                last_seen = datetime.utcnow().isoformat()
            for name, email in getaddresses([tos]):
                email_norm = (email or "").strip().lower()
                if not email_norm:
                    continue
                if email_norm not in seen:
                    seen[email_norm] = {
                        "user_id": user_id,
                        "email": email_norm,
                        "name": (name or ""),
                        "count": 1,
                        "first_seen": last_seen,
                        "last_seen": last_seen,
                    }
                else:
                    seen[email_norm]["count"] += 1
                    seen[email_norm]["last_seen"] = last_seen

        # Upsert into DB
        for email_norm, doc in seen.items():
            contacts_col.update_one(
                {"user_id": user_id, "email": email_norm},
                {
                    "$setOnInsert": {
                        "user_id": user_id,
                        "email": email_norm,
                        "first_seen": doc["first_seen"],
                        "name": _normalized_display_name(doc.get("name") or "", email_norm),
                    },
                    "$set": {
                        "last_seen": doc["last_seen"],
                    },
                    "$inc": {"count": doc["count"]},
                },
                upsert=True,
            )

        # Normalize names for any existing contacts with placeholder or missing names
        needs = list(contacts_col.find(
            {
                "user_id": user_id,
                "$or": [
                    {"name": {"$exists": False}},
                    {"name": ""}, {"name": "(No name)"},
                    {"name": {"$regex": r"^info$", "$options": "i"}}
                ]
            },
            {"_id": 0, "email": 1, "name": 1}
        ))
        for d in needs:
            em = d.get("email", "")
            new_name = _normalized_display_name(d.get("name",""), em)
            if new_name:
                contacts_col.update_one(
                    {"user_id": user_id, "email": em},
                    {"$set": {"name": new_name}}
                )

        # Auto-group by canonical person name and company (clusters with size >= 2)
        docs = list(contacts_col.find({"user_id": user_id, "archived": {"$ne": True}}, {"_id": 0, "email": 1, "name": 1}))
        from collections import defaultdict
        by_person = defaultdict(list)
        by_company = defaultdict(list)
        for d in docs:
            em = d.get("email","")
            nm = d.get("name","")
            person = _canonical_person_name(nm, em)
            if person:
                by_person[person].append(em)
            comp = _company_from_email(em)
            if comp:
                by_company[comp].append(em)
        for person, emails in by_person.items():
            if len(emails) >= 2:
                # Ensure groups is an array for all targeted docs
                contacts_col.update_many(
                    {"user_id": user_id, "email": {"$in": emails}, "groups": {"$exists": False}},
                    {"$set": {"groups": []}}
                )
                contacts_col.update_many(
                    {"user_id": user_id, "email": {"$in": emails}, "groups": {"$type": "object"}},
                    {"$set": {"groups": []}}
                )
                contacts_col.update_many(
                    {"user_id": user_id, "email": {"$in": emails}},
                    {"$addToSet": {"groups": person}}
                )
        for comp, emails in by_company.items():
            if len(emails) >= 2:
                # Ensure groups is an array for all targeted docs
                contacts_col.update_many(
                    {"user_id": user_id, "email": {"$in": emails}, "groups": {"$exists": False}},
                    {"$set": {"groups": []}}
                )
                contacts_col.update_many(
                    {"user_id": user_id, "email": {"$in": emails}, "groups": {"$type": "object"}},
                    {"$set": {"groups": []}}
                )
                contacts_col.update_many(
                    {"user_id": user_id, "email": {"$in": emails}},
                    {"$addToSet": {"groups": comp}}
                )

        items = list(contacts_col.find({"user_id": user_id}, {"_id": 0}).limit(500))
        return jsonify({"success": True, "initialized": True, "contacts": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/contacts/list", methods=["POST"])
def contacts_list():
    """List stored contacts for a user."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    include_archived = bool(data.get("include_archived", False))

    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return jsonify({"success": False, "error": "Database not connected"}), 500

    query = {"user_id": user_id}
    if not include_archived:
        query["archived"] = {"$ne": True}
    docs = list(contacts_col.find(query, {"_id": 0}).sort([("last_seen", -1), ("count", -1)]).limit(2000))
    # Merge duplicates by email (case-insensitive) and normalize groups to lower-case unique
    merged = {}
    for d in docs:
        email = (d.get("email") or "").lower()
        if not email:
            continue
        # normalize groups to lower-case unique list of strings
        grps = []
        for g in d.get("groups", []) or []:
            if isinstance(g, str):
                key = g.strip().lower()
                if key and key not in grps:
                    grps.append(key)
        name = d.get("name")
        entry = merged.get(email)
        if not entry:
            nd = dict(d)
            nd["email"] = email
            nd["groups"] = grps
            nd["name"] = name or ""
            merged[email] = nd
        else:
            # merge counts and timestamps
            try:
                entry["count"] = entry.get("count", 0) + int(d.get("count", 0))
            except Exception:
                pass
            ls = d.get("last_seen")
            if ls and (not entry.get("last_seen") or str(ls) > str(entry.get("last_seen"))):
                entry["last_seen"] = ls
            fs = d.get("first_seen")
            if fs and (not entry.get("first_seen") or str(fs) < str(entry.get("first_seen"))):
                entry["first_seen"] = fs
            # prefer longer non-empty name
            if name and (not entry.get("name") or len(name) > len(entry.get("name"))):
                entry["name"] = name
            # union groups (already normalized)
            for g in grps:
                if g not in entry["groups"]:
                    entry["groups"].append(g)
    return jsonify({"success": True, "contacts": list(merged.values())})


def _name_from_email(email: str) -> str:
    """Guess a human name from an email local-part."""
    try:
        local = (email or "").split("@", 1)[0]
        # strip +tag
        local = local.split("+", 1)[0]
        import re
        parts = re.split(r"[._\-]+", local)
        parts = [p for p in parts if p and p.isalpha()]
        if not parts:
            return ""
        # common no-name words to skip
        blacklist = {"info", "contact", "sales", "support", "hello", "mail", "team", "admin"}
        parts = [p for p in parts if p.lower() not in blacklist] or parts
        # Title Case
        return " ".join(w[:1].upper() + w[1:].lower() for w in parts[:3])
    except Exception:
        return ""

def _canonical_person_name(current_name: str, email: str) -> str:
    """
    Compute a canonical person name (no company suffix, not a role mailbox).
    Used for grouping same-person contacts across multiple emails.
    """
    base = (current_name or "").strip()
    if not base or base.lower() == "(no name)":
        base = _name_from_email(email) or ""
    # If base appears with a suffix ' - Company', strip it
    if " - " in base:
        base = base.split(" - ", 1)[0].strip()
    # Drop if role mailbox
    role_set = {
        "info","hr","support","sales","contact","admin","hello","mail","team",
        "office","careers","jobs","billing","help","service","services","enquiries","inquiries",
        "noreply","no reply","no-reply"
    }
    if base.lower() in role_set:
        return ""
    # Normalize spacing/case
    parts = [p for p in base.replace("_"," ").replace("."," ").split() if p]
    if not parts:
        return ""
    return " ".join(w[:1].upper() + w[1:].lower() for w in parts[:4])
def _company_from_email(email: str) -> str:
    """Extract a plausible company name from email domain; ignore public providers."""
    try:
        domain = (email or "").split("@", 1)[1].lower()
    except Exception:
        return ""
    public = {
        "gmail.com","googlemail.com","yahoo.com","yahoo.co.uk","outlook.com","hotmail.com","live.com",
        "msn.com","icloud.com","me.com","protonmail.com","zoho.com","gmx.com","aol.com","pm.me"
    }
    if domain in public:
        return ""
    parts = domain.split(".")
    core = parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")
    if not core:
        return ""
    # avoid technical subdomains if accidentally chosen
    if core in {"mail","mx","smtp","pop","imap","cpanel","webmail","ns"} and len(parts) >= 3:
        core = parts[-3]
    if not core:
        return ""
    return core[:1].upper() + core[1:].lower()

def _looks_like_email(text: str) -> bool:
    """Heuristic to detect if a given name string is actually an email."""
    if not text or "@" not in text:
        return False
    # very loose check: has one '@' and at least one dot after
    try:
        local, domain = text.split("@", 1)
        return bool(local) and "." in domain
    except Exception:
        return False

def _normalized_display_name(current_name: str, email: str) -> str:
    """
    Build display name using rules:
    - If current_name is missing/empty/'(No name)', derive from local-part.
    - If the base name is a generic role (info/hr/support/...), append company: 'Company - role'.
    - If the base name itself looks like an email, derive Name from email and use 'Name - Company' when company exists.
    - Otherwise keep the base name as-is (do NOT append company).
    """
    base = (current_name or "").strip()
    if not base or base.lower() == "(no name)":
        base = _name_from_email(email) or ""
    company = _company_from_email(email)
    if not base:
        # If we cannot derive a base, fall back to company alone
        return company or ""
    # If the provided name is actually an email string, promote to 'Name - Company'
    if _looks_like_email(base):
        derived = _name_from_email(email)
        if company and derived:
            return f"{derived} - {company}"
        return derived or base
    # Decide if base is a generic role mailbox
    role_set = {
        "info","hr","support","sales","contact","admin","hello","mail","team",
        "office","careers","jobs","billing","help","service","services","enquiries","inquiries",
        "noreply","no reply","no-reply"
    }
    base_l = base.lower()
    if base_l in role_set:
        # Format role nicely: HR uppercased; others lower-case
        display_role = "HR" if base_l == "hr" else base_l.replace("no reply", "no-reply")
        return (f"{company} - {display_role}" if company else display_role)
    # Non-generic personal-looking name: keep as-is, no company suffix
    return base

@app.route("/api/contacts/normalize-names", methods=["POST"])
def contacts_normalize_names():
    """Fill missing names from email local-part for a user's contacts."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()

    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return jsonify({"success": False, "error": "Database not connected"}), 500

    docs = list(contacts_col.find(
        {
            "user_id": user_id,
            "$or": [
                {"name": {"$exists": False}},
                {"name": ""}, {"name": "(No name)"},
                {"name": {"$regex": r"^info$", "$options": "i"}}
            ]
        },
        {"_id": 0, "email": 1, "name": 1}
    ))
    updated = 0
    for d in docs:
        email = d.get("email", "")
        new_name = _normalized_display_name(d.get("name",""), email)
        if new_name:
            contacts_col.update_one({"user_id": user_id, "email": email}, {"$set": {"name": new_name}})
            updated += 1
    return jsonify({"success": True, "updated": updated})


@app.route("/api/contacts/archive", methods=["POST"])
def contacts_archive():
    """Archive or unarchive a contact."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    email = (data.get("email") or "").strip().lower()
    archived = bool(data.get("archived", True))

    if not email:
        return jsonify({"success": False, "error": "Missing email"}), 400

    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return jsonify({"success": False, "error": "Database not connected"}), 500

    from datetime import datetime
    contacts_col.update_one(
        {"user_id": user_id, "email": email},
        {"$set": {"archived": archived, "archived_at": datetime.utcnow().isoformat() if archived else None}},
        upsert=False,
    )
    return jsonify({"success": True, "email": email, "archived": archived})


@app.route("/api/contacts/update", methods=["POST"])
def contacts_update():
    """Update contact fields: name, nickname, groups (array of strings)."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    email = (data.get("email") or "").strip().lower()
    name = data.get("name")
    nickname = data.get("nickname")
    groups = data.get("groups")

    if not email:
        return jsonify({"success": False, "error": "Missing email"}), 400

    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return jsonify({"success": False, "error": "Database not connected"}), 500

    update_doc = {}
    if name is not None:
        update_doc["name"] = name
    if nickname is not None:
        update_doc["nickname"] = nickname
    if groups is not None:
        # normalize groups to unique list of lowercase strings
        try:
            norm = []
            for g in groups:
                s = (g or "").strip()
                if not s:
                    continue
                if s.lower() not in [x.lower() for x in norm]:
                    norm.append(s)
            update_doc["groups"] = norm
        except Exception:
            update_doc["groups"] = []

    if not update_doc:
        return jsonify({"success": False, "error": "No fields to update"}), 400

    contacts_col.update_one(
        {"user_id": user_id, "email": email},
        {"$set": update_doc},
        upsert=False,
    )
    doc = contacts_col.find_one({"user_id": user_id, "email": email}, {"_id": 0})
    return jsonify({"success": True, "contact": doc})


@app.route("/api/contacts/groups", methods=["POST"])
def contacts_groups():
    """Return distinct groups for a user's contacts."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()

    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return jsonify({"success": False, "error": "Database not connected"}), 500

    pipeline = [
        {"$match": {"user_id": user_id, "archived": {"$ne": True}}},
        # Ensure groups is an array (if not present or wrong type -> empty array)
        {"$project": {
            "groups": {
                "$cond": [
                    {"$isArray": "$groups"},
                    "$groups",
                    []
                ]
            }
        }},
        {"$unwind": {"path": "$groups", "preserveNullAndEmptyArrays": False}},
        # Only keep string values for groups
        {"$match": {"groups": {"$type": "string"}}},
        {"$group": {"_id": {"$toLower": "$groups"}}},
        {"$sort": {"_id": 1}},
    ]
    groups = [d["_id"] for d in contacts_col.aggregate(pipeline)]
    return jsonify({"success": True, "groups": groups})


@app.route("/api/gmail/send", methods=["POST"])
def gmail_send_new():
    """Send a new email (compose)."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    to = data.get("to")
    subject = data.get("subject") or "(No subject)"
    body = data.get("body") or ""

    if not to or not body:
        return jsonify({"success": False, "error": "Missing 'to' or 'body'"}), 400

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    try:
        msg = tool_send_email(user_id=user_id, to=to, subject=subject, body=body)
        return jsonify({"success": True, "message": msg})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/gmail/rewrite", methods=["POST"])
def gmail_rewrite_text():
    """Rewrite a user-provided text more politely/clearly, optionally using user's style and appending a signature.
    Also optionally generate a concise subject line.
    """
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    text = (data.get("text") or "").strip()
    tone = (data.get("tone") or "polite and professional").strip()
    include_signature = bool(data.get("include_signature", False))
    signature_text = (data.get("signature") or "").strip()
    generate_subject = bool(data.get("generate_subject", True))

    if not text:
        return jsonify({"success": False, "error": "Missing 'text'"}), 400

    try:
        # Try to leverage user's style profile if available
        try:
            style_json = analyze_email_style(user_id=user_id, max_samples=5)
        except Exception:
            style_json = "{}"

        # Ask model to return strict JSON for easy parsing
        instructions = [
            f"Rewrite the following email body in a concise, {tone} tone.",
            "Keep the meaning, fix grammar, and avoid over-formality.",
            "Use proper email paragraphing with a blank line between paragraphs.",
        ]
        if include_signature and signature_text:
            instructions.append(
                "Append the following closing signature at the end, separated by one blank line, "
                "replacing any existing signature:"
            )
        else:
            instructions.append("Do not add a closing signature.")
        if generate_subject:
            instructions.append("Propose a concise subject (3-8 words).")
        else:
            instructions.append("Do not propose a subject.")
        instructions.append(
            "Return a JSON object ONLY with keys: subject (string, may be empty) and body (string). "
            "No markdown, no extra commentary."
        )

        prompt = "\n".join(instructions) + "\n\n" + \
                 f"User style profile (JSON, optional):\n{style_json}\n\n" + \
                 ("Signature to use:\n" + signature_text + "\n\n" if include_signature and signature_text else "") + \
                 "Email body:\n" + text

        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        resp = openai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a careful email rewriting assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        content = (resp.choices[0].message.content or "").strip()
        # Best-effort JSON parse
        import json as _json, re as _re
        clean = content.strip().strip("`")
        # remove ```json fences if present
        clean = _re.sub(r"^```json\s*|\s*```$", "", clean, flags=_re.IGNORECASE | _re.MULTILINE).strip()
        subject = ""
        body = content
        try:
            parsed = _json.loads(clean)
            subject = (parsed.get("subject") or "").strip()
            body = (parsed.get("body") or "").rstrip()
        except Exception:
            # Fallback: use entire content as body
            subject = ""
            body = content
        return jsonify({"success": True, "rewritten": body, "subject": subject})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
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

    