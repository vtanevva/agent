"""
Google Calendar provider implementation.

Uses Google Calendar API v3 via OAuth.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.utils.oauth_utils import load_google_credentials
from app.utils.logging_utils import get_logger
from .base_provider import CalendarProvider

logger = get_logger(__name__)


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar provider implementation"""
    
    def _get_provider_name(self) -> str:
        return "google"
    
    def _get_service(self):
        """Get authenticated Google Calendar service"""
        creds = load_google_credentials(self.user_id)
        return build("calendar", "v3", credentials=creds)
    
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
        """Create a new calendar event in Google Calendar"""
        try:
            service = self._get_service()
            
            # Build event object
            event = {
                "summary": summary,
                "description": description,
                "location": location,
                "start": {
                    "dateTime": start_time,
                    "timeZone": timezone,
                },
                "end": {
                    "dateTime": end_time,
                    "timeZone": timezone,
                },
            }
            
            # Add attendees if provided
            if attendees:
                event["attendees"] = [{"email": email} for email in attendees]
            
            # Add reminders if provided, otherwise use defaults
            if reminders:
                event["reminders"] = reminders
            else:
                event["reminders"] = {
                    "useDefault": False,
                    "overrides": [
                        {"method": "email", "minutes": 24 * 60},
                        {"method": "popup", "minutes": 30},
                    ],
                }
            
            # Create event
            created_event = service.events().insert(
                calendarId=calendar_id,
                body=event,
                sendUpdates="all" if attendees else "none",
            ).execute()
            
            return {
                "success": True,
                "event_id": created_event["id"],
                "html_link": created_event.get("htmlLink", ""),
                "summary": summary,
                "start": start_time,
                "end": end_time,
                "status": created_event.get("status", "confirmed"),
                "provider": self.provider_name,
                "provider_event_id": created_event["id"],
            }
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}", exc_info=True)
            return {"success": False, "error": f"Calendar API error: {e.reason}", "provider": self.provider_name}
        except Exception as e:
            logger.error(f"Error creating calendar event: {e}", exc_info=True)
            return {"success": False, "error": str(e), "provider": self.provider_name}
    
    def list_events(
        self,
        max_results: int = 20,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        calendar_id: str = "primary",
        order_by: str = "startTime",
    ) -> Dict[str, Any]:
        """List calendar events from Google Calendar"""
        try:
            logger.info(f"[GoogleCalendar] Fetching events for user {self.user_id}")
            service = self._get_service()
            
            # Default to next 30 days if no time range specified
            if not time_min:
                time_min = datetime.utcnow().isoformat() + "Z"
            
            if not time_max:
                time_max = (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"
            
            logger.info(f"[GoogleCalendar] Time range: {time_min} to {time_max}")
            
            # Fetch events
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy=order_by,
            ).execute()
            
            events = events_result.get("items", [])
            logger.info(f"[GoogleCalendar] Fetched {len(events)} events from Google Calendar API")
            
            formatted_events = []
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))
                
                formatted_event = {
                    "id": event["id"],
                    "summary": event.get("summary", "(No title)"),
                    "description": event.get("description", ""),
                    "location": event.get("location", ""),
                    "start": start,
                    "end": end,
                    "html_link": event.get("htmlLink", ""),
                    "status": event.get("status", "confirmed"),
                    "attendees": [
                        {
                            "email": att.get("email", ""),
                            "response_status": att.get("responseStatus", "needsAction"),
                        }
                        for att in event.get("attendees", [])
                    ],
                    "creator": event.get("creator", {}).get("email", ""),
                    "organizer": event.get("organizer", {}).get("email", ""),
                    "provider": self.provider_name,
                    "provider_event_id": event["id"],
                }
                formatted_events.append(formatted_event)
            
            return {
                "success": True,
                "events": formatted_events,
                "count": len(formatted_events),
                "time_min": time_min,
                "time_max": time_max,
                "provider": self.provider_name,
            }
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}", exc_info=True)
            
            # Check if Calendar API is not enabled
            if e.resp.status == 403 and "accessNotConfigured" in str(e):
                error_msg = (
                    "Google Calendar API is not enabled. "
                    "Enable it at: https://console.developers.google.com/apis/api/calendar-json.googleapis.com/overview"
                )
            else:
                error_msg = f"Calendar API error: {e.reason}"
            
            return {"success": False, "error": error_msg, "provider": self.provider_name}
        except Exception as e:
            logger.error(f"Error listing calendar events: {e}", exc_info=True)
            return {"success": False, "error": str(e), "provider": self.provider_name}
    
    def get_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Get detailed information about a specific calendar event"""
        try:
            service = self._get_service()
            
            event = service.events().get(
                calendarId=calendar_id,
                eventId=event_id,
            ).execute()
            
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            
            return {
                "success": True,
                "event": {
                    "id": event["id"],
                    "summary": event.get("summary", "(No title)"),
                    "description": event.get("description", ""),
                    "location": event.get("location", ""),
                    "start": start,
                    "end": end,
                    "html_link": event.get("htmlLink", ""),
                    "status": event.get("status", "confirmed"),
                    "attendees": [
                        {
                            "email": att.get("email", ""),
                            "display_name": att.get("displayName", ""),
                            "response_status": att.get("responseStatus", "needsAction"),
                            "organizer": att.get("organizer", False),
                        }
                        for att in event.get("attendees", [])
                    ],
                    "creator": event.get("creator", {}),
                    "organizer": event.get("organizer", {}),
                    "created": event.get("created"),
                    "updated": event.get("updated"),
                    "recurring": "recurrence" in event,
                    "recurrence": event.get("recurrence", []),
                    "reminders": event.get("reminders", {}),
                    "provider": self.provider_name,
                    "provider_event_id": event["id"],
                },
                "provider": self.provider_name,
            }
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}", exc_info=True)
            return {"success": False, "error": f"Calendar API error: {e.reason}", "provider": self.provider_name}
        except Exception as e:
            logger.error(f"Error getting event detail: {e}", exc_info=True)
            return {"success": False, "error": str(e), "provider": self.provider_name}
    
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
        try:
            service = self._get_service()
            
            # Get existing event
            event = service.events().get(
                calendarId=calendar_id,
                eventId=event_id,
            ).execute()
            
            # Update fields if provided
            if summary is not None:
                event["summary"] = summary
            if description is not None:
                event["description"] = description
            if location is not None:
                event["location"] = location
            if start_time is not None:
                event["start"]["dateTime"] = start_time
            if end_time is not None:
                event["end"]["dateTime"] = end_time
            if attendees is not None:
                event["attendees"] = [{"email": email} for email in attendees]
            
            # Update event
            updated_event = service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event,
                sendUpdates="all" if attendees else "none",
            ).execute()
            
            return {
                "success": True,
                "event_id": updated_event["id"],
                "html_link": updated_event.get("htmlLink", ""),
                "summary": updated_event.get("summary", ""),
                "status": updated_event.get("status", "confirmed"),
                "provider": self.provider_name,
                "provider_event_id": updated_event["id"],
            }
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}", exc_info=True)
            return {"success": False, "error": f"Calendar API error: {e.reason}", "provider": self.provider_name}
        except Exception as e:
            logger.error(f"Error updating calendar event: {e}", exc_info=True)
            return {"success": False, "error": str(e), "provider": self.provider_name}
    
    def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: str = "all",
    ) -> Dict[str, Any]:
        """Delete a calendar event"""
        try:
            service = self._get_service()
            
            service.events().delete(
                calendarId=calendar_id,
                eventId=event_id,
                sendUpdates=send_updates,
            ).execute()
            
            return {
                "success": True,
                "event_id": event_id,
                "message": "Event deleted successfully",
                "provider": self.provider_name,
            }
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}", exc_info=True)
            return {"success": False, "error": f"Calendar API error: {e.reason}", "provider": self.provider_name}
        except Exception as e:
            logger.error(f"Error deleting calendar event: {e}", exc_info=True)
            return {"success": False, "error": str(e), "provider": self.provider_name}
    
    def search_events(
        self,
        query: str,
        max_results: int = 20,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Search for calendar events matching a query"""
        try:
            service = self._get_service()
            
            if not time_min:
                time_min = datetime.utcnow().isoformat() + "Z"
            
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
                q=query,
            ).execute()
            
            events = events_result.get("items", [])
            
            formatted_events = []
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))
                
                formatted_event = {
                    "id": event["id"],
                    "summary": event.get("summary", "(No title)"),
                    "description": event.get("description", ""),
                    "location": event.get("location", ""),
                    "start": start,
                    "end": end,
                    "html_link": event.get("htmlLink", ""),
                    "status": event.get("status", "confirmed"),
                    "provider": self.provider_name,
                    "provider_event_id": event["id"],
                }
                formatted_events.append(formatted_event)
            
            return {
                "success": True,
                "events": formatted_events,
                "count": len(formatted_events),
                "query": query,
                "provider": self.provider_name,
            }
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}", exc_info=True)
            return {"success": False, "error": f"Calendar API error: {e.reason}", "provider": self.provider_name}
        except Exception as e:
            logger.error(f"Error searching calendar events: {e}", exc_info=True)
            return {"success": False, "error": str(e), "provider": self.provider_name}
    
    def list_calendars(self) -> Dict[str, Any]:
        """List all calendars accessible to the user"""
        try:
            service = self._get_service()
            
            calendars_result = service.calendarList().list().execute()
            calendars = calendars_result.get("items", [])
            
            formatted_calendars = []
            for calendar in calendars:
                formatted_calendar = {
                    "id": calendar["id"],
                    "summary": calendar.get("summary", ""),
                    "description": calendar.get("description", ""),
                    "primary": calendar.get("primary", False),
                    "access_role": calendar.get("accessRole", ""),
                    "time_zone": calendar.get("timeZone", ""),
                    "background_color": calendar.get("backgroundColor", ""),
                    "foreground_color": calendar.get("foregroundColor", ""),
                    "provider": self.provider_name,
                }
                formatted_calendars.append(formatted_calendar)
            
            return {
                "success": True,
                "calendars": formatted_calendars,
                "count": len(formatted_calendars),
                "provider": self.provider_name,
            }
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}", exc_info=True)
            return {"success": False, "error": f"Calendar API error: {e.reason}", "provider": self.provider_name}
        except Exception as e:
            logger.error(f"Error listing calendars: {e}", exc_info=True)
            return {"success": False, "error": str(e), "provider": self.provider_name}
    
    def get_free_busy(
        self,
        time_min: str,
        time_max: str,
        calendars: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get free/busy information for calendar(s)"""
        try:
            service = self._get_service()
            
            if not calendars:
                calendars = ["primary"]
            
            body = {
                "timeMin": time_min,
                "timeMax": time_max,
                "items": [{"id": cal_id} for cal_id in calendars],
            }
            
            freebusy_result = service.freebusy().query(body=body).execute()
            
            calendars_data = {}
            for cal_id, cal_data in freebusy_result.get("calendars", {}).items():
                busy_periods = cal_data.get("busy", [])
                calendars_data[cal_id] = {
                    "busy": busy_periods,
                    "errors": cal_data.get("errors", []),
                }
            
            return {
                "success": True,
                "calendars": calendars_data,
                "time_min": time_min,
                "time_max": time_max,
                "provider": self.provider_name,
            }
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}", exc_info=True)
            return {"success": False, "error": f"Calendar API error: {e.reason}", "provider": self.provider_name}
        except Exception as e:
            logger.error(f"Error getting free/busy info: {e}", exc_info=True)
            return {"success": False, "error": str(e), "provider": self.provider_name}
    
    def quick_add_event(
        self,
        text: str,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Quick add an event using natural language"""
        try:
            service = self._get_service()
            
            event = service.events().quickAdd(
                calendarId=calendar_id,
                text=text,
            ).execute()
            
            return {
                "success": True,
                "event_id": event["id"],
                "html_link": event.get("htmlLink", ""),
                "summary": event.get("summary", ""),
                "start": event["start"].get("dateTime", event["start"].get("date")),
                "end": event["end"].get("dateTime", event["end"].get("date")),
                "provider": self.provider_name,
                "provider_event_id": event["id"],
            }
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}", exc_info=True)
            return {"success": False, "error": f"Calendar API error: {e.reason}", "provider": self.provider_name}
        except Exception as e:
            logger.error(f"Error quick-adding event: {e}", exc_info=True)
            return {"success": False, "error": str(e), "provider": self.provider_name}

