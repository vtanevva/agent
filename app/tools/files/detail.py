"""Detail tool for getting file information."""

import json
from typing import Dict, Any

from app.services.file_service import get_file_by_id


def get_file_details(user_id: str, file_id: str) -> str:
    """
    Get detailed information about a specific file.
    
    Parameters
    ----------
    user_id : str
        User identifier
    file_id : str
        Google Drive file ID
        
    Returns
    -------
    str
        JSON string with file details
    """
    result = get_file_by_id(user_id, file_id)
    return json.dumps(result)

