"""Tool: list_contacts — list user's contacts."""

import json
from typing import Dict, Any

from app.services.contacts_service import list_contacts as service_list_contacts
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def list_contacts(
    user_id: str,
    include_archived: bool = False,
) -> str:
    """
    List user's contacts.
    
    Parameters
    ----------
    user_id : str
        User identifier
    include_archived : bool, optional
        Include archived contacts (default: False)
        
    Returns
    -------
    str
        JSON string with contacts list
    """
    try:
        result = service_list_contacts(
            user_id=user_id,
            include_archived=include_archived,
        )
        return json.dumps(result, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error in list_contacts tool: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Failed to list contacts"
        })

