"""OAuth utilities for Google, Outlook, and Instagram authentication"""

import os
import json
import requests
from typing import Optional, Dict, Any
from urllib.parse import unquote, urlencode
from datetime import datetime, timedelta

from flask import url_for, jsonify
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from requests_oauthlib import OAuth2Session

from app.config import Config
from app.db.collections import get_tokens_collection

# Google OAuth scopes
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
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
    
    def _clear_google_credentials():
        try:
            tokens.update_one({"user_id": user_id}, {"$unset": {"google": ""}})
        except Exception as e:
            print(f"[ERROR] Failed to clear Google credentials for {user_id}: {e}", flush=True)

    try:
        doc = tokens.find_one({"user_id": user_id}, {"google": 1})
        if not doc or "google" not in doc:
            return None

        creds = Credentials.from_authorized_user_info(doc["google"])

        # Proactively refresh if needed so we can handle invalid_grant cleanly.
        if not creds.valid and creds.refresh_token:
            try:
                creds.refresh(Request())
                save_google_credentials(user_id, creds)
            except RefreshError as e:
                # Common cause: refresh token revoked/expired => invalid_grant
                err = str(e)
                print(f"❌ Google credentials refresh failed for {user_id}: {err}", flush=True)
                if "invalid_grant" in err.lower():
                    _clear_google_credentials()
                return None

        if not creds.valid and not creds.refresh_token:
            # No way to refresh; treat as disconnected.
            return None

        return creds
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
        # IMPORTANT: ensure the redirect_uri we actually use is always included in the client config.
        # Some environments set GOOGLE_REDIRECT_URI separately; keep it as an optional additional URI.
        google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI") or redirect_uri
        redirect_uris = []
        for uri in [redirect_uri, google_redirect_uri]:
            if uri and uri not in redirect_uris:
                redirect_uris.append(uri)
        
        client_config = {
            "web": {
                "client_id": google_client_id,
                "project_id": google_project_id,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": google_client_secret,
                "redirect_uris": redirect_uris
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
    if not state:
        return state, False, None
    
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
                # Extract everything after "redirect:" - this handles URLs with colons correctly
                redirect_value = part.split(":", 1)[1]
                # Strip whitespace and ensure it's a valid URL
                expo_redirect = redirect_value.strip()
                # Double-decode in case it's double-encoded
                if "%" in expo_redirect:
                    expo_redirect = unquote(expo_redirect)
    
    return user_id, expo_app, expo_redirect


# ──────────────────────────────────────────────────────────────────────
# Outlook/Microsoft OAuth Functions
# ──────────────────────────────────────────────────────────────────────


def load_outlook_token(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Load Outlook access token from database.
    Automatically refreshes if expired.
    
    Returns
    -------
    dict or None
        Token dict with access_token, refresh_token, expires_at, etc.
    """
    tokens = get_tokens_collection()
    if tokens is None:
        return None
    
    try:
        token_doc = tokens.find_one({
            "user_id": user_id,
            "provider": "outlook"
        })
        
        if not token_doc:
            return None
        
        # Check if token is expired
        expires_at = token_doc.get("expires_at")
        if expires_at:
            try:
                if isinstance(expires_at, str):
                    expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                elif isinstance(expires_at, datetime):
                    pass  # Already datetime
                else:
                    expires_at = None
                
                # Refresh if expired or expiring soon (within 5 minutes)
                if expires_at and expires_at < (datetime.utcnow() + timedelta(minutes=5)):
                    return refresh_outlook_token(user_id, token_doc.get("refresh_token"))
            except Exception as e:
                print(f"[WARNING] Error checking token expiry: {e}", flush=True)
        
        return {
            "access_token": token_doc.get("access_token"),
            "refresh_token": token_doc.get("refresh_token"),
            "expires_at": token_doc.get("expires_at"),
            "token_type": token_doc.get("token_type", "Bearer"),
        }
        
    except Exception as e:
        print(f"[ERROR] Failed to load Outlook token: {e}", flush=True)
        return None


def refresh_outlook_token(user_id: str, refresh_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Refresh Outlook access token using refresh token.
    
    Parameters
    ----------
    user_id : str
        User identifier
    refresh_token : str, optional
        Refresh token. If not provided, loads from database.
        
    Returns
    -------
    dict or None
        New token dict with access_token, refresh_token, expires_at
    """
    if not refresh_token:
        token_doc = load_outlook_token(user_id)
        if not token_doc:
            return None
        refresh_token = token_doc.get("refresh_token")
    
    if not refresh_token:
        return None
    
    try:
        client_id = Config.MICROSOFT_CLIENT_ID
        client_secret = Config.MICROSOFT_CLIENT_SECRET
        tenant_id = Config.MICROSOFT_TENANT_ID
        
        if not client_id or not client_secret:
            print("[ERROR] Microsoft OAuth credentials not configured", flush=True)
            return None
        
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": " ".join(Config.MICROSOFT_SCOPES),
        }
        
        response = requests.post(token_url, data=data, timeout=30)
        
        if response.status_code != 200:
            print(f"[ERROR] Failed to refresh Outlook token: {response.text}", flush=True)
            return None
        
        token_data = response.json()
        
        # Calculate expiry time
        expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        # Save to database
        tokens = get_tokens_collection()
        if tokens is not None:
            tokens.update_one(
                {"user_id": user_id, "provider": "outlook"},
                {
                    "$set": {
                        "access_token": token_data.get("access_token"),
                        "refresh_token": token_data.get("refresh_token", refresh_token),  # Keep old if not provided
                        "expires_at": expires_at.isoformat(),
                        "token_type": token_data.get("token_type", "Bearer"),
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                },
                upsert=True,
            )
        
        return {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token", refresh_token),
            "expires_at": expires_at.isoformat(),
            "token_type": token_data.get("token_type", "Bearer"),
        }
        
    except Exception as e:
        print(f"[ERROR] Error refreshing Outlook token: {e}", flush=True)
        return None


def save_outlook_token(user_id: str, token_data: Dict[str, Any], real_email: Optional[str] = None) -> bool:
    """
    Save Outlook OAuth token to MongoDB.
    
    Parameters
    ----------
    user_id : str
        User identifier
    token_data : dict
        Token data from Microsoft OAuth response
    real_email : str, optional
        User's actual email address
        
    Returns
    -------
    bool
        True if saved successfully
    """
    tokens = get_tokens_collection()
    if tokens is None:
        print("[WARNING] Cannot save Outlook token - MongoDB not available", flush=True)
        return False
    
    try:
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        token_doc = {
            "user_id": user_id,
            "provider": "outlook",
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": expires_at.isoformat(),
            "token_type": token_data.get("token_type", "Bearer"),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        tokens.update_one(
            {"user_id": user_id, "provider": "outlook"},
            {"$set": token_doc},
            upsert=True,
        )
        
        # Also save under real email if different
        if real_email and real_email != user_id:
            tokens.update_one(
                {"user_id": real_email, "provider": "outlook"},
                {"$set": token_doc},
                upsert=True,
            )
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to save Outlook token: {e}", flush=True)
        return False


def build_outlook_auth_url(redirect_uri: str, state: str) -> str:
    """
    Build Outlook OAuth authorization URL.
    
    Parameters
    ----------
    redirect_uri : str
        OAuth redirect URI
    state : str
        State parameter (user_id or with expo info)
        
    Returns
    -------
    str
        Authorization URL
    """
    client_id = Config.MICROSOFT_CLIENT_ID
    tenant_id = Config.MICROSOFT_TENANT_ID
    scopes = " ".join(Config.MICROSOFT_SCOPES)
    
    if not client_id:
        raise ValueError("MICROSOFT_CLIENT_ID not configured")
    
    auth_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
    
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": scopes,
        "state": state,
        "prompt": "consent",  # Force consent to get refresh token
    }
    
    return f"{auth_url}?{urlencode(params)}"


def get_outlook_profile(access_token: str) -> Optional[str]:
    """
    Get the user's Outlook email address from Microsoft Graph API.
    
    Parameters
    ----------
    access_token : str
        Outlook access token
        
    Returns
    -------
    str or None
        User's email address
    """
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        response = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers=headers,
            timeout=30,
        )
        
        if response.status_code == 200:
            profile = response.json()
            return profile.get("mail") or profile.get("userPrincipalName")
        else:
            print(f"❌ Error getting Outlook profile: {response.text}", flush=True)
            return None
            
    except Exception as e:
        print(f"❌ Error getting Outlook profile: {e}", flush=True)
        return None


def require_outlook_auth(user_id: str):
    """Check if user has Outlook credentials, return auth redirect if not"""
    token = load_outlook_token(user_id)
    if not token:
        return jsonify({
            "action": "connect_outlook",
            "connect_url": url_for("outlook_auth", user_id=user_id, _external=True)
        })
    return None

