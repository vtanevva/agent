"""
Tool: resolve_contact_email — resolve a contact name or nickname to an email.

This tool is useful for commands like:
- "send an email to Marin"
- "email Marin - Fontys about the meeting"

It uses the contacts service to look up the best-matching email address
for the given user and name/nickname. The nickname is read from the
contact's details (the `nickname` field in the contacts collection /
Contacts UI).
"""

import json
from typing import Any, Dict

from app.services.contacts_service import resolve_contact_email as service_resolve_contact_email
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def resolve_contact_email(user_id: str, name_or_email: str) -> str:
    """
    Resolve a contact name or nickname to an email address.

    Parameters
    ----------
    user_id : str
        User identifier.
    name_or_email : str
        Name, nickname, or raw email string provided by the user.

    Returns
    -------
    str
        JSON string with fields:
        {
          "success": True/False,
          "input": original_string,
          "resolved_email": email_or_original,
          "matched": bool,
          "error": optional error message
        }
    """
    try:
        result: Dict[str, Any] = service_resolve_contact_email(
            user_id=user_id,
            name_or_email=name_or_email,
        )
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error in resolve_contact_email tool: {e}", exc_info=True)
        return json.dumps(
            {
                "success": False,
                "input": name_or_email,
                "resolved_email": name_or_email,
                "matched": False,
                "error": str(e),
            },
            indent=2,
        )



