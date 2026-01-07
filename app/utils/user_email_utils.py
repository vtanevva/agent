"""
Utility functions to get user email address from user_id
"""

import logging
from typing import Optional
from app.utils.oauth_utils import load_google_credentials, get_gmail_profile

logger = logging.getLogger(__name__)


def get_user_email(user_id: str) -> str:
    """
    Get user's email address from user_id.
    
    Strategy:
    1. If user_id is already an email (contains @), return it
    2. Try to get email from Gmail profile using stored credentials
    3. Fall back to user_id if email can't be retrieved
    
    Args:
        user_id: User identifier (username or email)
        
    Returns:
        Email address (or user_id if email can't be determined)
    """
    if not user_id:
        return user_id
    
    # If user_id is already an email, return it
    if "@" in user_id:
        return user_id.lower().strip()
    
    # Try to get email from Gmail profile
    try:
        creds = load_google_credentials(user_id)
        if creds:
            email = get_gmail_profile(creds)
            if email:
                logger.debug(f"Retrieved email {email} for user_id {user_id}")
                return email.lower().strip()
    except Exception as e:
        logger.debug(f"Could not get email for user_id {user_id}: {e}")
    
    # Fall back to user_id (might be username)
    logger.debug(f"Using user_id as email fallback: {user_id}")
    return user_id.lower().strip()

