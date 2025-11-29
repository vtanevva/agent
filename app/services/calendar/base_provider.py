"""
Abstract base class for calendar providers.

Defines the interface that all calendar providers (Google, Outlook, etc.) must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class CalendarProvider(ABC):
    """
    Abstract base class for calendar providers.
    
    All calendar providers must implement these methods to ensure
    consistent behavior across different calendar services.
    """
    
    def __init__(self, user_id: str):
        """
        Initialize the calendar provider.
        
        Parameters
        ----------
        user_id : str
            User identifier
        """
        self.user_id = user_id
        self.provider_name = self._get_provider_name()
    
    @abstractmethod
    def _get_provider_name(self) -> str:
        """Return the name of this provider (e.g., 'google', 'outlook')"""
        pass
    
    @abstractmethod
    def create_event(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
        attendees: Optional[List[str]] = None,
        timezone: str = "UTC",
        reminders: Optional[Dict[str, Any]] = None,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        Create a new calendar event.
        
        Returns
        -------
        dict
            Result with keys: success, event_id, html_link, summary, start, end, provider
        """
        pass
    
    @abstractmethod
    def list_events(
        self,
        max_results: int = 20,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        calendar_id: str = "primary",
        order_by: str = "startTime",
    ) -> Dict[str, Any]:
        """
        List calendar events.
        
        Returns
        -------
        dict
            Result with keys: success, events (list), count, provider
        """
        pass
    
    @abstractmethod
    def get_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        Get a specific event by ID.
        
        Returns
        -------
        dict
            Result with keys: success, event, provider
        """
        pass
    
    @abstractmethod
    def update_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        Update an existing event.
        
        Returns
        -------
        dict
            Result with keys: success, event_id, html_link, summary, provider
        """
        pass
    
    @abstractmethod
    def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: str = "all",
    ) -> Dict[str, Any]:
        """
        Delete an event.
        
        Returns
        -------
        dict
            Result with keys: success, event_id, provider
        """
        pass
    
    @abstractmethod
    def search_events(
        self,
        query: str,
        max_results: int = 20,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        Search for events matching a query.
        
        Returns
        -------
        dict
            Result with keys: success, events (list), count, query, provider
        """
        pass
    
    @abstractmethod
    def list_calendars(self) -> Dict[str, Any]:
        """
        List all accessible calendars.
        
        Returns
        -------
        dict
            Result with keys: success, calendars (list), count, provider
        """
        pass
    
    @abstractmethod
    def get_free_busy(
        self,
        time_min: str,
        time_max: str,
        calendars: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get free/busy information.
        
        Returns
        -------
        dict
            Result with keys: success, calendars (dict), time_min, time_max, provider
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
            # Try to list calendars as a connectivity check
            result = self.list_calendars()
            return result.get("success", False)
        except Exception:
            return False

