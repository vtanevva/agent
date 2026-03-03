"""
Unified email service that aggregates Gmail and Outlook.

Provides a single interface for email operations across multiple providers.
"""

from typing import Any, Dict, List, Optional

from app.database import get_db
from app.db.collections import get_tokens_collection
from app.utils.logging_utils import get_logger
from .gmail_provider import GmailProvider
from .outlook_provider import OutlookProvider
from .base_provider import EmailProvider

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────
# User Settings & Provider Management
# ──────────────────────────────────────────────────────────────────────


def check_user_email_connections(user_id: str) -> Dict[str, Any]:
    """
    Check which email providers the user has connected.
    
    Parameters
    ----------
    user_id : str
        User identifier
        
    Returns
    -------
    dict
        Connection status for each provider
    """
    try:
        tokens_col = get_tokens_collection()
        if tokens_col is None:
            return {
                "gmail_connected": False,
                "outlook_connected": False,
                "default_provider": "gmail",
            }
        
        # Check for Google credentials
        gmail_connected = False
        try:
            from app.utils.oauth_utils import load_google_credentials
            creds = load_google_credentials(user_id)
            if creds is not None:
                gmail_connected = True
                logger.info(f"Gmail credentials found for user {user_id}")
        except Exception as e:
            logger.warning(f"Could not load Gmail credentials for user {user_id}: {e}")
            gmail_connected = False
        
        # Check for Outlook token
        outlook_token = tokens_col.find_one({
            "user_id": user_id,
            "provider": "outlook"
        })
        outlook_connected = outlook_token is not None
        
        # Get user settings for default provider
        db = get_db()
        user_settings = None
        if db.is_connected:
            settings_col = db.db["user_settings"]
            user_settings = settings_col.find_one({"user_id": user_id})
        
        default_provider = "gmail"
        if user_settings:
            default_provider = user_settings.get("default_email_provider", "gmail")
        
        return {
            "gmail_connected": gmail_connected,
            "outlook_connected": outlook_connected,
            "default_provider": default_provider,
        }
        
    except Exception as e:
        logger.error(f"Error checking email connections: {e}", exc_info=True)
        return {
            "gmail_connected": False,
            "outlook_connected": False,
            "default_provider": "gmail",
        }


