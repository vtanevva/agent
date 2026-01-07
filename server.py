"""Main Flask server for the mental health AI assistant"""

import sys
import os
import json
import uuid
import pickle
import random
import string
from datetime import datetime
from urllib.parse import urlparse

# Ensure Windows consoles don't crash on unicode output (e.g., ✅)
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import certifi
import psutil
import requests
from dotenv import load_dotenv
from flask import (
    Flask, request, jsonify, send_from_directory,
    redirect, session, render_template_string, abort
)
from functools import wraps
from flask_cors import CORS
from requests_oauthlib import OAuth2Session
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import openai

# Local modules - Import logging utils FIRST to configure logging
from app.utils.logging_utils import get_logger
from app.services.memory_service import get_memory_service
from app.services.llm_service import get_llm_service
from app.database import init_database, get_db
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
from app.db.collections import get_conversations_collection, get_tokens_collection, get_contacts_collection, get_waitlist_collection
from app.utils.oauth_utils import (
    load_google_credentials, save_google_credentials, get_gmail_profile,
    require_google_auth, build_google_flow, parse_expo_state,
    GOOGLE_SCOPES, OAUTH_BASE, TOKEN_URL
)
from app.utils.email_resend import send_waitlist_welcome_email
from app.config import Config

# Import new blueprints
from app.api.chat_routes import chat_bp
from app.api.gmail_routes import gmail_bp
from app.api.contacts_routes import contacts_bp
from app.api.calendar_routes import calendar_bp
from app.api.files_routes import files_bp

