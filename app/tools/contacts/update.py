"""Tool: update_contact, normalize_contact_names, archive_contact — contact management."""

import json
from typing import Dict, Any, Optional, List

from app.services.contacts_service import (
    update_contact as service_update_contact,
    normalize_contact_names as service_normalize_contact_names,
    archive_contact as service_archive_contact,
)
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def update_contact(
    user_id: str,
    email: str,
    name: Optional[str] = None,
    nickname: Optional[str] = None,
    groups: Optional[List[str]] = None,
    notes: Optional[str] = None,
) -> str:
    """
    Update a contact's information.
    
    Parameters
    ----------
    user_id : str
        User identifier
    email : str
        Contact email address
    name : str, optional
        Contact name
    groups : list of str, optional
        Contact groups
    notes : str, optional
        Contact notes
        
    Returns
    -------
    str
        JSON string with update result
    """
    try:
        result = service_update_contact(
            user_id=user_id,
            email=email,
            name=name,
            nickname=nickname,
            groups=groups,
        )
        return json.dumps(result, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error in update_contact tool: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Failed to update contact"
        })


def normalize_contact_names(user_id: str) -> str:
    """
    Normalize contact names (fill missing names from email addresses).
    
    Parameters
    ----------
    user_id : str
        User identifier
        
    Returns
    -------
    str
        JSON string with normalization result
    """
    try:
        result = service_normalize_contact_names(user_id=user_id)
        return json.dumps(result, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error in normalize_contact_names tool: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Failed to normalize contact names"
        })


def archive_contact(
    user_id: str,
    email: str,
    archived: bool = True,
) -> str:
    """
    Archive or unarchive a contact.
    
    Parameters
    ----------
    user_id : str
        User identifier
    email : str
        Contact email address
    archived : bool, optional
        True to archive, False to unarchive (default: True)
        
    Returns
    -------
    str
        JSON string with archive result
    """
    try:
        result = service_archive_contact(
            user_id=user_id,
            email=email,
            archived=archived,
        )
        return json.dumps(result, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error in archive_contact tool: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Failed to archive contact"
        })

