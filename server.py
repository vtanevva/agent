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
# agent_core removed - calendar now uses CalendarAgent
# from app.agent_core.agent import run_agent
# from app.agent_core.tool_registry import all_openai_schemas
from app.services.memory_service import get_memory_service
from app.services.llm_service import get_llm_service
from app.database import init_database, get_db
# Old orchestrator imports - now handled by agents/orchestrator.py
# from app.orchestrator.aivis_orchestrator import handle_chat, detect_intent
# from app.orchestrator.session_memory import load_session_memory
from app.services.gmail_service import (
    get_thread_detail as gmail_get_thread_detail,
    reply_to_thread as gmail_reply_to_thread,
    archive_thread as gmail_archive_thread,
    mark_thread_handled as gmail_mark_handled,
    list_threads as gmail_list_threads_service,
    search_threads as gmail_search_threads_service,
    classify_single_email as gmail_classify_single_email,
    triaged_inbox as gmail_triaged_inbox_service,
    classify_background as gmail_classify_background_service,
    send_new_email as gmail_send_new_email,
    rewrite_email_text as gmail_rewrite_email_text,
)
from app.tools.contacts import (
    sync_contacts,
    list_contacts,
    normalize_contact_names,
    archive_contact,
    update_contact,
    list_contact_groups,
    get_contact_detail,
    get_contact_conversations,
)
# Calendar tools moved to app/api/calendar_routes.py
from app.db.collections import get_conversations_collection, get_tokens_collection, get_contacts_collection
from app.utils.oauth_utils import (
    load_google_credentials, save_google_credentials, get_gmail_profile,
    require_google_auth, build_google_flow, parse_expo_state,
    GOOGLE_SCOPES, IG_SCOPES, OAUTH_BASE, TOKEN_URL
)
from app.config import Config
# Old AutoGen import removed - now using new GmailAgent via orchestrator
# from app.agents.gmail_agent import run_gmail_autogen
from app.tools.email import (
    analyze_email_style,
    generate_reply_draft,
    reply_email as tool_reply_email,
    get_thread_detail,
    classify_email,
    send_email as tool_send_email,
)
from app.utils.oauth_utils import load_google_credentials
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from email.utils import getaddresses

# Import new blueprints
from app.api.chat_routes import chat_bp
from app.api.gmail_routes import gmail_bp
from app.api.contacts_routes import contacts_bp
from app.api.calendar_routes import calendar_bp

# Environment setup
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()


def create_app():
    """
    Application factory pattern for Flask app.
    
    This creates and configures the Flask application with all necessary
    blueprints, extensions, and middleware.
    """
    app = Flask(__name__, static_folder="my-chatbot/build", static_url_path="")
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
    app.secret_key = Config.FLASK_SECRET_KEY or "change-me-in-prod"

    # Initialize database
    db_connected = init_database()
    if db_connected:
        print("[INIT] ✅ MongoDB connected successfully")
    else:
        print("[INIT] ⚠️ MongoDB not connected - running in offline mode")

    # Tool registry removed - agents call functions directly now
    # available_tools = [tool['function']['name'] for tool in all_openai_schemas()]
    # print(f"[INIT] Available tools: {available_tools}")
    
    # Register new blueprints (Phase 1)
    app.register_blueprint(chat_bp)
    app.register_blueprint(gmail_bp)
    app.register_blueprint(contacts_bp)
    app.register_blueprint(calendar_bp)
    
    print("[INIT] ✅ Registered API blueprints: chat, gmail, contacts, calendar")
    
    return app


# Create the app instance
app = create_app()

# Instagram OAuth config (these are used by routes below)
IG_APP_ID = Config.IG_APP_ID
IG_APP_SECRET = Config.IG_APP_SECRET


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
    
    # Extract and store contact notes in background
    try:
        _extract_contact_notes(user_id, user_message, bot_reply)
    except Exception as e:
        print(f"[ERROR] Failed to extract contact notes: {e}", flush=True)


