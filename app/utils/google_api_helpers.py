"""
Shared helpers for Google API service construction.

This eliminates duplication across tool files that need to build
Gmail and Calendar service clients.
"""

from typing import Optional
from googleapiclient.discovery import build

from app.db.collections import get_tokens_collection
from app.utils import oauth_utils


def get_gmail_service(user_id: str):
    """
    Get Gmail API service for a user.
    
    This is the centralized way to get a Gmail service instance.
    It handles:
    - Checking MongoDB availability
    - Loading OAuth credentials
    - Building the service client
    - Error handling
    
    Parameters
    ----------
    user_id : str
        User identifier
        
    Returns
    -------
    googleapiclient Resource
        Gmail API v1 service client
        
    Raises
    ------
    RuntimeError
        If MongoDB is not available or service building fails
    FileNotFoundError
        If OAuth credentials not found for user
    """
    tokens = get_tokens_collection()
    if tokens is None:
        raise RuntimeError(
            "MongoDB is not available. Gmail features are disabled. "
            "Please set up a database connection."
        )
    
    try:
        creds = oauth_utils.load_google_credentials(user_id)
        if not creds:
            raise FileNotFoundError(
                f"Google OAuth token for user '{user_id}' not found. "
                "Ask the user to connect Gmail first."
            )
        return build("gmail", "v1", credentials=creds, cache_discovery=False)
    except FileNotFoundError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to load Gmail service: {e}")


def get_calendar_service(user_id: str):
    """
    Get Google Calendar API service for a user.
    
    Similar to get_gmail_service but for Calendar API.
    
    Parameters
    ----------
    user_id : str
        User identifier
        
    Returns
    -------
    googleapiclient Resource
        Calendar API v3 service client
        
    Raises
    ------
    RuntimeError
        If MongoDB is not available or service building fails
    FileNotFoundError
        If OAuth credentials not found for user
    """
    tokens = get_tokens_collection()
    if tokens is None:
        raise RuntimeError(
            "MongoDB is not available. Calendar features are disabled. "
            "Please set up a database connection."
        )
    
    try:
        creds = oauth_utils.load_google_credentials(user_id)
        if not creds:
            raise FileNotFoundError(
                f"Google OAuth token for user '{user_id}' not found. "
                "Ask the user to connect Google Calendar first."
            )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except FileNotFoundError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to load Calendar service: {e}")


def get_instagram_auth(user_id: str) -> dict:
    """
    Get Instagram authentication info for a user.
    
    Returns the Instagram page access token and account info.
    
    Parameters
    ----------
    user_id : str
        User identifier
        
    Returns
    -------
    dict
        Dictionary with 'page_id', 'ig_user_id', 'access_token'
        
    Raises
    ------
    RuntimeError
        If MongoDB is not available
    FileNotFoundError
        If Instagram is not connected for user
    """
    tokens = get_tokens_collection()
    if tokens is None:
        raise RuntimeError(
            "MongoDB is not available. Instagram features are disabled. "
            "Please set up a database connection."
        )
    
    doc = tokens.find_one({"user_id": user_id})
    if not doc or "instagram" not in doc:
        raise FileNotFoundError(
            f"Instagram not connected for user '{user_id}'. "
            "Ask the user to connect Instagram first."
        )
    
    return doc["instagram"]