# Initialize logger after logging is configured
logger = get_logger(__name__)

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
    app = Flask(__name__, static_folder="web-build", static_url_path="")
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
    app.secret_key = Config.FLASK_SECRET_KEY or "change-me-in-prod"
    
    # Configure Flask's logger to use our logging system
    # Flask's logger should propagate to root logger (which has our handler)
    app.logger.propagate = True
    # Clear Flask's default handlers so messages propagate to root logger
    app.logger.handlers.clear()

    # Initialize database
    db_connected = init_database()
    if db_connected:
        logger.info("MongoDB connected successfully")
        
        # Initialize memory system indexes
        try:
            from app.memory.models import ensure_indexes
            ensure_indexes()
            logger.info("✅ Memory system indexes initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize memory indexes: {e}")
    else:
        logger.warning("MongoDB not connected - running in offline mode")

    # Register new blueprints (Phase 1)
    app.register_blueprint(chat_bp)
    app.register_blueprint(gmail_bp)
    app.register_blueprint(contacts_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(files_bp)
    
    # Register memory system blueprint
    from app.api.memory_routes import memory_bp
    app.register_blueprint(memory_bp)
    
    logger.info("Registered API blueprints: chat, gmail, contacts, calendar, files, memory")
    
    # Add request logging
    @app.before_request
    def log_request():
        msg = f"{request.method} {request.path}"
        # Force log to appear - use info level
        logger.info(msg)
        if request.path == "/api/gmail/send":
            logger.info("Sending email endpoint hit!")
    
    @app.after_request
    def log_response(response):
        msg = f"{request.method} {request.path} -> {response.status_code}"
        logger.info(msg)
        return response
    
    return app


# Create the app instance
app = create_app()


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
        logger.error(f"Failed to save message: {e}", exc_info=True)
    
    # Extract and store contact notes in background
    try:
        _extract_contact_notes(user_id, user_message, bot_reply)
    except Exception as e:
        logger.error(f"Failed to extract contact notes: {e}", exc_info=True)


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
            logger.error(f"Failed to extract notes for contact {contact.get('email')}: {e}", exc_info=True)
            continue


def _build_flow(redirect_uri: str, state: str | None = None):
    """Return a google-auth Flow object with the common settings."""
    return build_google_flow(redirect_uri, state)


def _get_redirect_uri():
    """Get the appropriate redirect URI based on environment."""
    # 🔧 FORCE LOCAL DEVELOPMENT MODE
    # If FORCE_LOCAL_OAUTH is set to true, always use localhost (for testing)
    force_local = os.getenv("FORCE_LOCAL_OAUTH", "false").lower() == "true"
    if force_local:
        logger.info("🏠 Forcing localhost OAuth redirect (FORCE_LOCAL_OAUTH=true)")
        return "http://localhost:10000/google/oauth2callback"
    
    # Check for Railway or other production URL from environment
    railway_url = os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("RAILWAY_STATIC_URL")
    production_url = os.getenv("PRODUCTION_URL")
    
    # Prefer explicit production base URL if provided (keeps www if you configured it)
    if production_url:
        base_url = production_url if production_url.startswith("http") else f"https://{production_url}"
        return f"{base_url}/google/oauth2callback"
    
    # Use request host / forwarded host if available (for dynamic detection behind proxies)
    try:
        forwarded_proto = request.headers.get("X-Forwarded-Proto")
        scheme = "https" if (request.is_secure or forwarded_proto == "https") else "http"

        forwarded_host = request.headers.get("X-Forwarded-Host")
        if forwarded_host and forwarded_host not in ["localhost", "127.0.0.1"]:
            return f"{scheme}://{forwarded_host}/google/oauth2callback"

        host = request.host
        # Also check for local network IPs (192.168.x.x, 10.x.x.x)
        if host and not any(h in host for h in ["localhost", "127.0.0.1", "192.168.", "10."]):
            return f"{scheme}://{host}/google/oauth2callback"
    except Exception:
        pass

    # Fallback to environment variables
    if railway_url:
        base_url = railway_url if railway_url.startswith("http") else f"https://{railway_url}"
        return f"{base_url}/google/oauth2callback"

    # Development fallback
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




# All Gmail routes are now handled by the gmail_bp blueprint (app/api/gmail_routes.py)


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


# NOTE: Route removed - handled by gmail_bp blueprint (app/api/gmail_routes.py)
# The blueprint route has better error handling and should be used instead


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
        logger.error(f"OAuth error: {e}", exc_info=True)
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
        
        # 🎯 BACKFILL FACTS: User just connected their account
        # Trigger background backfill of their Gmail messages to extract facts
        try:
            from app.memory.background_jobs import get_job_queue
            from app.memory.models import get_messages_collection
            
            # Check if user has existing messages in DB
            messages_col = get_messages_collection()
            if messages_col:
                message_count = messages_col.count_documents({"user_id": state})
                
                if message_count > 0:
                    logger.info(f"🔄 Triggering backfill for user {state} ({message_count} messages)")
                    
                    # Enqueue backfill job (non-blocking)
                    def backfill_for_new_user():
                        import requests
                        try:
                            requests.post(
                                "http://localhost:10000/memory/admin/backfill-facts",
                                json={"user_id": state, "limit": 50},  # Last 50 messages
                                timeout=300  # 5 minutes timeout
                            )
                            logger.info(f"✅ Backfill completed for user {state}")
                        except Exception as e:
                            logger.error(f"❌ Backfill failed for user {state}: {e}")
                    
                    job_queue = get_job_queue()
                    job_queue.enqueue(
                        backfill_for_new_user,
                        job_id=f"backfill-oauth-{state}"
                    )
                else:
                    logger.info(f"ℹ️ No messages to backfill for new user {state}")
        except Exception as e:
            # Don't fail OAuth if backfill fails
            logger.warning(f"⚠️ Could not trigger backfill for user {state}: {e}")
        
        # 📧 EMAIL FACT EXTRACTION: Extract facts from emails after login (background workers)
        # This runs separately from classification to ensure facts are extracted immediately after login
        try:
            from app.memory.background_jobs import get_job_queue
            
            # Enqueue email fact extraction job (non-blocking)
            def extract_email_facts_for_new_user():
                import requests
                try:
                    logger.info(f"🔄 Starting email fact extraction for user {state}")
                    response = requests.post(
                        "http://localhost:10000/memory/admin/backfill-email-facts",
                        json={"user_id": state, "max_emails": 100},  # Extract facts from last 100 emails
                        timeout=600  # 10 minutes timeout
                    )
                    if response.status_code == 200:
                        logger.info(f"✅ Email fact extraction completed for user {state}")
                    else:
                        logger.error(f"❌ Email fact extraction failed for user {state}: HTTP {response.status_code}")
                except Exception as e:
                    logger.error(f"❌ Email fact extraction failed for user {state}: {e}")
            
            job_queue = get_job_queue()
            job_queue.enqueue(
                extract_email_facts_for_new_user,
                job_id=f"extract-email-facts-oauth-{state}"
            )
        except Exception as e:
            # Don't fail OAuth if fact extraction fails
            logger.warning(f"⚠️ Could not trigger email fact extraction for user {state}: {e}")
        
        # 📧 EMAIL CLASSIFICATION: Classify existing emails on first login
        # Uses the existing classify_background endpoint (v3.0 classification only, no fact extraction)
        try:
            import threading
            from app.database import get_db
            
            db = get_db()
            if db.is_connected and db.db is not None:
                users_col = db.db["users"]
                emails_col = db.db["emails"]
                
                # Check if user has been processed
                user_doc = users_col.find_one({"user_id": state})
                email_count = emails_col.count_documents({"user_id": state})
                
                # Only trigger if: has emails AND not yet classified
                if email_count > 0 and (not user_doc or not user_doc.get("initial_email_classification_done")):
                    logger.info(f"📧 New user {state} - classifying {email_count} emails with v3.0")
                    
                    # Mark as in-progress
                    users_col.update_one(
                        {"user_id": state},
                        {
                            "$set": {
                                "user_id": state,
                                "initial_email_classification_done": False,
                                "email_classification_started_at": datetime.utcnow().isoformat(),
                            }
                        },
                        upsert=True
                    )
                    
                    # Trigger classification in background
                    def classify_user_emails():
                        import requests
                        try:
                            logger.info(f"🔄 Starting email classification for user {state}")
                            
                            # Use existing classify_background endpoint (v3.0 classification only, no fact extraction)
                            # Fact extraction happens separately via backfill-email-facts endpoint
                            response = requests.post(
                                "http://localhost:10000/api/gmail/classify-background",
                                json={"user_id": state, "max_emails": 200},
                                timeout=600
                            )
                            
                            if response.status_code == 200:
                                logger.info(f"✅ Email classification completed for user {state}")
                                users_col.update_one(
                                    {"user_id": state},
                                    {
                                        "$set": {
                                            "initial_email_classification_done": True,
                                            "email_classification_completed_at": datetime.utcnow().isoformat(),
                                        }
                                    }
                                )
                            else:
                                logger.error(f"❌ Email classification failed for user {state}: HTTP {response.status_code}")
                                
                        except Exception as e:
                            logger.error(f"❌ Email classification error for user {state}: {e}")
                    
                    # Run in background thread (non-blocking)
                    thread = threading.Thread(target=classify_user_emails, daemon=True)
                    thread.start()
                    
                    logger.info(f"📧 Email classification started in background for user {state}")
                else:
                    if email_count == 0:
                        logger.info(f"ℹ️ No emails to classify for user {state}")
                    else:
                        logger.info(f"✅ User {state} emails already classified")
                        
        except Exception as e:
            # Don't fail OAuth if classification fails
            logger.warning(f"⚠️ Could not trigger email classification for user {state}: {e}")

    except Exception as e:
        logger.error(f"OAuth callback error: {e}", exc_info=True)
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
    user_id = state  # Use state as userId (this is the username)

    # Generate session ID (matching frontend genSession format: userId-randomstring)
    # Frontend uses: `${id}-${Math.random().toString(36).substring(2, 8)}`
    # This generates a 6-character alphanumeric string (base36)
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    session_id = f"{user_id}-{random_str}"

    # Get base domain for redirect - prioritize custom domain over Railway domain
    scheme = 'https' if (request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https') else 'http'
    
    # Determine the base URL for redirect
    clean_base_url = None
    
    # 🔧 PRIORITY 0: Force localhost if FORCE_LOCAL_OAUTH is enabled
    force_local = os.getenv("FORCE_LOCAL_OAUTH", "false").lower() == "true"
    if force_local:
        logger.info("🏠 Forcing localhost final redirect (FORCE_LOCAL_OAUTH=true)")
        clean_base_url = "http://localhost:8081"  # Your frontend port
    
    # Priority 1: Check PRODUCTION_URL first (explicit configuration takes highest priority)
    if not clean_base_url:
        production_url = os.getenv("PRODUCTION_URL")
        if production_url and 'railway.app' not in production_url.lower():
            # Use custom domain from PRODUCTION_URL exactly as specified (preserve www. if included)
            if production_url.startswith('http'):
                parsed = urlparse(production_url)
                clean_base_url = f"{parsed.scheme}://{parsed.netloc}"
            else:
                clean_base_url = f"{scheme}://{production_url}"
    
    # Priority 2: Check expo_redirect if it's a web URL (only if PRODUCTION_URL not set)
    if not clean_base_url and expo_app and expo_redirect and (expo_redirect.startswith('http://') or expo_redirect.startswith('https://')):
        parsed = urlparse(expo_redirect)
        if parsed.netloc and 'railway.app' not in parsed.netloc.lower():
            # Preserve the domain exactly as provided (don't strip www.)
            clean_base_url = f"{parsed.scheme}://{parsed.netloc}"
    
    # Priority 3: Check X-Forwarded-Host header (Railway sets this for custom domains)
    if not clean_base_url:
        forwarded_host = request.headers.get('X-Forwarded-Host')
        if forwarded_host and 'railway.app' not in forwarded_host.lower():
            # Preserve the domain exactly as provided (don't strip www.)
            clean_base_url = f"{scheme}://{forwarded_host}"
    
    # Priority 4: Fall back to request.host
    if not clean_base_url:
        host = request.host
        # Preserve the domain exactly as provided (don't strip www.)
        clean_base_url = f"{scheme}://{host}"
    
    # Redirect to chat page with both userId and sessionId (same format as guest login)
    if expo_app:
        # Check if expo_redirect is a web URL (starts with http)
        if expo_redirect and (expo_redirect.startswith('http://') or expo_redirect.startswith('https://')):
            # Web app accessing via Expo - redirect to chat page with userId and sessionId
            redirect_url = f"{clean_base_url}/chat?userId={user_id}&sessionId={session_id}"
            return redirect(redirect_url)
        else:
            # Mobile Expo app - show success page
            display_email = str(user_email) if user_email else str(state)
            return render_template_string(_get_success_page_template(display_email))

    # Web app redirect - redirect to chat page with userId and sessionId
    redirect_url = f"{clean_base_url}/chat?userId={user_id}&sessionId={session_id}"
    return redirect(redirect_url)


# ──────────────────────────────────────────────────────────────────
# Health Check & API Info Route
# ──────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for Railway and monitoring."""
    return jsonify({
        "status": "healthy",
        "service": "mental-health-ai-assistant",
        "version": "1.0.0"
    }), 200


@app.route("/api/info", methods=["GET"])
def api_info():
    """API information endpoint."""
    return jsonify({
        "service": "Mental Health AI Assistant API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "api": "/api",
            "chat": "/api/chat",
            "gmail": "/api/gmail/*",
            "contacts": "/api/contacts/*",
            "calendar": "/api/calendar/*",
            "files": "/api/files/*"
        },
        "documentation": "See API endpoints for usage"
    }), 200


# ──────────────────────────────────────────────────────────────────
# Waitlist Routes
# ──────────────────────────────────────────────────────────────────

# Waitlist page is now handled by the Expo app frontend (my-chatbot-expo)
# The old Flask HTML template has been removed to avoid conflicts
# Only API endpoints remain here for backend functionality


@app.route("/api/waitlist/test-email", methods=["POST"])
def test_waitlist_email():
    """Test endpoint to verify email sending works."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        test_email = (data.get("email") or "").strip().lower()
        test_name = (data.get("name") or "Test User").strip()
        
        if not test_email:
            return jsonify({
                "success": False,
                "error": "Email is required for testing."
            }), 400
        
        logger.info(f"Testing email send to {test_email}")
        email_sent = send_waitlist_welcome_email(to_email=test_email, name=test_name)
        
        if email_sent:
            return jsonify({
                "success": True,
                "message": f"Test email sent successfully to {test_email}! Check your inbox."
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Failed to send test email. Check server logs for details."
            }), 500
            
    except Exception as e:
        logger.error(f"Test email error: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"Error: {str(e)}"
        }), 500


@app.route("/api/waitlist/signup", methods=["POST"])
def waitlist_signup():
    """Handle waitlist signup submissions."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        referral_source = (data.get("referral_source") or "").strip()
        
        # Validation
        if not name or not email:
            return jsonify({
                "success": False,
                "error": "Name and email are required."
            }), 400
        
        # Basic email validation
        if "@" not in email or "." not in email.split("@")[1]:
            return jsonify({
                "success": False,
                "error": "Please enter a valid email address."
            }), 400
        
        # Get waitlist collection
        waitlist_col = get_waitlist_collection()
        
        # Track if we should save to database
        save_to_db = waitlist_col is not None
        
        if not save_to_db:
            logger.warning(f"Database not connected, but received signup: {email}")
        else:
            # Check if email already exists
            existing = waitlist_col.find_one({"email": email})
            if existing:
                logger.info(f"Email {email} already exists in waitlist, skipping email send")
                return jsonify({
                    "success": True,
                    "message": "You're already on the waitlist!"
                }), 200
            
            # Add to waitlist
            waitlist_entry = {
                "name": name,
                "email": email,
                "created_at": datetime.utcnow(),
                "status": "pending"
            }
            
            if referral_source:
                waitlist_entry["referral_source"] = referral_source
            
            waitlist_col.insert_one(waitlist_entry)
            logger.info(f"New signup: {name} ({email}) - Referral: {referral_source or 'N/A'}")
        
        # Send welcome email regardless of database status (non-blocking - don't fail if email fails)
        logger.info(f"Attempting to send welcome email to {email}")
        try:
            email_sent = send_waitlist_welcome_email(to_email=email, name=name)
            if email_sent:
                logger.info(f"Welcome email sent to {email}")
            else:
                logger.warning(f"Failed to send welcome email to {email}")
        except Exception as email_error:
            # Log but don't fail the request if email fails
            logger.error(f"Error sending welcome email to {email}: {email_error}", exc_info=True)
        
        return jsonify({
            "success": True,
            "message": "Successfully joined the waitlist!"
        }), 200
        
    except Exception as e:
        logger.error(f"Waitlist signup error: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "An error occurred. Please try again later."
        }), 500