def _extract_contact_notes(user_id: str, user_message: str, bot_reply: str):
    """Extract contact-related information from conversation and store as notes."""
    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return
    
    # Get all contacts for this user
    contacts = list(contacts_col.find({"user_id": user_id}, {"email": 1, "name": 1, "nickname": 1}))
    if not contacts:
        return
    
    # Check if conversation mentions any contacts
    conversation_text = f"{user_message} {bot_reply}".lower()
    mentioned_contacts = []
    
    for contact in contacts:
        email = (contact.get("email") or "").lower()
        name = (contact.get("name") or "").lower()
        nickname = (contact.get("nickname") or "").lower()
        
        # Check if contact is mentioned
        if email and email in conversation_text:
            mentioned_contacts.append(contact)
        elif name and name in conversation_text:
            mentioned_contacts.append(contact)
        elif nickname and nickname in conversation_text:
            mentioned_contacts.append(contact)
    
    if not mentioned_contacts:
        return
    
    # Extract notes for each mentioned contact
    for contact in mentioned_contacts:
        try:
            email = contact.get("email", "")
            contact_name = contact.get("name", "")
            contact_nickname = contact.get("nickname", "")
            
            # Build prompt to extract contact-specific information
            prompt = f"""Extract and summarize any relevant information about this contact from the conversation.
Contact: {contact_name or email} {f'("{contact_nickname}")' if contact_nickname else ''}
Email: {email}

Conversation:
User: {user_message}
Assistant: {bot_reply}

Extract any:
- Personal details mentioned (work, interests, preferences, etc.)
- Relationship context
- Important facts or events
- Communication style or preferences

Return a concise summary (2-3 sentences) or "None" if nothing relevant was mentioned.
Summary:"""
            
            # Use OpenAI to extract notes
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a contact information extractor. Extract relevant information about contacts from conversations."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=150,
                temperature=0.3,
            )
            
            extracted_note = response.choices[0].message.content.strip()
            
            # Skip if no relevant information
            if not extracted_note or extracted_note.lower() == "none" or len(extracted_note) < 10:
                continue
            
            # Get existing notes
            existing_contact = contacts_col.find_one({"user_id": user_id, "email": email})
            existing_notes = existing_contact.get("notes", "") if existing_contact else ""
            
            # Combine with existing notes (keep last 5 notes to avoid bloat)
            if existing_notes:
                # Split existing notes by newlines or periods to get individual notes
                notes_list = [n.strip() for n in existing_notes.split("\n\n") if n.strip()]
                notes_list.append(f"[{datetime.utcnow().strftime('%Y-%m-%d')}] {extracted_note}")
                # Keep only last 5 notes
                notes_list = notes_list[-5:]
                updated_notes = "\n\n".join(notes_list)
            else:
                updated_notes = f"[{datetime.utcnow().strftime('%Y-%m-%d')}] {extracted_note}"
            
            # Update contact with new notes
            contacts_col.update_one(
                {"user_id": user_id, "email": email},
                {"$set": {"notes": updated_notes, "notes_updated_at": datetime.utcnow().isoformat()}},
            )
            
        except Exception as e:
            print(f"[ERROR] Failed to extract notes for contact {contact.get('email')}: {e}", flush=True)
            continue


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


