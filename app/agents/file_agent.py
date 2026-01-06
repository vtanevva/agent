"""
FileAgent - handles file-related requests and document retrieval.

This agent:
1. Detects file-related intents (search documents, list files, etc.)
2. Connects to Google Drive via file_service
3. Returns relevant documents based on the prompt
4. Uses LLM to enhance relevance scoring
"""

import json
from typing import Dict, Any, Optional, List

from app.services.file_service import (
    search_files_by_prompt,
    list_recent_files,
    fetch_files,
    get_file_by_id,
    sync_files_metadata,
)
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


class FileAgent:
    """
    Agent for handling file and document requests.
    
    Capabilities:
    - Search for documents related to tasks, projects, etc.
    - List recent files
    - Fetch files by type (documents, spreadsheets, etc.)
    - Sync file metadata
    """
    
    def __init__(self, llm_service, memory_service):
        """
        Initialize FileAgent.
        
        Parameters
        ----------
        llm_service : LLMService
            LLM service for text generation and analysis
        memory_service : MemoryService
            Memory service for conversation history
        """
        self.llm_service = llm_service
        self.memory_service = memory_service
    
    def _detect_file_intent(self, message: str) -> str:
        """
        Detect what the user wants to do with files.
        
        Returns: "search", "list", "fetch_type", "detail", or "unknown"
        """
        lower = message.lower()
        
        # Search for documents
        if any(phrase in lower for phrase in [
            "find", "search", "look for", "show me", "get me",
            "documents for", "files for", "related to", "about"
        ]):
            return "search"
        
        # List recent files
        if any(phrase in lower for phrase in [
            "recent files", "latest files", "recent documents",
            "recent changes", "list my files", "show files"
        ]):
            return "list"
        
        # Fetch specific file type
        if any(phrase in lower for phrase in [
            "documents", "spreadsheets", "sheets", "presentations",
            "slides", "pdfs", "images", "all my files"
        ]):
            return "fetch_type"
        
        # Get file detail
        if any(phrase in lower for phrase in [
            "details", "info", "open", "view", "show file"
        ]):
            return "detail"
        
        return "unknown"
    
    def _extract_file_types_from_message(self, message: str) -> Optional[List[str]]:
        """
        Extract file types from user message.
        
        Examples:
        - "show me documents" → ["document"]
        - "find spreadsheets and pdfs" → ["spreadsheet", "pdf"]
        """
        lower = message.lower()
        
        type_mapping = {
            "document": ["documents", "docs", "word"],
            "spreadsheet": ["spreadsheets", "sheets", "excel"],
            "presentation": ["presentations", "slides", "powerpoint"],
            "pdf": ["pdfs", "pdf"],
            "image": ["images", "pictures", "photos"],
        }
        
        found_types = []
        for file_type, keywords in type_mapping.items():
            if any(kw in lower for kw in keywords):
                found_types.append(file_type)
        
        return found_types if found_types else None
    
    def handle_chat(
        self,
        user_id: str,
        message: str,
        session_memory: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Handle a file-related chat message.
        
        Parameters
        ----------
        user_id : str
            User identifier
        message : str
            User's message
        session_memory : list, optional
            Recent conversation history
        metadata : dict, optional
            Additional metadata
            
        Returns
        -------
        dict
            Response with files and metadata
        """
        intent = self._detect_file_intent(message)
        logger.info(f"FileAgent detected intent: {intent} for message: {message[:50]}")
        
        try:
            if intent == "search":
                return self._handle_search_intent(user_id, message)
            
            elif intent == "list":
                return self._handle_list_intent(user_id)
            
            elif intent == "fetch_type":
                return self._handle_fetch_type_intent(user_id, message)
            
            elif intent == "detail":
                return self._handle_detail_intent(user_id, message)
            
            else:
                return {
                    "success": False,
                    "message": "I can help you with files. Try asking me to:\n"
                              "- Search for documents related to a topic\n"
                              "- Show recent files\n"
                              "- List specific file types (documents, spreadsheets, etc.)"
                }
        
        except Exception as e:
            logger.error(f"Error in FileAgent: {e}", exc_info=True)
            return {
                "success": False,
                "error": "I'm having trouble accessing your files right now. Please try again."
            }
    
    def _handle_search_intent(self, user_id: str, message: str) -> Dict[str, Any]:
        """Handle search intent - find documents related to prompt"""
        logger.info(f"Searching for files related to: {message}")
        
        result = search_files_by_prompt(user_id, message, max_results=10)
        
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Failed to search files")
            }
        
        files = result.get("files", [])
        
        if not files:
            return {
                "success": True,
                "files": [],
                "message": f"No files found related to '{message}'"
            }
        
        # Format response
        formatted_files = self._format_files_for_response(files)
        
        return {
            "success": True,
            "files": formatted_files,
            "count": len(formatted_files),
            "message": f"Found {len(formatted_files)} file(s) related to your request"
        }
    
    def _handle_list_intent(self, user_id: str) -> Dict[str, Any]:
        """Handle list intent - show recent files"""
        logger.info(f"Listing recent files for user {user_id}")
        
        result = list_recent_files(user_id, max_results=15)
        
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Failed to list files")
            }
        
        files = result.get("files", [])
        formatted_files = self._format_files_for_response(files)
        
        return {
            "success": True,
            "files": formatted_files,
            "count": len(formatted_files),
            "message": f"Here are your {len(formatted_files)} most recent files"
        }
    
    def _handle_fetch_type_intent(self, user_id: str, message: str) -> Dict[str, Any]:
        """Handle fetch type intent - get files by specific types"""
        logger.info(f"Fetching files by type for message: {message}")
        
        file_types = self._extract_file_types_from_message(message)
        
        if not file_types:
            return {
                "success": False,
                "error": "Could not determine file type from your request"
            }
        
        result = fetch_files(user_id, file_types=file_types, max_results=20)
        
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Failed to fetch files")
            }
        
        files = result.get("files", [])
        formatted_files = self._format_files_for_response(files)
        
        return {
            "success": True,
            "files": formatted_files,
            "count": len(formatted_files),
            "file_types": file_types,
            "message": f"Found {len(formatted_files)} {', '.join(file_types)} file(s)"
        }
    
    def _handle_detail_intent(self, user_id: str, message: str) -> Dict[str, Any]:
        """Handle detail intent - get specific file details"""
        logger.info(f"Getting file details for: {message}")
        
        # Try to extract file ID from message
        import re
        file_id_match = re.search(r'file[:\s]+([a-zA-Z0-9_-]+)', message, re.IGNORECASE)
        
        if not file_id_match:
            return {
                "success": False,
                "error": "Please specify the file ID"
            }
        
        file_id = file_id_match.group(1)
        
        result = get_file_by_id(user_id, file_id)
        
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Failed to get file details")
            }
        
        file_obj = result.get("file", {})
        
        return {
            "success": True,
            "file": {
                "id": file_obj.get("id"),
                "name": file_obj.get("name"),
                "type": file_obj.get("mimeType"),
                "size": file_obj.get("size"),
                "modified_time": file_obj.get("modifiedTime"),
                "created_time": file_obj.get("createdTime"),
                "url": file_obj.get("webViewLink"),
                "owners": file_obj.get("owners"),
            },
            "message": f"File: {file_obj.get('name')}"
        }
    
    def _format_files_for_response(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Format files for API response.
        
        Parameters
        ----------
        files : list
            Raw file objects from Google Drive
            
        Returns
        -------
        list
            Formatted file objects
        """
        formatted = []
        for file_obj in files:
            formatted.append({
                "id": file_obj.get("id"),
                "name": file_obj.get("name"),
                "type": self._get_file_type_label(file_obj.get("mimeType")),
                "mime_type": file_obj.get("mimeType"),
                "size": file_obj.get("size"),
                "modified_time": file_obj.get("modifiedTime"),
                "created_time": file_obj.get("createdTime"),
                "url": file_obj.get("webViewLink"),
                "relevance_score": file_obj.get("relevance_score", 0),
            })
        
        return formatted
    
    def _get_file_type_label(self, mime_type: str) -> str:
        """
        Get user-friendly file type label from MIME type.
        
        Parameters
        ----------
        mime_type : str
            MIME type string
            
        Returns
        -------
        str
            Human-readable file type
        """
        if not mime_type:
            return "File"
        
        type_map = {
            "application/vnd.google-apps.document": "Google Doc",
            "application/vnd.google-apps.spreadsheet": "Google Sheet",
            "application/vnd.google-apps.presentation": "Google Slides",
            "application/pdf": "PDF",
            "application/msword": "Word Document",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word Document",
            "application/vnd.ms-excel": "Excel Spreadsheet",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel Spreadsheet",
        }
        
        # Check for exact match
        if mime_type in type_map:
            return type_map[mime_type]
        
        # Check for image types
        if mime_type.startswith("image/"):
            return "Image"
        
        # Check for text types
        if mime_type.startswith("text/"):
            return "Text File"
        
        # Default
        return "File"

