"""Email service providers for Gmail and Outlook."""

from .base_provider import EmailProvider
from .gmail_provider import GmailProvider
from .outlook_provider import OutlookProvider
from .unified_service import (
    check_user_email_connections,
    set_default_email_provider,
    list_recent_emails,
    send_email,
    reply_email,
    get_thread_detail,
)

__all__ = [
    "EmailProvider",
    "GmailProvider",
    "OutlookProvider",
    "check_user_email_connections",
    "set_default_email_provider",
    "list_recent_emails",
    "send_email",
    "reply_email",
    "get_thread_detail",
]



