"""Tool: reply_email — reply inside an existing email thread (Gmail or Outlook)."""

from typing import Optional

from app.utils.tool_registry import register, ToolSchema
from app.services.email.unified_service import reply_email as unified_reply_email


def reply_email(
    user_id: str,
    thread_id: str,
    to: str,
    body: str,
    subj_prefix: str = "Re:",
    provider: Optional[str] = None,
):
    """
    Reply to an email thread using the user's email provider.
    
    Uses unified email service to support both Gmail and Outlook.
    Automatically detects provider from stored email metadata if not specified.
    """
    try:
        result = unified_reply_email(
            user_id=user_id,
            thread_id=thread_id,
            to=to,
            body=body,
            subj_prefix=subj_prefix,
            provider=provider,
        )
        
        if result.get("success"):
            return f"Reply sent in thread {thread_id}."
        else:
            return f"Error: {result.get('error', 'Failed to send reply')}"
            
    except Exception as e:
        return f"Error: Failed to send reply - {str(e)}"


# Register the tool
register(
    reply_email,
    ToolSchema(
        name="reply_email",
        description="Send a reply inside an existing email thread (accepts threadId or messageId). Works with Gmail and Outlook.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "thread_id": {"type": "string"},
                "to": {"type": "string"},
                "body": {"type": "string"},
                "subj_prefix": {"type": "string"},
            },
            "required": ["user_id", "thread_id", "to", "body"],
        },
    ),
)