def require_admin_auth(f):
    """Decorator to require admin authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is authenticated
        if not session.get('admin_authenticated'):
            return jsonify({
                "success": False,
                "error": "Authentication required"
            }), 401
        return f(*args, **kwargs)
    return decorated_function


@app.route("/api/waitlist/auth", methods=["POST"])
def waitlist_admin_auth():
    """Authenticate admin access."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        password = data.get("password", "").strip()
        
        # Get admin password from environment or use default
        admin_password = os.getenv("WAITLIST_ADMIN_PASSWORD", "admin123")
        
        if password == admin_password:
            session['admin_authenticated'] = True
            return jsonify({
                "success": True,
                "message": "Authenticated"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Invalid password"
            }), 401
            
    except Exception as e:
        logger.error(f"Admin auth error: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Authentication error"
        }), 500


@app.route("/api/waitlist/logout", methods=["POST"])
def waitlist_admin_logout():
    """Logout admin."""
    session.pop('admin_authenticated', None)
    return jsonify({
        "success": True,
        "message": "Logged out"
    }), 200


@app.route("/api/waitlist/list", methods=["GET"])
@require_admin_auth
def waitlist_list():
    """Get all waitlist signups (admin view)."""
    try:
        # Get waitlist collection
        waitlist_col = get_waitlist_collection()
        if waitlist_col is None:
            return jsonify({
                "success": False,
                "error": "Database not connected."
            }), 500
        
        # Get all entries, sorted by creation date (newest first)
        entries = list(waitlist_col.find(
            {},
            {"_id": 0}  # Exclude MongoDB _id field
        ).sort("created_at", -1))
        
        # Convert datetime objects to strings for JSON serialization
        for entry in entries:
            if "created_at" in entry and isinstance(entry["created_at"], datetime):
                entry["created_at"] = entry["created_at"].isoformat()
        
        return jsonify({
            "success": True,
            "count": len(entries),
            "entries": entries
        }), 200
        
    except Exception as e:
        logger.error(f"Waitlist list error: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "An error occurred while fetching waitlist entries."
        }), 500


