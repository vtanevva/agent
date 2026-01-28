"""
Shared utilities for email providers.

Common functions used by both Gmail and Outlook providers to avoid code duplication.
"""

import re
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.db.collections import get_contacts_collection
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def lookup_contact_emails(user_id: str, name: str) -> List[str]:
    """
    Look up all email addresses for a contact by name.
    
    Supports two modes:
    - "Marin" → matches all contacts with first name "Marin" (across all companies)
    - "Marin Fontys" or "Marin - Fontys" → matches only "Marin" at "Fontys" company
    
    Parameters
    ----------
    user_id : str
        User identifier
    name : str
        Contact name or email address
        
    Returns
    -------
    list of str
        List of email addresses
    """
    if not name or "@" in name:
        return [name] if name else []  # Already an email or empty
    
    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return []
    
    name_lower = name.strip().lower()
    emails = []
    
    # Parse query to detect if it contains company info
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
            first_name = words[0]
            company_name = " ".join(words[1:])
            has_company = True
    
    # Build query based on whether company is specified
    if has_company and company_name:
        # Match by first name AND company
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
        
        # Try matching name starting with first name AND company
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
            company_match = False
            if email:
                try:
                    domain = email.split("@", 1)[1].lower()
                    domain_parts = domain.split(".")
                    domain_company = domain_parts[-2] if len(domain_parts) >= 2 else ""
                    if company_name.lower() in domain_company.lower() or domain_company.lower() in company_name.lower():
                        company_match = True
                except:
                    pass
            
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


def normalize_email_format(email_data: Dict[str, Any], provider: str) -> Dict[str, Any]:
    """
    Normalize email data from different providers to a common format.
    
    Parameters
    ----------
    email_data : dict
        Raw email data from provider
    provider : str
        Provider name ("gmail" or "outlook")
        
    Returns
    -------
    dict
        Normalized email data with: threadId, from, subject, snippet, source
    """
    normalized = {
        "source": provider,
    }
    
    if provider == "gmail":
        # Gmail format: already has threadId
        normalized["threadId"] = email_data.get("threadId", email_data.get("id", ""))
        normalized["from"] = email_data.get("from", "")
        normalized["subject"] = email_data.get("subject", "(No subject)")
        normalized["snippet"] = email_data.get("snippet", "")[:120]
        
    elif provider == "outlook":
        # Outlook format: use conversationId as threadId, or messageId as fallback
        normalized["threadId"] = email_data.get("conversationId", email_data.get("id", ""))
        
        # Extract from address
        from_field = email_data.get("from", {})
        if isinstance(from_field, dict):
            email_address = from_field.get("emailAddress", {})
            name = email_address.get("name", "")
            email = email_address.get("address", "")
            if name and email:
                normalized["from"] = f"{name} <{email}>"
            else:
                normalized["from"] = email or name or ""
        else:
            normalized["from"] = str(from_field)
        
        normalized["subject"] = email_data.get("subject", "(No subject)")
        normalized["snippet"] = email_data.get("bodyPreview", email_data.get("preview", ""))[:120]
    
    return normalized


def store_email_metadata(
    user_id: str,
    thread_id: str,
    from_address: str,
    subject: str,
    snippet: str,
    source: str,
    additional_data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Store email metadata in the emails collection with source field.
    
    Parameters
    ----------
    user_id : str
        User identifier
    thread_id : str
        Thread/conversation ID
    from_address : str
        Sender address
    subject : str
        Email subject
    snippet : str
        Email preview/snippet
    source : str
        Email source ("gmail" or "outlook")
    additional_data : dict, optional
        Additional fields to store
    """
    try:
        from app.database import get_db
        
        db = get_db()
        if not db.is_connected or db.db is None:
            return
        
        emails_col = db.db.get_collection("emails")
        
        update_data = {
            "user_id": user_id,
            "thread_id": thread_id,
            "from": from_address,
            "subject": subject,
            "snippet": snippet[:200],  # Limit snippet length
            "source": source,  # Add source field
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        if additional_data:
            update_data.update(additional_data)
        
        # Use compound key: user_id + thread_id + source (same thread can exist in both providers)
        emails_col.update_one(
            {
                "user_id": user_id,
                "thread_id": thread_id,
                "source": source,  # Include source in query
            },
            {
                "$set": update_data,
                "$setOnInsert": {
                    "created_at": datetime.utcnow().isoformat(),
                }
            },
            upsert=True,
        )
        
    except Exception as e:
        logger.warning(f"Failed to store email metadata: {e}")


def extract_email_from_header(header: str) -> str:
    """
    Extract email address from "Name <email>" format.
    
    Parameters
    ----------
    header : str
        From header in format "Name <email>" or just "email"
        
    Returns
    -------
    str
        Email address
    """
    if not header:
        return ""
    
    # Try to extract email from <email> format
    email_match = re.search(r'<([^>]+)>', header)
    if email_match:
        return email_match.group(1)
    
    # If no angle brackets, assume the whole string is the email
    return header.strip()



