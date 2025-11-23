"""Tool: list_recent_emails — show the user’s most‑recent *received* emails.

Returns JSON like:
[
  { "idx": 1,
    "threadId": "1983025185d299de",
    "from": "Deya Ivanova <ivanova.deq06@gmail.com>",
    "subject": "Re: Come Join Me",
    "snippet": "No thanks. I don't like you" },
  ...
]
"""

import json
from collections import OrderedDict
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from ..agent_core.tool_registry import register, ToolSchema
from ..utils import db_utils, oauth_utils


def _service(user_id: str):
    """Get Gmail service for user"""
    tokens = db_utils.get_tokens_collection()
    if tokens is None:
        raise RuntimeError(
            "MongoDB is not available. Gmail features are disabled. Please set up a database connection."
        )
    
    try:
        creds = oauth_utils.load_google_credentials(user_id)
        if not creds:
            raise FileNotFoundError(
                f"Google OAuth token for user '{user_id}' not found. Ask the user to connect Gmail first."
            )
        return build("gmail", "v1", credentials=creds, cache_discovery=False)
    except Exception as e:
        raise RuntimeError(f"Failed to load Gmail service: {e}")


def _lookup_contact_emails(user_id: str, name: str) -> list:
    """Look up all email addresses for a contact by name. Returns list of email strings.
    Supports two modes:
    - "Marin" → matches all contacts with first name "Marin" (across all companies)
    - "Marin Fontys" or "Marin - Fontys" → matches only "Marin" at "Fontys" company
    """
    if not name or "@" in name:
        return [name] if name else []  # Already an email or empty
    
    contacts_col = db_utils.get_contacts_collection()
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


def list_recent_emails(user_id: str, max_results: int = 5, from_email: str = None, contact_name: str = None):
    try:
        svc = _service(user_id)
    except Exception as e:
        return json.dumps([{
            "error": "Gmail service unavailable",
            "message": str(e),
            "suggestion": "Please set up MongoDB and connect your Gmail account."
        }])

    # If contact_name is provided, look up their email(s)
    contact_emails = []
    if contact_name and not from_email:
        contact_emails = _lookup_contact_emails(user_id, contact_name)
    elif from_email:
        contact_emails = [from_email]

    # 1) Build query - filter by sender email if provided
    query = "in:inbox to:me -from:me -from:mailer-daemon@googlemail.com"
    if contact_emails:
        if len(contact_emails) == 1:
            # Single email
            query = f"{query} from:{contact_emails[0]}"
        else:
            # Multiple emails - use OR syntax
            email_list = " OR ".join(contact_emails)
            query = f"{query} from:({email_list})"
    
    resp = svc.users().messages().list(
        userId="me",
        q=query,
        maxResults=50,
    ).execute()

    messages = resp.get("messages", [])

    # 2) Keep first message per thread, preserving order (newest first)
    threads_seen = OrderedDict()
    for m in messages:
        msg = (
            svc.users()
            .messages()
            .get(userId="me", id=m["id"], format="metadata", metadataHeaders=["Subject", "From"])
            .execute()
        )
        t_id = msg["threadId"]
        if t_id not in threads_seen:
            threads_seen[t_id] = msg
        if len(threads_seen) >= max_results:
            break

    # 3) Build JSON list and filter by email if needed (for exact match)
    items = []
    for idx, (t_id, msg) in enumerate(threads_seen.items(), start=1):
        hdrs = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        from_header = hdrs.get("From", "")
        
        # If contact_emails is provided, ensure it matches (extract email from "Name <email>" format)
        if contact_emails:
            import re
            # Extract email from From header
            email_match = re.search(r'<([^>]+)>', from_header)
            header_email = email_match.group(1) if email_match else from_header.lower()
            header_email_lower = header_email.lower()
            
            # Check if the header email matches any of the contact emails
            matches = False
            for contact_email in contact_emails:
                contact_email_lower = contact_email.lower()
                if contact_email_lower in header_email_lower or header_email_lower in contact_email_lower:
                    matches = True
                    break
            
            if not matches:
                continue  # Skip if doesn't match any contact email
        
        items.append({
            "idx": idx,
            "threadId": msg["threadId"],
            "from": from_header,
            "subject": hdrs.get("Subject", "(No subject)"),
            "snippet": msg.get("snippet", "")[:120],
        })

    return json.dumps(items, ensure_ascii=False)


# Register the tool
register(
    list_recent_emails,
    ToolSchema(
        name="list_recent_emails",
        description="Return a JSON array of the user's latest received inbox threads. Optionally filter by sender email address or contact name.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
                "from_email": {"type": "string", "description": "Optional: Filter emails by sender email address"},
                "contact_name": {"type": "string", "description": "Optional: Filter emails by contact name (will look up their email from contacts)"},
            },
            "required": ["user_id"],
        },
    ),
)