@app.route("/waitlist", methods=["GET"])
def waitlist_page():
    """Serve the waitlist page (handled by Expo frontend)."""
    # Serve index.html for SPA routing - the frontend will handle the /waitlist route
    static_folder = app.static_folder
    if static_folder and os.path.exists(static_folder):
        index_path = os.path.join(static_folder, "index.html")
        if os.path.exists(index_path):
            response = send_from_directory(static_folder, "index.html")
            response.headers['Content-Type'] = 'text/html; charset=utf-8'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            return response
    return jsonify({"error": "Frontend not found"}), 404


@app.route("/chat", methods=["GET"])
@app.route("/Chat", methods=["GET"])
def chat_page():
    """Serve the chat page (handled by Expo frontend)."""
    logger.info("chat_page route called")
    # Serve index.html for SPA routing - the frontend will handle the /chat route
    static_folder = app.static_folder
    if static_folder and os.path.exists(static_folder):
        index_path = os.path.join(static_folder, "index.html")
        logger.info(f"Serving index.html from chat route, exists: {os.path.exists(index_path)}")
        if os.path.exists(index_path):
            response = send_from_directory(static_folder, "index.html")
            response.headers['Content-Type'] = 'text/html; charset=utf-8'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            return response
    logger.error("index.html not found in chat route")
    return jsonify({"error": "Frontend not found"}), 404


