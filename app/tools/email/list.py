"""Tool: list_recent_emails — show the user's most‑recent *received* emails.

Returns JSON like:
[
  { "idx": 1,
    "threadId": "1983025185d299de",
    "from": "Deya Ivanova <ivanova.deq06@gmail.com>",
    "subject": "Re: Come Join Me",
    "snippet": "No thanks. I don't like you",
    "source": "gmail" },
  ...
]
"""

import json
from typing import Optional

from app.utils.tool_registry import register, ToolSchema
from app.services.email.unified_service import list_recent_emails as unified_list_emails


def list_recent_emails(
    user_id: str,
    max_results: int = 5,
    from_email: Optional[str] = None,
    contact_name: Optional[str] = None,
    provider: Optional[str] = None,
):
    """
    List recent emails from user's email provider(s).
    
    Uses unified email service to support both Gmail and Outlook.
    """
    try:
        result = unified_list_emails(
            user_id=user_id,
            max_results=max_results,
            from_email=from_email,
            contact_name=contact_name,
            provider=provider,
        )
        
        if not result.get("success"):
            return json.dumps([{
                "error": result.get("error", "Failed to list emails"),
                "message": result.get("error", "Unknown error"),
            }])
        
        # Return emails in expected format
        emails = result.get("emails", [])
        return json.dumps(emails, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps([{
            "error": "Failed to list emails",
            "message": str(e),
        }])


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
