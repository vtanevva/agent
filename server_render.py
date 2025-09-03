import os, uuid, pickle
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

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

# ──────────────────────────────────────────────────────────────────
# Local modules
# ──────────────────────────────────────────────────────────────────
try:
    from app.agent_core.agent import run_agent
    from app.chatbot import chat_with_gpt
    from app.chat_embeddings import get_user_facts
    from app.chat_embeddings import save_chat_to_memory, extract_facts_with_gpt
    from app.tools.calendar_manager import detect_calendar_requests, parse_datetime_from_text, create_calendar_event, list_calendar_events
    from app.agent_core.tool_registry import all_openai_schemas
    AGENT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Some modules not available: {e}")
    AGENT_AVAILABLE = False

# Google libs
try:
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    GOOGLE_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Google modules not available: {e}")
    GOOGLE_AVAILABLE = False

# ──────────────────────────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="my-chatbot/build", static_url_path="")
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Debug port binding
print(f"[DEBUG] App initialized. PORT env var: {os.getenv('PORT')}")
print(f"[DEBUG] Current working directory: {os.getcwd()}")
print(f"[DEBUG] Available environment variables: {list(os.environ.keys())}")

# Health check endpoint for Render
@app.route("/health")
def health_check():
    try:
        return jsonify({
            "status": "healthy",
            "message": "Server is running",
            "timestamp": datetime.now().isoformat(),
            "port": os.getenv('PORT', 'unknown'),
            "agent_available": AGENT_AVAILABLE,
            "google_available": GOOGLE_AVAILABLE
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Health check failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }), 500

# Memory usage monitoring endpoint (simplified for Render)
@app.route("/memory")
def memory_usage():
    try:
        return jsonify({
            "status": "ok",
            "message": "Memory monitoring available",
            "timestamp": datetime.now().isoformat(),
            "note": "Detailed memory info requires psutil (not available on Render free tier)"
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

# ──────────────────────────────────────────────────────────────────
# Database connection
# ──────────────────────────────────────────────────────────────────
try:
    if MONGO_URI:
        client = MongoClient(MONGO_URI)
        db = client.mental_health
        print("✅ MongoDB connected successfully")
    else:
        print("⚠️ MONGO_URI not set, database features disabled")
        client = None
        db = None
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    client = None
    db = None

# ──────────────────────────────────────────────────────────────────
# Main routes
# ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("my-chatbot/build", "index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    if not AGENT_AVAILABLE:
        return jsonify({"error": "Agent not available"}), 503
    
    try:
        data = request.get_json()
        user_message = data.get("message", "")
        user_id = data.get("user_id", "anonymous")
        
        # Simple response for now
        response = {
            "message": f"Hello! I'm your mental health assistant. You said: {user_message}",
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }
        
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/health")
def api_health():
    return health_check()

# ──────────────────────────────────────────────────────────────────
# Error handlers
# ──────────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500

# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Starting server on port {port}")
    print(f"🔍 PORT environment variable: {os.environ.get('PORT')}")
    print(f"🌍 Binding to 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

# Add port detection for gunicorn
print(f"🚀 [STARTUP] Server configured for port: {os.environ.get('PORT', '10000')}")
print(f"🚀 [STARTUP] App object created: {app}")
print(f"🚀 [STARTUP] Routes available: {[rule.rule for rule in app.url_map.iter_rules()]}")