# OLD /api/chat endpoint - now handled by app/api/chat_routes.py blueprint
# This is kept here temporarily for reference during Phase 1
# @app.route("/api/chat", methods=["POST"])
# def chat():
#     """Main chat endpoint that handles user messages."""
#     ...
# (Code moved to app/api/chat_routes.py)


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
    """
    DEPRECATED: Old AutoGen-based Gmail agent route.
    
    This route is kept for backward compatibility but now redirects to the new
    /api/chat endpoint which uses the new agent architecture.
    """
    data = request.get_json(force=True, silent=True) or {}
    user_message = (data.get("message") or "").strip()
    user_id = (data.get("user_id") or "anonymous").strip().lower()

    if not user_message:
        return jsonify({"reply": "No message received. Please enter something."}), 400

    # Redirect to new chat endpoint
    from app.agents.orchestrator import get_orchestrator
    
    try:
        orchestrator = get_orchestrator()
        intent, reply = orchestrator.handle_chat(
            user_id=user_id,
            session_id=f"{user_id}-autogen",
            user_message=user_message,
        )
        return jsonify({"reply": reply})
    except Exception as e:
        print(f"[ERROR] Error in autogen_gmail: {e}", flush=True)
        return jsonify({"error": "Failed to process request", "message": str(e)}), 500

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

    result = gmail_get_thread_detail(user_id=user_id, thread_id=thread_id)
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status

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

    result = gmail_reply_to_thread(
        user_id=user_id,
        thread_id=thread_id,
        to=to,
        body=body,
        subj_prefix=subj_prefix,
    )
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


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

    result = gmail_archive_thread(user_id=user_id, thread_id=thread_id)
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


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

    result = gmail_mark_handled(user_id=user_id, thread_id=thread_id)
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


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

    result = gmail_list_threads_service(user_id=user_id, label=label, max_results=max_results)
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


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

    result = gmail_search_threads_service(user_id=user_id, query=query, max_results=max_results)
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@app.route("/api/gmail/classify-email", methods=["POST"])
def gmail_classify_email():
    """Classify a single email using the Smart Inbox Triage system."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    
    # Email data can come from request or be fetched by thread_id
    thread_id = data.get("thread_id")
    email_data = data.get("email", {})
    
    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response
    
    # Delegate to service; it handles fetching by thread_id when needed.
    result = gmail_classify_single_email(user_id=user_id, thread_id=thread_id, email_data=email_data or None)
    # Keep 400 response if request was structurally invalid
    if not result.get("success") and result.get("error") == "Missing email data or thread_id":
        return jsonify(result), 400
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@app.route("/api/gmail/triaged-inbox", methods=["POST"])
def gmail_triaged_inbox():
    """Get triaged inbox with emails categorized by priority. Returns cached data immediately, classifies new emails in background."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    max_results = int(data.get("max_results", 50))
    category_filter = data.get("category")  # Optional: filter by specific category

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = gmail_triaged_inbox_service(
        user_id=user_id,
        max_results=max_results,
        category_filter=category_filter,
    )
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@app.route("/api/gmail/classify-background", methods=["POST"])
def gmail_classify_background():
    """Trigger background classification for unclassified emails. Returns immediately."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    max_emails = int(data.get("max_emails", 20))

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = gmail_classify_background_service(user_id=user_id, max_emails=max_emails)
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@app.route("/api/contacts/sync", methods=["POST"])
def contacts_sync():
    """Initialize or refresh user's contacts from last 100 Sent messages (To: only). Idempotent."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    max_sent = int(data.get("max_sent", 1000))
    force = bool(data.get("force", False))

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result_json = sync_contacts(user_id=user_id, max_sent=max_sent, force=force)
    result = json.loads(result_json)
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@app.route("/api/contacts/list", methods=["POST"])
def contacts_list():
    """List stored contacts for a user."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    include_archived = bool(data.get("include_archived", False))

    result_json = list_contacts(user_id=user_id, include_archived=include_archived)
    result = json.loads(result_json)
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


def _generate_nickname(name: str, email: str = None) -> str:
    """Generate a nickname from a full name. Format: 'First Name - Company' if company exists, else just first name."""
    if not name or name.lower() == "(no name)":
        return ""
    
    name = name.strip()
    parts = name.split()
    
    if len(parts) == 0:
        return ""
    
    # Extract first name
    first_name = parts[0]
    
    # Check if name already contains company (format: "Name - Company")
    if " - " in name:
        # Already has company format, use as is
        return name
    
    # Try to extract company from email domain
    company = None
    if email:
        company = _company_from_email(email)
    
    # Build nickname: "First Name - Company" or just "First Name"
    if company:
        nickname = f"{first_name} - {company}"
        return nickname[:50]  # Cap at 50 chars
    else:
        return first_name


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

def _category_groups_for_email(email: str):
    """
    Heuristic category groups based on email domain.
    Returns a list of lower-case category names like ['travel','food','events','housing'].
    """
    try:
        domain = (email or "").split("@", 1)[1].lower()
    except Exception:
        return []
    cats = set()
    travel_keys = {
        "airbnb","booking","expedia","kayak","skyscanner","tripadvisor","trivago","agoda","hostelworld",
        "uber","lyft","bolt","blablacar","ryanair","easyjet","delta","united","american","lufthansa",
        "wizzair","aircanada","britishairways","emirates","qatarairways","airasia","sbb","bahn","amtrak"
    }
    food_keys = {
        "ubereats","doordash","deliveroo","justeat","grubhub","postmates","wolt","glovo","foodpanda",
        "deliveryhero","dominos","pizzahut","mcdonalds","burgerking","kfc","chipotle","boltfood"
    }
    event_keys = {
        "eventbrite","ticketmaster","tickets","eventim","meetup","dice","ticketek","universe",
        "skiddle","festicket","axs","billetto","eventzilla","splashthat","bizzabo"
    }
    housing_keys = {
        "zillow","realtor","trulia","redfin","apartments","apartmentlist","rent","rentals",
        "rightmove","zoopla","spareroom","roomster","nestoria","idealista","fotocasa",
        "immobilienscout","immowelt","immobiliare","leboncoin","seloger","funda","bolig",
        "booking","airbnb","vrbo","homeaway","bookingcom","hostelworld","hostelbookers"
    }
    toks = [t for t in domain.replace('.', ' ').replace('-', ' ').split() if t]
    lower_join = ' '.join(toks)
    if any(k in domain for k in travel_keys) or any(k in lower_join for k in {"travel","flight","hotel","hostel","train","bus","ferry"}):
        cats.add("travel")
    if any(k in domain for k in food_keys) or any(k in lower_join for k in {"eat","food","pizza","burger","kebab","sushi","delivery","cafe","restaurant"}):
        cats.add("food")
    if any(k in domain for k in event_keys) or any(k in lower_join for k in {"event","ticket","festival","conference","meetup"}):
        cats.add("events")
    if any(k in domain for k in housing_keys) or any(k in lower_join for k in {"housing","rent","rental","apartment","flat","house","property","realestate","real estate","accommodation","room","rooms","landlord","tenant"}):
        cats.add("housing")
    return list(cats)

@app.route("/api/contacts/normalize-names", methods=["POST"])
def contacts_normalize_names():
    """Fill missing names from email local-part for a user's contacts."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()

    result_json = normalize_contact_names(user_id=user_id)
    result = json.loads(result_json)
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@app.route("/api/contacts/archive", methods=["POST"])
def contacts_archive():
    """Archive or unarchive a contact."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    email = (data.get("email") or "").strip().lower()
    archived = bool(data.get("archived", True))

    if not email:
        return jsonify({"success": False, "error": "Missing email"}), 400

    result_json = archive_contact(user_id=user_id, email=email, archived=archived)
    result = json.loads(result_json)
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


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

    result_json = update_contact(
        user_id=user_id,
        email=email,
        name=name,
        nickname=nickname,
        groups=groups,
    )
    result = json.loads(result_json)
    if not result.get("success") and result.get("error") == "No fields to update":
        return jsonify(result), 400
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@app.route("/api/contacts/groups", methods=["POST"])
def contacts_groups():
    """Return distinct groups for a user's contacts."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()

    result_json = list_contact_groups(user_id=user_id)
    result = json.loads(result_json)
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@app.route("/api/contacts/detail", methods=["POST"])
def contacts_detail():
    """Get detailed contact information including notes, last interaction, and past conversations."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"success": False, "error": "Missing email"}), 400

    result_json = get_contact_detail(user_id=user_id, email=email)
    result = json.loads(result_json)
    if not result.get("success") and result.get("error") == "Contact not found":
        return jsonify(result), 404
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@app.route("/api/contacts/conversations", methods=["POST"])
def contacts_conversations():
    """Get all conversations related to a specific contact."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get("user_id") or "anonymous").strip().lower()
    email = (data.get("email") or "").strip().lower()
    limit = int(data.get("limit", 20))

    if not email:
        return jsonify({"success": False, "error": "Missing email"}), 400

    result_json = get_contact_conversations(user_id=user_id, email=email, max_results=limit)
    result = json.loads(result_json)
    if not result.get("success") and result.get("error") == "Contact not found":
        return jsonify(result), 404
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


