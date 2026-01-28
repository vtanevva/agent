"""Tool: send_email — send a fresh email message (Gmail or Outlook)."""

from typing import Optional

from app.utils.tool_registry import register, ToolSchema
from app.services.email.unified_service import send_email as unified_send_email


def send_email(
    user_id: str,
    to: str,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    provider: Optional[str] = None,
):
    """
    Send an email using the user's default or specified email provider.
    
    Uses unified email service to support both Gmail and Outlook.
    """
    subject = subject or "(No subject)"
    body = body or "Hello,\n\nBest regards"
    
    try:
        result = unified_send_email(
            user_id=user_id,
            to=to,
            subject=subject,
            body=body,
            provider=provider,
        )
        
        if result.get("success"):
            return f"Email sent to {to}."
        else:
            return f"Error: {result.get('error', 'Failed to send email')}"
            
    except Exception as e:
        return f"Error: Failed to send email - {str(e)}"


# Register the tool
register(
    send_email,
    ToolSchema(
        name="send_email",
        description="Send an email via the user's email account (Gmail or Outlook).",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["user_id", "to"],
        },
    ),
)