def set_default_email_provider(user_id: str, provider: str) -> Dict[str, Any]:
    """
    Set the default email provider for a user.
    
    Parameters
    ----------
    user_id : str
        User identifier
    provider : str
        Provider name ("gmail" or "outlook")
        
    Returns
    -------
    dict
        Result with success status
    """
    if provider not in ["gmail", "outlook"]:
        return {
            "success": False,
            "error": "Invalid provider. Must be 'gmail' or 'outlook'",
        }
    
    try:
        db = get_db()
        if not db.is_connected:
            return {"success": False, "error": "Database not available"}
        
        settings_col = db.db["user_settings"]
        settings_col.update_one(
            {"user_id": user_id},
            {"$set": {"default_email_provider": provider}},
            upsert=True,
        )
        
        return {
            "success": True,
            "default_provider": provider,
            "message": f"Default email provider set to {provider}",
        }
        
    except Exception as e:
        logger.error(f"Error setting default provider: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def _get_provider(user_id: str, provider: Optional[str] = None) -> Optional[EmailProvider]:
    """
    Get an email provider instance.
    
    Parameters
    ----------
    user_id : str
        User identifier
    provider : str, optional
        Provider name ("gmail" or "outlook"). If None, uses default.
        
    Returns
    -------
    EmailProvider or None
        Provider instance
    """
    if provider is None:
        connections = check_user_email_connections(user_id)
        provider = connections.get("default_provider", "gmail")
    
    if provider == "gmail":
        return GmailProvider(user_id)
    elif provider == "outlook":
        return OutlookProvider(user_id)
    else:
        logger.error(f"Unknown email provider: {provider}")
        return None


def _get_all_providers(user_id: str) -> List[EmailProvider]:
    """
    Get all connected email providers for a user.
    
    Parameters
    ----------
    user_id : str
        User identifier
        
    Returns
    -------
    list of EmailProvider
        List of connected provider instances
    """
    connections = check_user_email_connections(user_id)
    providers = []
    
    if connections.get("gmail_connected"):
        providers.append(GmailProvider(user_id))
    
    if connections.get("outlook_connected"):
        providers.append(OutlookProvider(user_id))
    
    return providers


# ──────────────────────────────────────────────────────────────────────
# Unified Email Operations
# ──────────────────────────────────────────────────────────────────────


def list_recent_emails(
    user_id: str,
    max_results: int = 5,
    from_email: Optional[str] = None,
    contact_name: Optional[str] = None,
    provider: Optional[str] = None,
    unified: bool = False,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    List recent emails from one or all providers.
    
    Parameters
    ----------
    user_id : str
        User identifier
    max_results : int, optional
        Maximum number of emails (default: 5)
    from_email : str, optional
        Filter by sender email
    contact_name : str, optional
        Filter by contact name
    provider : str, optional
        Specific provider to use. Ignored if unified=True.
    unified : bool, optional
        If True, fetch from all connected providers (default: False)
        
    Returns
    -------
    dict
        Result with emails list
    """
    try:
        if unified:
            # Fetch from all providers
            all_providers = _get_all_providers(user_id)
            all_emails = []
            
            for prov in all_providers:
                result = prov.list_recent_emails(
                    max_results=max_results,
                    from_email=from_email,
                    contact_name=contact_name,
                    force_refresh=force_refresh,
                )
                
                if result.get("success"):
                    all_emails.extend(result.get("emails", []))
            
            # Sort all emails by date (newest first) - using idx as proxy
            all_emails.sort(key=lambda x: x.get("idx", 0), reverse=True)
            
            # Limit to max_results
            all_emails = all_emails[:max_results]
            
            return {
                "success": True,
                "emails": all_emails,
                "count": len(all_emails),
                "unified": True,
            }
        else:
            # Fetch from single provider
            email_provider = _get_provider(user_id, provider)
            if not email_provider:
                return {"success": False, "error": "No email provider available"}
            
            return email_provider.list_recent_emails(
                max_results=max_results,
                from_email=from_email,
                contact_name=contact_name,
                force_refresh=force_refresh,
            )
            
    except Exception as e:
        logger.error(f"Error listing emails: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def send_email(
    user_id: str,
    to: str,
    subject: str,
    body: str,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send an email using the specified or default provider.
    
    Parameters
    ----------
    user_id : str
        User identifier
    to : str
        Recipient email address
    subject : str
        Email subject
    body : str
        Email body
    provider : str, optional
        Provider to use ("gmail" or "outlook"). Uses default if None.
        
    Returns
    -------
    dict
        Result with success status
    """
    try:
        email_provider = _get_provider(user_id, provider)
        if not email_provider:
            return {"success": False, "error": "No email provider available"}
        
        return email_provider.send_email(to=to, subject=subject, body=body)
        
    except Exception as e:
        logger.error(f"Error sending email: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def reply_email(
    user_id: str,
    thread_id: str,
    to: str,
    body: str,
    subj_prefix: str = "Re:",
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reply to an email thread using the specified or default provider.
    
    Parameters
    ----------
    user_id : str
        User identifier
    thread_id : str
        Thread/conversation ID
    to : str
        Recipient email address
    body : str
        Reply body
    subj_prefix : str, optional
        Subject prefix (default: "Re:")
    provider : str, optional
        Provider to use. If None, tries to detect from thread_id or uses default.
        
    Returns
    -------
    dict
        Result with success status
    """
    try:
        # If provider not specified, try to detect from stored email metadata
        if provider is None:
            try:
                db = get_db()
                if db.is_connected:
                    emails_col = db.db.get_collection("emails")
                    email_doc = emails_col.find_one({
                        "user_id": user_id,
                        "thread_id": thread_id,
                    })
                    if email_doc and email_doc.get("source"):
                        provider = email_doc.get("source")
            except Exception:
                pass  # Fall back to default
        
        email_provider = _get_provider(user_id, provider)
        if not email_provider:
            return {"success": False, "error": "No email provider available"}
        
        return email_provider.reply_email(
            thread_id=thread_id,
            to=to,
            body=body,
            subj_prefix=subj_prefix,
        )
        
    except Exception as e:
        logger.error(f"Error replying to email: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def get_thread_detail(
    user_id: str,
    thread_id: str,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get detailed information about an email thread.
    
    Parameters
    ----------
    user_id : str
        User identifier
    thread_id : str
        Thread/conversation ID
    provider : str, optional
        Provider to use. If None, tries to detect from stored metadata.
        
    Returns
    -------
    dict
        Result with thread details
    """
    try:
        # If provider not specified, try to detect from stored email metadata
        if provider is None:
            try:
                db = get_db()
                if db.is_connected:
                    emails_col = db.db.get_collection("emails")
                    email_doc = emails_col.find_one({
                        "user_id": user_id,
                        "thread_id": thread_id,
                    })
                    if email_doc and email_doc.get("source"):
                        provider = email_doc.get("source")
            except Exception:
                pass  # Fall back to default
        
        email_provider = _get_provider(user_id, provider)
        if not email_provider:
            return {"success": False, "error": "No email provider available"}
        
        return email_provider.get_thread_detail(thread_id=thread_id)
        
    except Exception as e:
        logger.error(f"Error getting thread detail: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def search_emails(
    user_id: str,
    query: str,
    max_results: int = 20,
    provider: Optional[str] = None,
    unified: bool = False,
) -> Dict[str, Any]:
    """
    Search for emails matching a query.
    
    Parameters
    ----------
    user_id : str
        User identifier
    query : str
        Search query
    max_results : int, optional
        Maximum number of results (default: 20)
    provider : str, optional
        Specific provider to use. Ignored if unified=True.
    unified : bool, optional
        If True, search across all connected providers (default: False)
        
    Returns
    -------
    dict
        Result with emails list
    """
    try:
        if unified:
            # Search across all providers
            all_providers = _get_all_providers(user_id)
            all_emails = []
            
            for prov in all_providers:
                result = prov.search_emails(query=query, max_results=max_results)
                
                if result.get("success"):
                    all_emails.extend(result.get("emails", []))
            
            # Sort by relevance (simplified - just by order)
            all_emails = all_emails[:max_results]
            
            return {
                "success": True,
                "emails": all_emails,
                "count": len(all_emails),
                "query": query,
                "unified": True,
            }
        else:
            email_provider = _get_provider(user_id, provider)
            if not email_provider:
                return {"success": False, "error": "No email provider available"}
            
            return email_provider.search_emails(query=query, max_results=max_results)
            
    except Exception as e:
        logger.error(f"Error searching emails: {e}", exc_info=True)
        return {"success": False, "error": str(e)}