def _lookup_contact_email(user_id: str, name_or_email: str) -> str:
    """Look up email address from contacts by name or return the input if it's already an email.
    Prioritizes exact matches over partial matches."""
    if not name_or_email or "@" in name_or_email:
        return name_or_email  # Already an email or empty
    
    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return name_or_email
    
    name_lower = name_or_email.strip().lower()
    
    # 1. Try exact match first (name or nickname exactly equals the search term)
    contact = contacts_col.find_one(
        {
            "user_id": user_id,
            "$or": [
                {"name": {"$regex": f"^{name_lower}$", "$options": "i"}},
                {"nickname": {"$regex": f"^{name_lower}$", "$options": "i"}},
            ]
        },
        {"email": 1}
    )
    if contact:
        return contact.get("email", name_or_email)
    
    # 2. Try word boundary match (whole word, not substring) - prevents "marin" matching "marina"
    contact = contacts_col.find_one(
        {
            "user_id": user_id,
            "$or": [
                {"name": {"$regex": f"\\b{name_lower}\\b", "$options": "i"}},
                {"nickname": {"$regex": f"\\b{name_lower}\\b", "$options": "i"}},
            ]
        },
        {"email": 1}
    )
    if contact:
        return contact.get("email", name_or_email)
    
    # 3. Last resort: partial match (only if name starts with the search term)
    contact = contacts_col.find_one(
        {
            "user_id": user_id,
            "$or": [
                {"name": {"$regex": f"^{name_lower}", "$options": "i"}},
                {"nickname": {"$regex": f"^{name_lower}", "$options": "i"}},
            ]
        },
        {"email": 1}
    )
    if contact:
        return contact.get("email", name_or_email)
    
    return name_or_email  # Not found, return original


