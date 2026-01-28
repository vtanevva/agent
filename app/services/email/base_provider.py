"""
Abstract base class for email providers.

Defines the interface that all email providers (Gmail, Outlook, etc.) must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class EmailProvider(ABC):
    """
    Abstract base class for email providers.
    
    All email providers must implement these methods to ensure
    consistent behavior across different email services.
    """
    
    def __init__(self, user_id: str):
        """
        Initialize the email provider.
        
        Parameters
        ----------
        user_id : str
            User identifier
        """
        self.user_id = user_id
        self.provider_name = self._get_provider_name()
    
    @abstractmethod
    def _get_provider_name(self) -> str:
        """Return the name of this provider (e.g., 'gmail', 'outlook')"""
        pass
    
    @abstractmethod
    def list_recent_emails(
        self,
        max_results: int = 5,
        from_email: Optional[str] = None,
        contact_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List recent emails from inbox.
        
        Returns
        -------
        dict
            Result with keys: success, emails (list), count, provider
            Each email in list has: threadId, from, subject, snippet
        """
        pass
    
    @abstractmethod
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> Dict[str, Any]:
        """
        Send a new email.
        
        Returns
        -------
        dict
            Result with keys: success, message_id, provider
        """
        pass
    
    @abstractmethod
    def reply_email(
        self,
        thread_id: str,
        to: str,
        body: str,
        subj_prefix: str = "Re:",
    ) -> Dict[str, Any]:
        """
        Reply to an existing email thread.
        
        Parameters
        ----------
        thread_id : str
            Thread ID (or message ID for Outlook)
        to : str
            Recipient email address
        body : str
            Reply body
        subj_prefix : str
            Subject prefix (default: "Re:")
            
        Returns
        -------
        dict
            Result with keys: success, message_id, thread_id, provider
        """
        pass
    
    @abstractmethod
    def get_thread_detail(
        self,
        thread_id: str,
    ) -> Dict[str, Any]:
        """
        Get detailed information about an email thread.
        
        Returns
        -------
        dict
            Result with keys: success, subject, from, date, body, provider
        """
        pass
    
    @abstractmethod
    def search_emails(
        self,
        query: str,
        max_results: int = 20,
    ) -> Dict[str, Any]:
        """
        Search for emails matching a query.
        
        Returns
        -------
        dict
            Result with keys: success, emails (list), count, query, provider
        """
        pass
    
    def is_connected(self) -> bool:
        """
        Check if the provider is connected and has valid credentials.
        
        Returns
        -------
        bool
            True if connected, False otherwise
        """
        try:
            # Try to list emails as a connectivity check
            result = self.list_recent_emails(max_results=1)
            return result.get("success", False)
        except Exception:
            return False



