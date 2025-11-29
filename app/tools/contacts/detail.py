"""Tool: get_contact_detail, get_contact_conversations — contact details and conversations."""

import json
from typing import Dict, Any, Optional

from app.services.contacts_service import (
    get_contact_detail as service_get_contact_detail,
    get_contact_conversations as service_get_contact_conversations,
)
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def get_contact_detail(
    user_id: str,
    email: str,
) -> str:
    """
    Get detailed information about a contact.
    
    Parameters
    ----------
    user_id : str
        User identifier
    email : str
        Contact email address
        
    Returns
    -------
    str
        JSON string with contact details
    """
    try:
        result = service_get_contact_detail(
            user_id=user_id,
            email=email,
        )
        return json.dumps(result, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error in get_contact_detail tool: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Failed to get contact detail"
        })


def get_contact_conversations(
    user_id: str,
    email: str,
    max_results: int = 50,
) -> str:
    """
    Get email conversations with a contact.
    
    Parameters
    ----------
    user_id : str
        User identifier
    email : str
        Contact email address
    max_results : int, optional
        Maximum number of conversations to return (default: 50)
        
    Returns
    -------
    str
        JSON string with conversations list
    """
    try:
        result = service_get_contact_conversations(
            user_id=user_id,
            email=email,
            max_results=max_results,
        )
        return json.dumps(result, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error in get_contact_conversations tool: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Failed to get contact conversations"
        })

