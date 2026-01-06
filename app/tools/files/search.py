"""Search tool for finding files related to prompts."""

import json
from typing import Dict, Any

from app.services.file_service import search_files_by_prompt


def search_documents(user_id: str, query: str, max_results: int = 10) -> str:
    """
    Search for documents related to a query.
    
    Parameters
    ----------
    user_id : str
        User identifier
    query : str
        Search query (e.g., "task list", "project documents")
    max_results : int
        Maximum number of results to return
        
    Returns
    -------
    str
        JSON string with search results
    """
    result = search_files_by_prompt(user_id, query, max_results=max_results)
    return json.dumps(result)

