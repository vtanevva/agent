"""
Outlook Calendar provider implementation.

Uses Microsoft Graph API for Office 365/Outlook.com calendar integration.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import requests

from app.utils.logging_utils import get_logger
from app.db.collections import get_tokens_collection
from .base_provider import CalendarProvider

logger = get_logger(__name__)


class OutlookCalendarProvider(CalendarProvider):
    """Outlook Calendar provider implementation using Microsoft Graph API"""
    
    GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"
    
    def _get_provider_name(self) -> str:
        return "outlook"
    
    def _get_access_token(self) -> Optional[str]:
        """Get Outlook access token from database"""
        try:
            tokens_col = get_tokens_collection()
            if tokens_col is None:
                return None
            
            token_doc = tokens_col.find_one({
                "user_id": self.user_id,
                "provider": "outlook"
            })
            
            if not token_doc:
                return None
            
            # TODO: Add token refresh logic here when token is expired
            # Check if token_doc['expires_at'] < datetime.utcnow()
            # If expired, refresh using token_doc['refresh_token']
            
            return token_doc.get("access_token")
            
        except Exception as e:
            logger.error(f"Error getting Outlook access token: {e}", exc_info=True)
            return None
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make a request to Microsoft Graph API"""
        access_token = self._get_access_token()
        if not access_token:
            return {
                "success": False,
                "error": "Not connected to Outlook. Please authenticate first.",
                "provider": self.provider_name,
            }
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        url = f"{self.GRAPH_API_ENDPOINT}{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=json_data, timeout=30)
            elif method == "PATCH":
                response = requests.patch(url, headers=headers, json=json_data, timeout=30)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=30)
            else:
                return {"success": False, "error": f"Unsupported method: {method}", "provider": self.provider_name}
            
            if response.status_code == 204:  # No content (successful delete)
                return {"success": True, "provider": self.provider_name}
            
            if response.status_code >= 400:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", response.text)
                return {"success": False, "error": error_msg, "provider": self.provider_name}
            
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"Outlook API request error: {e}", exc_info=True)
            return {"success": False, "error": str(e), "provider": self.provider_name}
        except Exception as e:
            logger.error(f"Error making Outlook API request: {e}", exc_info=True)
            return {"success": False, "error": str(e), "provider": self.provider_name}
    
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
        """Create a new calendar event in Outlook"""
        # Build event object for Microsoft Graph API
        event_data = {
            "subject": summary,
            "body": {
                "contentType": "Text",
                "content": description,
            },
            "start": {
                "dateTime": start_time,
                "timeZone": timezone,
            },
            "end": {
                "dateTime": end_time,
                "timeZone": timezone,
            },
            "location": {
                "displayName": location,
            },
        }
        
        # Add attendees if provided
        if attendees:
            event_data["attendees"] = [
                {
                    "emailAddress": {"address": email},
                    "type": "required",
                }
                for email in attendees
            ]
        
        # Add reminders (Outlook uses "isReminderOn" and "reminderMinutesBeforeStart")
        if reminders and isinstance(reminders, dict):
            event_data["isReminderOn"] = reminders.get("enabled", True)
            event_data["reminderMinutesBeforeStart"] = reminders.get("minutes", 15)
        else:
            event_data["isReminderOn"] = True
            event_data["reminderMinutesBeforeStart"] = 15
        
        # Use calendar_id or default to primary
        endpoint = "/me/calendar/events" if calendar_id == "primary" else f"/me/calendars/{calendar_id}/events"
        
        result = self._make_request("POST", endpoint, json_data=event_data)
        
        if not result.get("success", True):  # If explicit failure
            return result
        
        # Parse successful response
        return {
            "success": True,
            "event_id": result.get("id"),
            "html_link": result.get("webLink", ""),
            "summary": result.get("subject", summary),
            "start": result.get("start", {}).get("dateTime", start_time),
            "end": result.get("end", {}).get("dateTime", end_time),
            "status": "confirmed",
            "provider": self.provider_name,
            "provider_event_id": result.get("id"),
        }
    
    def list_events(
        self,
        max_results: int = 20,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        calendar_id: str = "primary",
        order_by: str = "startTime",
    ) -> Dict[str, Any]:
        """List calendar events from Outlook"""
        # Build query parameters
        params = {
            "$top": max_results,
            "$orderby": "start/dateTime" if order_by == "startTime" else "lastModifiedDateTime",
        }
        
        # Add time filters if provided
        filters = []
        if time_min:
            # Remove 'Z' suffix and format for Outlook
            time_min_clean = time_min.rstrip("Z")
            filters.append(f"start/dateTime ge '{time_min_clean}'")
        if time_max:
            time_max_clean = time_max.rstrip("Z")
            filters.append(f"end/dateTime le '{time_max_clean}'")
        
        if filters:
            params["$filter"] = " and ".join(filters)
        
        endpoint = "/me/calendar/events" if calendar_id == "primary" else f"/me/calendars/{calendar_id}/events"
        
        result = self._make_request("GET", endpoint, params=params)
        
        if not result.get("success", True):
            return result
        
        events = result.get("value", [])
        
        formatted_events = []
        for event in events:
            formatted_event = {
                "id": event.get("id"),
                "summary": event.get("subject", "(No title)"),
                "description": event.get("body", {}).get("content", ""),
                "location": event.get("location", {}).get("displayName", ""),
                "start": event.get("start", {}).get("dateTime", ""),
                "end": event.get("end", {}).get("dateTime", ""),
                "html_link": event.get("webLink", ""),
                "status": "confirmed",
                "attendees": [
                    {
                        "email": att.get("emailAddress", {}).get("address", ""),
                        "response_status": att.get("status", {}).get("response", "none"),
                    }
                    for att in event.get("attendees", [])
                ],
                "creator": event.get("organizer", {}).get("emailAddress", {}).get("address", ""),
                "organizer": event.get("organizer", {}).get("emailAddress", {}).get("address", ""),
                "provider": self.provider_name,
                "provider_event_id": event.get("id"),
            }
            formatted_events.append(formatted_event)
        
        return {
            "success": True,
            "events": formatted_events,
            "count": len(formatted_events),
            "time_min": time_min or "",
            "time_max": time_max or "",
            "provider": self.provider_name,
        }
    
    def get_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Get detailed information about a specific calendar event"""
        endpoint = f"/me/events/{event_id}"
        
        result = self._make_request("GET", endpoint)
        
        if not result.get("success", True):
            return result
        
        event = result
        
        return {
            "success": True,
            "event": {
                "id": event.get("id"),
                "summary": event.get("subject", "(No title)"),
                "description": event.get("body", {}).get("content", ""),
                "location": event.get("location", {}).get("displayName", ""),
                "start": event.get("start", {}).get("dateTime", ""),
                "end": event.get("end", {}).get("dateTime", ""),
                "html_link": event.get("webLink", ""),
                "status": "confirmed",
                "attendees": [
                    {
                        "email": att.get("emailAddress", {}).get("address", ""),
                        "display_name": att.get("emailAddress", {}).get("name", ""),
                        "response_status": att.get("status", {}).get("response", "none"),
                        "organizer": att.get("type", "") == "organizer",
                    }
                    for att in event.get("attendees", [])
                ],
                "creator": event.get("organizer", {}).get("emailAddress", {}),
                "organizer": event.get("organizer", {}).get("emailAddress", {}),
                "created": event.get("createdDateTime"),
                "updated": event.get("lastModifiedDateTime"),
                "recurring": event.get("recurrence") is not None,
                "recurrence": event.get("recurrence", {}),
                "reminders": {
                    "enabled": event.get("isReminderOn", False),
                    "minutes": event.get("reminderMinutesBeforeStart", 15),
                },
                "provider": self.provider_name,
                "provider_event_id": event.get("id"),
            },
            "provider": self.provider_name,
        }
    
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
        """Update an existing calendar event"""
        # Build update data
        update_data = {}
        
        if summary is not None:
            update_data["subject"] = summary
        if description is not None:
            update_data["body"] = {
                "contentType": "Text",
                "content": description,
            }
        if location is not None:
            update_data["location"] = {
                "displayName": location,
            }
        if start_time is not None:
            update_data["start"] = {
                "dateTime": start_time,
                "timeZone": "UTC",
            }
        if end_time is not None:
            update_data["end"] = {
                "dateTime": end_time,
                "timeZone": "UTC",
            }
        if attendees is not None:
            update_data["attendees"] = [
                {
                    "emailAddress": {"address": email},
                    "type": "required",
                }
                for email in attendees
            ]
        
        endpoint = f"/me/events/{event_id}"
        
        result = self._make_request("PATCH", endpoint, json_data=update_data)
        
        if not result.get("success", True):
            return result
        
        return {
            "success": True,
            "event_id": result.get("id"),
            "html_link": result.get("webLink", ""),
            "summary": result.get("subject", ""),
            "status": "confirmed",
            "provider": self.provider_name,
            "provider_event_id": result.get("id"),
        }
    
    def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: str = "all",
    ) -> Dict[str, Any]:
        """Delete a calendar event"""
        endpoint = f"/me/events/{event_id}"
        
        result = self._make_request("DELETE", endpoint)
        
        if result.get("success"):
            return {
                "success": True,
                "event_id": event_id,
                "message": "Event deleted successfully",
                "provider": self.provider_name,
            }
        
        return result
    
    def search_events(
        self,
        query: str,
        max_results: int = 20,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Search for calendar events matching a query"""
        params = {
            "$top": max_results,
            "$search": f'"{query}"',
            "$orderby": "start/dateTime",
        }
        
        # Add time filters
        filters = []
        if time_min:
            time_min_clean = time_min.rstrip("Z")
            filters.append(f"start/dateTime ge '{time_min_clean}'")
        if time_max:
            time_max_clean = time_max.rstrip("Z")
            filters.append(f"end/dateTime le '{time_max_clean}'")
        
        if filters:
            params["$filter"] = " and ".join(filters)
        
        endpoint = "/me/calendar/events" if calendar_id == "primary" else f"/me/calendars/{calendar_id}/events"
        
        result = self._make_request("GET", endpoint, params=params)
        
        if not result.get("success", True):
            return result
        
        events = result.get("value", [])
        
        formatted_events = []
        for event in events:
            formatted_event = {
                "id": event.get("id"),
                "summary": event.get("subject", "(No title)"),
                "description": event.get("body", {}).get("content", ""),
                "location": event.get("location", {}).get("displayName", ""),
                "start": event.get("start", {}).get("dateTime", ""),
                "end": event.get("end", {}).get("dateTime", ""),
                "html_link": event.get("webLink", ""),
                "status": "confirmed",
                "provider": self.provider_name,
                "provider_event_id": event.get("id"),
            }
            formatted_events.append(formatted_event)
        
        return {
            "success": True,
            "events": formatted_events,
            "count": len(formatted_events),
            "query": query,
            "provider": self.provider_name,
        }
    
    def list_calendars(self) -> Dict[str, Any]:
        """List all calendars accessible to the user"""
        endpoint = "/me/calendars"
        
        result = self._make_request("GET", endpoint)
        
        if not result.get("success", True):
            return result
        
        calendars = result.get("value", [])
        
        formatted_calendars = []
        for calendar in calendars:
            formatted_calendar = {
                "id": calendar.get("id"),
                "summary": calendar.get("name", ""),
                "description": "",
                "primary": calendar.get("isDefaultCalendar", False),
                "access_role": calendar.get("canEdit", False) and "owner" or "reader",
                "time_zone": "",
                "background_color": calendar.get("color", ""),
                "foreground_color": "",
                "provider": self.provider_name,
            }
            formatted_calendars.append(formatted_calendar)
        
        return {
            "success": True,
            "calendars": formatted_calendars,
            "count": len(formatted_calendars),
            "provider": self.provider_name,
        }
    
    def get_free_busy(
        self,
        time_min: str,
        time_max: str,
        calendars: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get free/busy information for calendar(s)"""
        # Microsoft Graph uses getSchedule endpoint
        # Note: This requires Calendars.Read.Shared permission
        
        request_data = {
            "schedules": calendars or ["primary"],
            "startTime": {
                "dateTime": time_min.rstrip("Z"),
                "timeZone": "UTC",
            },
            "endTime": {
                "dateTime": time_max.rstrip("Z"),
                "timeZone": "UTC",
            },
            "availabilityViewInterval": 60,  # 60 minutes
        }
        
        endpoint = "/me/calendar/getSchedule"
        
        result = self._make_request("POST", endpoint, json_data=request_data)
        
        if not result.get("success", True):
            return result
        
        schedules = result.get("value", [])
        
        calendars_data = {}
        for schedule in schedules:
            cal_id = schedule.get("scheduleId", "")
            busy_periods = [
                {
                    "start": item.get("start", {}).get("dateTime", ""),
                    "end": item.get("end", {}).get("dateTime", ""),
                }
                for item in schedule.get("scheduleItems", [])
            ]
            calendars_data[cal_id] = {
                "busy": busy_periods,
                "errors": schedule.get("error", {}) and [schedule.get("error")] or [],
            }
        
        return {
            "success": True,
            "calendars": calendars_data,
            "time_min": time_min,
            "time_max": time_max,
            "provider": self.provider_name,
        }

