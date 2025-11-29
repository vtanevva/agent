"""
Email tools for the mental health AI assistant.

Tools for Gmail operations: list, detail, reply, send, style analysis, and classification.
"""

from .list import list_recent_emails
from .detail import get_thread_detail, _extract_plain_text
from .reply import reply_email
from .send import send_email
from .style import analyze_email_style, generate_reply_draft, generate_forward_draft
from .classifier import classify_email, CLASSIFICATION_VERSION

__all__ = [
    "list_recent_emails",
    "get_thread_detail",
    "_extract_plain_text",
    "reply_email",
    "send_email",
    "analyze_email_style",
    "generate_reply_draft",
    "generate_forward_draft",
    "classify_email",
    "CLASSIFICATION_VERSION",
]