@app.route("/waitlist/admin", methods=["GET"])
def waitlist_admin():
    """Admin page to view all waitlist signups."""
    # Check if authenticated
    if not session.get('admin_authenticated'):
        return render_template_string(_get_waitlist_admin_login_template())
    return render_template_string(_get_waitlist_admin_template())


def _get_waitlist_admin_login_template():
    """Return the admin login page HTML template."""
    template_path = os.path.join(os.path.dirname(__file__), "app", "templates", "waitlist", "admin_login.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Template not found: {template_path}")
        return "<html><body><h1>Template not found</h1></body></html>"


def _get_waitlist_admin_template():
    """Return the waitlist admin page HTML template."""
    template_path = os.path.join(os.path.dirname(__file__), "app", "templates", "waitlist", "admin.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Template not found: {template_path}")
        return "<html><body><h1>Template not found</h1></body></html>"


# ──────────────────────────────────────────────────────────────────
# Frontend Serving - Expo Web App
# ──────────────────────────────────────────────────────────────────

# Serve Expo static assets from root (these are referenced with absolute paths in the HTML)
# These routes must come BEFORE the catch-all route to be matched first
@app.route("/_expo/<path:asset_path>")
def serve_expo_assets(asset_path):
    """Serve Expo's _expo static assets."""
    static_folder = app.static_folder
    if static_folder and os.path.exists(static_folder):
        expo_dir = os.path.join(static_folder, "_expo")
        file_path = os.path.join(expo_dir, asset_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_from_directory(expo_dir, asset_path)
    logger.debug(f"_expo asset not found: {asset_path}")
    return jsonify({"error": "Asset not found"}), 404

@app.route("/assets/<path:asset_path>")
def serve_assets(asset_path):
    """Serve assets directory files."""
    static_folder = app.static_folder
    if static_folder and os.path.exists(static_folder):
        assets_dir = os.path.join(static_folder, "assets")
        file_path = os.path.join(assets_dir, asset_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_from_directory(assets_dir, asset_path)
    logger.debug(f"assets file not found: {asset_path}")
    return jsonify({"error": "Asset not found"}), 404

@app.route("/static/<path:asset_path>")
def serve_static_assets(asset_path):
    """Serve static directory files."""
    static_folder = app.static_folder
    if static_folder and os.path.exists(static_folder):
        static_dir = os.path.join(static_folder, "static")
        file_path = os.path.join(static_dir, asset_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_from_directory(static_dir, asset_path)
    logger.debug(f"static file not found: {asset_path}")
    return jsonify({"error": "Asset not found"}), 404

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    """Serve Expo web app or API routes."""
    logger.info(f"serve_frontend called with path: '{path}'")
    
    # Normalize path to lowercase for comparison
    path_lower = path.lower()
    
    # Don't interfere with API routes (check lowercase)
    if path_lower.startswith("api/"):
        logger.info(f"Returning 404 for API route: {path}")
        return jsonify({"error": "API endpoint not found"}), 404
    
    # Don't interfere with OAuth routes (check lowercase)
    if path_lower.startswith("google/"):
        logger.info(f"Returning 404 for OAuth route: {path}")
        return jsonify({"error": "Endpoint not found"}), 404
    
    # Don't interfere with waitlist admin route (check lowercase)
    if path_lower == "waitlist/admin":
        logger.info(f"Returning 404 for waitlist/admin route: {path}")
        return jsonify({"error": "Endpoint not found"}), 404
    
    # Check if web-build exists
    static_folder = app.static_folder
    if not static_folder:
        logger.warning("Static folder not configured")
        return jsonify({
            "service": "Mental Health AI Assistant API",
            "version": "1.0.0",
            "status": "running",
            "note": "Frontend web build not configured.",
            "health": "/health",
            "api_info": "/api/info"
        }), 200
    
    if not os.path.exists(static_folder):
        logger.warning(f"Static folder does not exist: {static_folder}")
        return jsonify({
            "service": "Mental Health AI Assistant API",
            "version": "1.0.0",
            "status": "running",
            "note": f"Frontend web build not found at {static_folder}. Expo app build may have failed.",
            "health": "/health",
            "api_info": "/api/info"
        }), 200
    
    # Serve static files if they exist (JS, CSS, images, etc.)
    # Handle both root-level assets and assets in subdirectories
    if path:
        file_path = os.path.join(static_folder, path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_from_directory(static_folder, path)
        
        # Also check for common asset paths that Expo uses
        # Expo web export creates assets in _expo/static/ and assets/ directories
        # These should be accessible from root, not from /waitlist
        if path.startswith("_expo/") or path.startswith("assets/") or path.startswith("static/"):
            # These are root-level assets, serve them from root
            root_path = path
            root_file_path = os.path.join(static_folder, root_path)
            if os.path.exists(root_file_path) and os.path.isfile(root_file_path):
                return send_from_directory(static_folder, root_path)
    
    # Serve index.html for all other routes (SPA routing)
    # This includes /waitlist and /chat which are handled by the Expo app's React Navigation
    index_path = os.path.join(static_folder, "index.html")
    logger.info(f"Checking for index.html at: {index_path}, exists: {os.path.exists(index_path)}")
    
    if os.path.exists(index_path):
        logger.info(f"Serving index.html for path: {path}")
        response = send_from_directory(static_folder, "index.html")
        # Ensure correct content type and prevent caching of index.html
        # This forces browsers to always fetch the latest version
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    
    # Fallback: API info if index.html doesn't exist
    logger.error(f"index.html not found at {index_path}")
    # List what files exist in the static folder for debugging
    try:
        files = os.listdir(static_folder) if os.path.exists(static_folder) else []
    except:
        files = []
    
    return jsonify({
        "service": "Mental Health AI Assistant API",
        "version": "1.0.0",
        "status": "running",
        "note": "Frontend index.html not found in web-build. Check Expo build logs.",
        "health": "/health",
        "api_info": "/api/info",
        "static_folder": static_folder,
        "static_folder_exists": os.path.exists(static_folder),
        "files_in_static_folder": files[:20]  # First 20 files for debugging
    }), 200


# ──────────────────────────────────────────────────────────────────
# Main Entry Point
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port_str = os.getenv("PORT", "10000")
    try:
        port = int(''.join(filter(str.isdigit, port_str)) or "10000")
    except ValueError:
        port = 10000
    
    logger.info(f"Starting server on http://0.0.0.0:{port}")
    logger.info("Server is ready to accept requests...")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    