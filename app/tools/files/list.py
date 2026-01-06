"""List tool for getting recent files."""

import json
from typing import Dict, Any

from app.services.file_service import list_recent_files


def list_files(user_id: str, max_results: int = 20) -> str:
    """
    List recent files from Google Drive.
    
    Parameters
    ----------
    user_id : str
        User identifier
    max_results : int
        Maximum number of files to return
        
    Returns
    -------
    str
        JSON string with file list
    """
    result = list_recent_files(user_id, max_results=max_results)
    return json.dumps(result)