def _lookup_contact_emails(user_id: str, name: str) -> list:
    """Look up all email addresses for a contact by name. Returns list of email strings.
    Supports two modes:
    - "Marin" → matches all contacts with first name "Marin" (across all companies)
    - "Marin Fontys" or "Marin - Fontys" → matches only "Marin" at "Fontys" company
    """
    if not name or "@" in name:
        return [name] if name else []  # Already an email or empty
    
    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return []
    
    name_lower = name.strip().lower()
    emails = []
    
    # Parse query to detect if it contains company info
    # Check for " - " separator or multiple words (likely "First Company")
    has_company = False
    first_name = name_lower
    company_name = None
    
    if " - " in name_lower:
        # Format: "Marin - Fontys"
        parts = name_lower.split(" - ", 1)
        first_name = parts[0].strip()
        company_name = parts[1].strip() if len(parts) > 1 else None
        has_company = bool(company_name)
    else:
        # Check if multiple words (likely "Marin Fontys")
        words = name_lower.split()
        if len(words) >= 2:
            # Assume first word is first name, rest is company
            first_name = words[0]
            company_name = " ".join(words[1:])
            has_company = True
    
    # Build query based on whether company is specified
    if has_company and company_name:
        # Match by first name AND company
        # Try exact nickname match first (format: "First - Company")
        exact_nickname = f"{first_name} - {company_name}"
        exact_contacts = contacts_col.find(
            {
                "user_id": user_id,
                "nickname": {"$regex": f"^{exact_nickname}$", "$options": "i"}
            },
            {"email": 1}
        )
        
        for contact in exact_contacts:
            email = contact.get("email")
            if email and email not in emails:
                emails.append(email)
        
        if emails:
            return emails
        
        # Try matching name starting with first name AND company in email domain or groups
        all_contacts = contacts_col.find(
            {
                "user_id": user_id,
                "$or": [
                    {"name": {"$regex": f"^{first_name}", "$options": "i"}},
                    {"nickname": {"$regex": f"^{first_name}", "$options": "i"}},
                ]
            },
            {"email": 1, "name": 1, "groups": 1}
        )
        
        # Filter by company
        for contact in all_contacts:
            email = contact.get("email", "")
            # Check if company matches email domain or groups
            company_match = False
            if email:
                # Extract company from email domain
                try:
                    domain = email.split("@", 1)[1].lower()
                    domain_parts = domain.split(".")
                    domain_company = domain_parts[-2] if len(domain_parts) >= 2 else ""
                    if company_name.lower() in domain_company.lower() or domain_company.lower() in company_name.lower():
                        company_match = True
                except:
                    pass
            
            # Check groups
            if not company_match:
                groups = contact.get("groups", [])
                for g in groups:
                    if isinstance(g, str) and company_name.lower() in g.lower():
                        company_match = True
                        break
            
            if company_match:
                if email and email not in emails:
                    emails.append(email)
        
        return emails
    else:
        # No company specified - match all contacts with this first name
        # Try exact first name match in nickname (format: "First - Company" or just "First")
        first_name_regex = f"^{first_name}( - |$)"
        contacts = contacts_col.find(
            {
                "user_id": user_id,
                "$or": [
                    {"name": {"$regex": f"^{first_name}\\b", "$options": "i"}},
                    {"nickname": {"$regex": first_name_regex, "$options": "i"}},
                ]
            },
            {"email": 1}
        )
        
        for contact in contacts:
            email = contact.get("email")
            if email and email not in emails:
                emails.append(email)
        
        return emails


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

    # Look up contact if needed
    to = _lookup_contact_email(user_id, to)

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

    # Get user facts from MemoryService
    memory_service = get_memory_service()
    memory_facts = memory_service.retrieve_facts(user_id=user_id, limit=200)
    
    # Convert to old format for backward compatibility
    memory = [{"text": fact} for fact in memory_facts]
    
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


# Calendar routes moved to app/api/calendar_routes.py


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

    