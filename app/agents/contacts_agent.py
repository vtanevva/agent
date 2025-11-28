"""
Contacts Agent - manages contact-related tasks.

This agent is responsible for:
- Contact syncing from Gmail
- Contact search and lookup
- Contact notes and metadata
- Contact grouping and organization
"""

from typing import Optional, Dict, Any, List

from app.services.contacts_service import (
    sync_contacts,
    list_contacts,
    normalize_contact_names,
    archive_contact,
    update_contact,
    list_contact_groups,
    get_contact_detail,
    get_contact_conversations,
)
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


class ContactsAgent:
    """
    Agent for contact management tasks.
    
    Handles:
    - Syncing contacts from Gmail
    - Listing and searching contacts
    - Updating contact information
    - Managing contact groups
    - Retrieving contact details and history
    """
    
    def __init__(self, llm_service=None, memory_service=None):
        """
        Initialize the Contacts agent.
        
        Parameters
        ----------
        llm_service : LLMService, optional
            Service for LLM operations (for future conversational features)
        memory_service : MemoryService, optional
            Service for conversation memory
        """
        self.llm_service = llm_service
        self.memory_service = memory_service
        logger.info("ContactsAgent initialized")
    
    def handle_chat(
        self,
        user_id: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Handle contact-related chat messages.
        
        Detects contact queries in natural language.
        
        Parameters
        ----------
        user_id : str
            User identifier
        message : str
            User's message
        metadata : dict, optional
            Additional metadata
            
        Returns
        -------
        str
            Response message
        """
        logger.info(f"ContactsAgent handling request for user {user_id}")
        
        message_lower = message.lower()
        
        # Sync contacts
        if any(keyword in message_lower for keyword in ["sync", "import", "load contacts"]):
            result = self.sync(user_id)
            if result.get("success"):
                count = len(result.get("contacts", []))
                return f"✅ Synced {count} contacts from Gmail!"
            return f"❌ Failed to sync contacts: {result.get('error')}"
        
        # List contacts
        if any(keyword in message_lower for keyword in ["list contacts", "show contacts", "my contacts"]):
            result = self.list(user_id)
            if result.get("success"):
                contacts = result.get("contacts", [])
                if not contacts:
                    return "You have no contacts yet. Try syncing from Gmail first."
                
                # Show top 10
                lines = [f"📇 You have {len(contacts)} contact(s):\n"]
                for i, contact in enumerate(contacts[:10], 1):
                    name = contact.get("name", "(No name)")
                    email = contact.get("email", "")
                    lines.append(f"{i}. **{name}** - {email}")
                
                if len(contacts) > 10:
                    lines.append(f"\n... and {len(contacts) - 10} more")
                
                return "\n".join(lines)
            return f"❌ Failed to list contacts: {result.get('error')}"
        
        # Search for specific contact
        if "contact" in message_lower and ("who is" in message_lower or "find" in message_lower):
            return "Please provide the contact's email or name to search."
        
        # Fallback: use LLM if available
        if self.llm_service:
            return self._handle_with_llm(user_id, message)
        
        return (
            "I can help you manage contacts. Try:\n"
            "- 'Sync my contacts'\n"
            "- 'Show my contacts'\n"
            "- 'List contact groups'"
        )
    
    def _handle_with_llm(self, user_id: str, message: str) -> str:
        """Use LLM to understand and respond to contact requests."""
        logger.debug("Using LLM to handle contact request")
        
        system_prompt = """You are a contacts assistant. Help the user manage their contacts.

You can help with:
- Syncing contacts from Gmail
- Listing contacts
- Searching for specific contacts
- Managing contact groups
- Updating contact information

Be helpful and concise."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]
        
        try:
            response = self.llm_service.chat_completion_text(
                messages=messages,
                temperature=0.5,
            )
            return response
        except Exception as e:
            logger.error(f"LLM error in contacts agent: {e}", exc_info=True)
            return (
                "I can help you with contact management. "
                "Try asking me to 'sync contacts' or 'show my contacts'."
            )
    
    # ──────────────────────────────────────────────────────────────────
    # Direct Contact Operations (wrapper methods for service layer)
    # ──────────────────────────────────────────────────────────────────
    
    def sync(
        self,
        user_id: str,
        max_sent: int = 1000,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Sync contacts from Gmail Sent messages.
        
        Parameters
        ----------
        user_id : str
            User identifier
        max_sent : int
            Maximum number of sent emails to scan
        force : bool
            Force re-sync even if already initialized
            
        Returns
        -------
        dict
            Result with success status and contacts list
        """
        logger.info(f"Syncing contacts for user {user_id}")
        return sync_contacts(user_id, max_sent, force)
    
    def list(
        self,
        user_id: str,
        include_archived: bool = False,
    ) -> Dict[str, Any]:
        """
        List all contacts for a user.
        
        Parameters
        ----------
        user_id : str
            User identifier
        include_archived : bool
            Include archived contacts
            
        Returns
        -------
        dict
            Result with contacts list
        """
        logger.info(f"Listing contacts for user {user_id}")
        return list_contacts(user_id, include_archived)
    
    def normalize_names(self, user_id: str) -> Dict[str, Any]:
        """
        Normalize contact names (fill missing from email).
        
        Parameters
        ----------
        user_id : str
            User identifier
            
        Returns
        -------
        dict
            Result with number of contacts updated
        """
        logger.info(f"Normalizing contact names for user {user_id}")
        return normalize_contact_names(user_id)
    
    def archive(
        self,
        user_id: str,
        email: str,
        archived: bool = True,
    ) -> Dict[str, Any]:
        """
        Archive or unarchive a contact.
        
        Parameters
        ----------
        user_id : str
            User identifier
        email : str
            Contact email
        archived : bool
            Archive (True) or unarchive (False)
            
        Returns
        -------
        dict
            Result with success status
        """
        logger.info(f"Archiving contact {email} for user {user_id}")
        return archive_contact(user_id, email, archived)
    
    def update(
        self,
        user_id: str,
        email: str,
        name: Optional[str] = None,
        nickname: Optional[str] = None,
        groups: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Update contact information.
        
        Parameters
        ----------
        user_id : str
            User identifier
        email : str
            Contact email
        name : str, optional
            New name
        nickname : str, optional
            New nickname
        groups : list of str, optional
            New groups list
            
        Returns
        -------
        dict
            Result with updated contact
        """
        logger.info(f"Updating contact {email} for user {user_id}")
        return update_contact(user_id, email, name, nickname, groups)
    
    def list_groups(self, user_id: str) -> Dict[str, Any]:
        """
        List all contact groups for a user.
        
        Parameters
        ----------
        user_id : str
            User identifier
            
        Returns
        -------
        dict
            Result with groups list
        """
        logger.info(f"Listing contact groups for user {user_id}")
        return list_contact_groups(user_id)
    
    def get_detail(
        self,
        user_id: str,
        email: str,
    ) -> Dict[str, Any]:
        """
        Get detailed information about a contact.
        
        Includes last interaction, notes, and past conversations.
        
        Parameters
        ----------
        user_id : str
            User identifier
        email : str
            Contact email
            
        Returns
        -------
        dict
            Result with contact details
        """
        logger.info(f"Getting detail for contact {email}, user {user_id}")
        return get_contact_detail(user_id, email)
    
    def get_conversations(
        self,
        user_id: str,
        email: str,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Get all conversations related to a contact.
        
        Parameters
        ----------
        user_id : str
            User identifier
        email : str
            Contact email
        limit : int
            Maximum number of conversations
            
        Returns
        -------
        dict
            Result with conversations list
        """
        logger.info(f"Getting conversations for contact {email}, user {user_id}")
        return get_contact_conversations(user_id, email, limit)
