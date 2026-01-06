"""Filter tool for getting files by type."""

import json
from typing import Dict, Any, List, Optional

from app.services.file_service import fetch_files


def fetch_files_by_type(
    user_id: str,
    file_types: List[str],
    max_results: int = 20,
) -> str:
    """
    Fetch files by specific types.
    
    Parameters
    ----------
    user_id : str
        User identifier
    file_types : list
        List of file types to filter by:
        - 'document' (Google Docs)
        - 'spreadsheet' (Google Sheets)
        - 'presentation' (Google Slides)
        - 'pdf'
        - 'image'
        - 'folder'
    max_results : int
        Maximum number of files to return
        
    Returns
    -------
    str
        JSON string with files
    """
    result = fetch_files(user_id, file_types=file_types, max_results=max_results)
    return json.dumps(result)

