"""Tool: list_contact_groups — list contact groups."""

import json
from typing import Dict, Any

from app.services.contacts_service import list_contact_groups as service_list_contact_groups
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def list_contact_groups(user_id: str) -> str:
    """
    List all contact groups for a user.
    
    Parameters
    ----------
    user_id : str
        User identifier
        
    Returns
    -------
    str
        JSON string with groups list
    """
    try:
        result = service_list_contact_groups(user_id=user_id)
        return json.dumps(result, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error in list_contact_groups tool: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Failed to list contact groups"
        })

