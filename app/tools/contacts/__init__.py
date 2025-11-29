"""
Contact tools for the mental health AI assistant.

Tools for contact management: sync, list, update, archive, groups, and conversations.
"""

from .sync import sync_contacts
from .list import list_contacts
from .update import update_contact, normalize_contact_names, archive_contact
from .groups import list_contact_groups
from .detail import get_contact_detail, get_contact_conversations
from .resolve_email import resolve_contact_email

__all__ = [
    "sync_contacts",
    "list_contacts",
    "update_contact",
    "normalize_contact_names",
    "archive_contact",
    "list_contact_groups",
    "get_contact_detail",
    "get_contact_conversations",
    "resolve_contact_email",
]

