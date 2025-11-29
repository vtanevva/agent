"""Tool: sync_contacts — sync contacts from Gmail sent messages."""

import json
from typing import Dict, Any

from app.services.contacts_service import sync_contacts as service_sync_contacts
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def sync_contacts(
    user_id: str,
    max_sent: int = 1000,
    force: bool = False,
) -> str:
    """
    Sync contacts from Gmail sent messages.
    
    Parameters
    ----------
    user_id : str
        User identifier
    max_sent : int, optional
        Maximum number of sent messages to process (default: 1000)
    force : bool, optional
        Force re-sync even if contacts already exist (default: False)
        
    Returns
    -------
    str
        JSON string with sync result
    """
    try:
        result = service_sync_contacts(
            user_id=user_id,
            max_sent=max_sent,
            force=force,
        )
        return json.dumps(result, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error in sync_contacts tool: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Failed to sync contacts"
        })

