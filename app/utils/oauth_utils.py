"""OAuth utilities for Google and Instagram authentication"""

import os
import json
from typing import Optional
from urllib.parse import unquote

from flask import url_for, jsonify
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from requests_oauthlib import OAuth2Session

from app.config import Config
from app.utils.db_utils import get_tokens_collection

# Google OAuth scopes
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.events",
]

# Instagram OAuth config
IG_SCOPES = [
    "pages_show_list",
    "instagram_basic",
    "instagram_manage_messages",
]

OAUTH_BASE = "https://www.facebook.com/v19.0/dialog/oauth"
TOKEN_URL = "https://graph.facebook.com/v19.0/oauth/access_token"


def load_google_credentials(user_id: str) -> Optional[Credentials]:
    """
    Fetch saved Google OAuth2 credentials for `user_id` from MongoDB
    and rehydrate to a Credentials instance.
    Returns None if no creds are found.
    """
    tokens = get_tokens_collection()
    if tokens is None:
        return None
    
    try:
        doc = tokens.find_one({"user_id": user_id}, {"google": 1})
        if not doc or "google" not in doc:
            return None
        return Credentials.from_authorized_user_info(doc["google"])
    except Exception as e:
        print(f"[ERROR] Failed to load Google credentials: {e}", flush=True)
        return None


def save_google_credentials(user_id: str, creds: Credentials, real_email: Optional[str] = None):
    """Save Google credentials to MongoDB"""
    tokens = get_tokens_collection()
    if tokens is None:
        print(f"[WARNING] Cannot save Google credentials - MongoDB not available", flush=True)
        return False
    
    try:
        cred_json = json.loads(creds.to_json())
        tokens.update_one(
            {"user_id": user_id},
            {"$set": {"google": cred_json}},
            upsert=True
        )
        
        # Also save under real email if different
        if real_email and real_email != user_id:
            tokens.update_one(
                {"user_id": real_email},
                {"$set": {"google": cred_json}},
                upsert=True
            )
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save Google credentials: {e}", flush=True)
        return False


def build_google_flow(redirect_uri: str, state: Optional[str] = None) -> Flow:
    """Build a Google OAuth Flow object"""
    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    if google_client_id and google_client_secret:
        # Use environment variables
        google_project_id = os.getenv("GOOGLE_PROJECT_ID", "gmail-agent-466700")
        google_redirect_uri = os.getenv(
            "GOOGLE_REDIRECT_URI", 
            "https://web-production-0b6ce.up.railway.app/google/oauth2callback"
        )
        
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
        google_json = os.getenv("GOOGLE_SECRET_FILE", "google_client_secret.json")
        flow = Flow.from_client_secrets_file(
            google_json,
            scopes=GOOGLE_SCOPES,
            redirect_uri=redirect_uri,
            state=state,
        )
    
    flow.redirect_uri = redirect_uri
    return flow


def get_gmail_profile(creds: Credentials) -> Optional[str]:
    """Get the user's Gmail email address"""
    try:
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress")
    except Exception as e:
        print(f"❌ Error getting Gmail profile: {e}")
        return None


def require_google_auth(user_id: str):
    """Check if user has Google credentials, return auth redirect if not"""
    creds = load_google_credentials(user_id)
    if not creds:
        return jsonify({
            "action": "connect_google",
            "connect_url": url_for("google_auth", user_id=user_id, _external=True)
        })
    return None


def parse_expo_state(state: str) -> tuple[str, bool, Optional[str]]:
    """Parse Expo app state from OAuth state parameter"""
    state_decoded = unquote(state) if state else state
    
    expo_app = False
    expo_redirect = None
    user_id = state_decoded
    
    if "|expo:" in state_decoded or "|expo:" in state_decoded.lower():
        parts = state_decoded.split("|")
        user_id = parts[0]  # Original user_id
        for part in parts[1:]:
            if part.startswith("expo:"):
                expo_value = part.split(":", 1)[1].strip().lower()
                expo_app = expo_value == "true"
            elif part.startswith("redirect:"):
                expo_redirect = part.split(":", 1)[1]
    
    return user_id, expo_app, expo_redirect

