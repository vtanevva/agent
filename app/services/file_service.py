"""
File service for Google Drive operations.

This module provides:
- Connecting to Google Drive
- Fetching files and folders
- Searching for documents based on queries
- Caching and syncing file metadata
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import threading

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.utils.logging_utils import get_logger
from app.utils.oauth_utils import load_google_credentials
from app.database import get_db

logger = get_logger(__name__)

# Cache to store files metadata for fast retrieval
_FILES_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TIMESTAMP: Dict[str, datetime] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour


def _invalidate_cache(user_id: str) -> None:
    """Invalidate cache for a specific user"""
    if user_id in _FILES_CACHE:
        del _FILES_CACHE[user_id]
    if user_id in _CACHE_TIMESTAMP:
        del _CACHE_TIMESTAMP[user_id]


def _is_cache_valid(user_id: str) -> bool:
    """Check if cache is still valid for user"""
    if user_id not in _CACHE_TIMESTAMP:
        return False
    age = (datetime.now() - _CACHE_TIMESTAMP[user_id]).total_seconds()
    return age < CACHE_TTL_SECONDS


def _connect_to_google_drive(user_id: str):
    """
    Connect to Google Drive using user's credentials.
    
    Parameters
    ----------
    user_id : str
        User identifier
        
    Returns
    -------
    googleapiclient.discovery.Resource or None
        Google Drive service resource, or None if auth fails
    """
    try:
        creds = load_google_credentials(user_id)
        if not creds:
            logger.error(f"No Google credentials found for user {user_id}")
            return None
        
        service = build("drive", "v3", credentials=creds)
        logger.info(f"Successfully connected to Google Drive for user {user_id}")
        return service
    except Exception as e:
        logger.error(f"Failed to connect to Google Drive for user {user_id}: {e}", exc_info=True)
        return None


def _fetch_files_from_drive(
    user_id: str,
    query: Optional[str] = None,
    max_results: int = 50,
    page_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch files from Google Drive.
    
    Parameters
    ----------
    user_id : str
        User identifier
    query : str, optional
        Drive API query string (e.g., "name contains 'task'")
    max_results : int
        Maximum number of files to return
    page_token : str, optional
        Token for pagination
        
    Returns
    -------
    dict
        Response with files list and metadata
    """
    try:
        service = _connect_to_google_drive(user_id)
        if not service:
            return {"success": False, "error": "Failed to authenticate with Google Drive"}
        
        # Default query: exclude trashed files and folders
        if query:
            full_query = f"{query} and trashed=false"
        else:
            full_query = "trashed=false"
        
        request = service.files().list(
            q=full_query,
            spaces="drive",
            fields="files(id, name, mimeType, modifiedTime, createdTime, webViewLink, size, owners, parents)",
            pageSize=max_results,
            pageToken=page_token,
            orderBy="modifiedTime desc",
        )
        
        result = request.execute()
        files = result.get("files", [])
        
        logger.info(f"Fetched {len(files)} files from Google Drive for user {user_id}")
        
        return {
            "success": True,
            "files": files,
            "next_page_token": result.get("nextPageToken"),
        }
    except HttpError as e:
        logger.error(f"Google Drive API error: {e}", exc_info=True)
        return {"success": False, "error": f"Google Drive API error: {str(e)}"}
    except Exception as e:
        logger.error(f"Error fetching files from Google Drive: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def fetch_files(
    user_id: str,
    file_types: Optional[List[str]] = None,
    max_results: int = 50,
) -> Dict[str, Any]:
    """
    Fetch files from Google Drive, optionally filtered by type.
    
    Parameters
    ----------
    user_id : str
        User identifier
    file_types : list, optional
        List of file types to filter by. Examples:
        - 'document' (Google Docs)
        - 'spreadsheet' (Google Sheets)
        - 'presentation' (Google Slides)
        - 'pdf'
        - 'image'
        - None to get all types
    max_results : int
        Maximum number of files to return
        
    Returns
    -------
    dict
        Response with files list
    """
    try:
        mime_type_map = {
            "document": "application/vnd.google-apps.document",
            "spreadsheet": "application/vnd.google-apps.spreadsheet",
            "presentation": "application/vnd.google-apps.presentation",
            "pdf": "application/pdf",
            "image": ["image/jpeg", "image/png", "image/gif"],
            "folder": "application/vnd.google-apps.folder",
        }
        
        query_parts = []
        
        if file_types:
            type_queries = []
            for file_type in file_types:
                mime_types = mime_type_map.get(file_type.lower())
                if isinstance(mime_types, list):
                    for mime_type in mime_types:
                        type_queries.append(f"mimeType='{mime_type}'")
                elif mime_types:
                    type_queries.append(f"mimeType='{mime_types}'")
            
            if type_queries:
                query_parts.append(f"({' or '.join(type_queries)})")
        
        query = " and ".join(query_parts) if query_parts else None
        
        return _fetch_files_from_drive(user_id, query=query, max_results=max_results)
    except Exception as e:
        logger.error(f"Error in fetch_files: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def search_files_by_prompt(
    user_id: str,
    prompt: str,
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    Search Google Drive files related to a given prompt.
    
    Searches file names, descriptions, and uses semantic matching via LLM.
    
    Parameters
    ----------
    user_id : str
        User identifier
    prompt : str
        Search prompt or question (e.g., "find my task list", "documents for projects")
    max_results : int
        Maximum number of files to return
        
    Returns
    -------
    dict
        Response with relevant files and relevance scores
    """
    try:
        # Extract keywords from prompt for initial search
        keywords = _extract_keywords_from_prompt(prompt)
        
        if not keywords:
            logger.warning(f"No keywords extracted from prompt: {prompt}")
            return {"success": True, "files": [], "message": "No relevant files found"}
        
        # Build Drive API query with keywords
        query_conditions = []
        for keyword in keywords[:3]:  # Limit to 3 keywords to avoid complex queries
            query_conditions.append(f"name contains '{keyword}'")
        
        query = " or ".join(query_conditions)
        
        result = _fetch_files_from_drive(user_id, query=query, max_results=max_results * 2)
        
        if not result["success"]:
            return result
        
        files = result["files"]
        
        # Score files based on relevance to prompt
        scored_files = _score_files_by_relevance(files, prompt)
        
        # Sort by score and return top results
        sorted_files = sorted(scored_files, key=lambda f: f["relevance_score"], reverse=True)
        
        logger.info(f"Found {len(sorted_files)} relevant files for prompt: {prompt}")
        
        return {
            "success": True,
            "files": sorted_files[:max_results],
            "prompt": prompt,
            "total_found": len(sorted_files),
        }
    except Exception as e:
        logger.error(f"Error searching files by prompt: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def _extract_keywords_from_prompt(prompt: str) -> List[str]:
    """
    Extract search keywords from a natural language prompt.
    
    Examples:
    - "find my task list" → ["task", "list"]
    - "documents for projects" → ["documents", "projects"]
    
    Parameters
    ----------
    prompt : str
        Natural language search prompt
        
    Returns
    -------
    list
        List of keywords to search for
    """
    # Remove common words
    stop_words = {
        "find", "my", "the", "a", "and", "or", "is", "for", "to", "in", "of",
        "about", "with", "from", "on", "at", "by", "all", "can", "have", "this",
        "that", "what", "which", "when", "where", "why", "how", "please", "show",
        "get", "documents", "files"
    }
    
    # Split and clean
    words = prompt.lower().split()
    keywords = [
        w.strip('.,!?;:') for w in words
        if w.strip('.,!?;:') and w.lower() not in stop_words and len(w) > 2
    ]
    
    return keywords


def _score_files_by_relevance(files: List[Dict[str, Any]], prompt: str) -> List[Dict[str, Any]]:
    """
    Score files by relevance to the prompt.
    
    Parameters
    ----------
    files : list
        List of file objects from Google Drive
    prompt : str
        Search prompt
        
    Returns
    -------
    list
        Files with added relevance_score field
    """
    keywords = _extract_keywords_from_prompt(prompt)
    
    for file_obj in files:
        file_name = file_obj.get("name", "").lower()
        score = 0
        
        # Score based on keyword matches in name
        for keyword in keywords:
            if keyword in file_name:
                score += 10
                # Boost if keyword is at the start
                if file_name.startswith(keyword):
                    score += 5
        
        # Slight boost for recently modified files
        modified_time_str = file_obj.get("modifiedTime")
        if modified_time_str:
            try:
                modified_time = datetime.fromisoformat(modified_time_str.replace("Z", "+00:00"))
                days_old = (datetime.now(modified_time.tzinfo) - modified_time).days
                if days_old < 7:
                    score += 5
                elif days_old < 30:
                    score += 2
            except Exception:
                pass
        
        file_obj["relevance_score"] = score
    
    return files


def get_file_by_id(user_id: str, file_id: str) -> Dict[str, Any]:
    """
    Get file metadata by ID.
    
    Parameters
    ----------
    user_id : str
        User identifier
    file_id : str
        Google Drive file ID
        
    Returns
    -------
    dict
        File metadata or error
    """
    try:
        service = _connect_to_google_drive(user_id)
        if not service:
            return {"success": False, "error": "Failed to authenticate with Google Drive"}
        
        file_obj = service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, modifiedTime, createdTime, webViewLink, size, owners, description",
        ).execute()
        
        return {"success": True, "file": file_obj}
    except HttpError as e:
        logger.error(f"Google Drive API error: {e}")
        return {"success": False, "error": f"File not found or access denied"}
    except Exception as e:
        logger.error(f"Error getting file by ID: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def list_recent_files(user_id: str, max_results: int = 20) -> Dict[str, Any]:
    """
    List recently modified files.
    
    Parameters
    ----------
    user_id : str
        User identifier
    max_results : int
        Maximum number of files to return
        
    Returns
    -------
    dict
        List of recent files
    """
    return _fetch_files_from_drive(user_id, max_results=max_results)


def sync_files_metadata(user_id: str) -> Dict[str, Any]:
    """
    Sync file metadata to local database in background.
    
    Parameters
    ----------
    user_id : str
        User identifier
        
    Returns
    -------
    dict
        Response indicating sync started
    """
    def _sync_worker() -> None:
        try:
            logger.info(f"Starting file metadata sync for user {user_id}")
            
            result = list_recent_files(user_id, max_results=100)
            
            if not result["success"]:
                logger.error(f"Failed to fetch files during sync: {result.get('error')}")
                return
            
            files = result.get("files", [])
            
            # Store in database if available
            try:
                db_manager = get_db()
                if db_manager.is_connected:
                    files_col = db_manager.db.get_collection("files_metadata")
                    
                    for file_obj in files:
                        files_col.update_one(
                            {"user_id": user_id, "file_id": file_obj["id"]},
                            {
                                "$set": {
                                    "user_id": user_id,
                                    "file_id": file_obj["id"],
                                    "name": file_obj.get("name"),
                                    "mime_type": file_obj.get("mimeType"),
                                    "modified_time": file_obj.get("modifiedTime"),
                                    "created_time": file_obj.get("createdTime"),
                                    "web_view_link": file_obj.get("webViewLink"),
                                    "size": file_obj.get("size"),
                                    "owners": file_obj.get("owners"),
                                    "synced_at": datetime.utcnow().isoformat(),
                                }
                            },
                            upsert=True,
                        )
                    
                    logger.info(f"Synced {len(files)} files to database for user {user_id}")
            except Exception as e:
                logger.warning(f"Failed to store files in database: {e}")
            
            # Update cache
            _FILES_CACHE[user_id] = {file_obj["id"]: file_obj for file_obj in files}
            _CACHE_TIMESTAMP[user_id] = datetime.now()
        except Exception as e:
            logger.error(f"File sync error: {e}", exc_info=True)
    
    # Run sync in background thread
    thread = threading.Thread(target=_sync_worker, daemon=True)
    thread.start()
    
    return {"success": True, "message": "File sync started in background"}

