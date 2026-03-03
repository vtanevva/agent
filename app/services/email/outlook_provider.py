"""
Outlook email provider implementation.

Uses Microsoft Graph API for Office 365/Outlook.com email integration.
"""

import json
import requests
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.utils.logging_utils import get_logger
from app.db.collections import get_tokens_collection
from .base_provider import EmailProvider
from .common import (
    lookup_contact_emails,
    normalize_email_format,
    store_email_metadata,
    extract_email_from_header,
)

logger = get_logger(__name__)


class OutlookProvider(EmailProvider):
    """Outlook email provider implementation using Microsoft Graph API"""
    
    GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"
    
    def _get_provider_name(self) -> str:
        return "outlook"
    
    def _get_access_token(self) -> Optional[str]:
        """Get Outlook access token from database (with automatic refresh)"""
        try:
            from app.utils.oauth_utils import load_outlook_token
            
            token_data = load_outlook_token(self.user_id)
            if not token_data:
                return None
            
            return token_data.get("access_token")
            
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
                return {
                    "success": False,
                    "error": f"Unsupported method: {method}",
                    "provider": self.provider_name,
                }
            
            if response.status_code == 204:  # No content (successful delete)
                return {"success": True, "provider": self.provider_name}
            
            if response.status_code >= 400:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", response.text)
                return {
                    "success": False,
                    "error": error_msg,
                    "provider": self.provider_name,
                }
            
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"Outlook API request error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "provider": self.provider_name,
            }
        except Exception as e:
            logger.error(f"Error making Outlook API request: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "provider": self.provider_name,
            }
    
    def list_recent_emails(
        self,
        max_results: int = 5,
        from_email: Optional[str] = None,
        contact_name: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """List recent emails from Outlook inbox"""
        # Look up contact emails if contact_name provided
        contact_emails = []
        if contact_name and not from_email:
            contact_emails = lookup_contact_emails(self.user_id, contact_name)
        elif from_email:
            contact_emails = [from_email]
        
        # Build filter for Outlook API
        params = {
            "$top": max_results,
            "$orderby": "receivedDateTime desc",
            "$select": "id,conversationId,subject,from,bodyPreview,receivedDateTime",
        }
        
        # Add filter by sender if provided
        if contact_emails:
            # Outlook filter: from/emailAddress/address eq 'email@example.com'
            if len(contact_emails) == 1:
                params["$filter"] = f"from/emailAddress/address eq '{contact_emails[0]}'"
            else:
                # Multiple emails - use OR
                filter_parts = [f"from/emailAddress/address eq '{email}'" for email in contact_emails]
                params["$filter"] = " or ".join(filter_parts)
        
        # Make API request
        result = self._make_request("GET", "/me/mailFolders/inbox/messages", params=params)
        
        if not result.get("success", True) or "value" not in result:
            return result
        
        messages = result.get("value", [])
        items = []
        
        for idx, msg in enumerate(messages, start=1):
            # Normalize Outlook format to common format
            normalized = normalize_email_format(msg, self.provider_name)
            normalized["idx"] = idx
            
            # Extract from address for storage
            from_field = msg.get("from", {})
            if isinstance(from_field, dict):
                email_address = from_field.get("emailAddress", {})
                name = email_address.get("name", "")
                email = email_address.get("address", "")
                from_address = f"{name} <{email}>" if name and email else (email or name or "")
            else:
                from_address = str(from_field)
            
            # Store metadata in database
            store_email_metadata(
                user_id=self.user_id,
                thread_id=normalized["threadId"],
                from_address=from_address,
                subject=normalized["subject"],
                snippet=normalized["snippet"],
                source=self.provider_name,
            )
            
            items.append(normalized)
        
        return {
            "success": True,
            "emails": items,
            "count": len(items),
            "provider": self.provider_name,
        }
    
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> Dict[str, Any]:
        """Send email via Outlook"""
        # Build message payload for Microsoft Graph API
        message = {
            "message": {
                "subject": subject or "(No subject)",
                "body": {
                    "contentType": "text",
                    "content": body,
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to,
                        }
                    }
                ],
            }
        }
        
        result = self._make_request("POST", "/me/messages", json_data=message)
        
        if not result.get("success", True):
            return result
        
        # Send the message
        message_id = result.get("id", "")
        send_result = self._make_request("POST", f"/me/messages/{message_id}/send")
        
        if not send_result.get("success", True):
            return send_result
        
        return {
            "success": True,
            "message_id": message_id,
            "provider": self.provider_name,
        }
    
    def reply_email(
        self,
        thread_id: str,
        to: str,
        body: str,
        subj_prefix: str = "Re:",
    ) -> Dict[str, Any]:
        """Reply to email via Outlook"""
        # First, get the original message to get subject
        msg_result = self._make_request("GET", f"/me/messages/{thread_id}")
        
        if not msg_result.get("success", True):
            return msg_result
        
        original_subject = msg_result.get("subject", "(No subject)")
        if subj_prefix not in original_subject:
            subject = f"{subj_prefix} {original_subject}"
        else:
            subject = original_subject
        
        # Build reply message
        reply_message = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "text",
                    "content": body,
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to,
                        }
                    }
                ],
            }
        }
        
        # Create reply
        create_result = self._make_request("POST", f"/me/messages/{thread_id}/reply", json_data=reply_message)
        
        if not create_result.get("success", True):
            return create_result
        
        return {
            "success": True,
            "message_id": create_result.get("id", ""),
            "thread_id": thread_id,
            "provider": self.provider_name,
        }
    
    def get_thread_detail(
        self,
        thread_id: str,
    ) -> Dict[str, Any]:
        """Get message detail from Outlook"""
        # Get message details
        result = self._make_request("GET", f"/me/messages/{thread_id}?$select=subject,from,receivedDateTime,body")
        
        if not result.get("success", True):
            return result
        
        # Extract data
        subject = result.get("subject", "(No subject)")
        
        from_field = result.get("from", {})
        if isinstance(from_field, dict):
            email_address = from_field.get("emailAddress", {})
            name = email_address.get("name", "")
            email = email_address.get("address", "")
            from_address = f"{name} <{email}>" if name and email else (email or name or "")
        else:
            from_address = str(from_field)
        
        date = result.get("receivedDateTime", "")
        
        # Extract body
        body_data = result.get("body", {})
        body = body_data.get("content", "") if isinstance(body_data, dict) else ""
        
        # Clean HTML if present
        if body_data.get("contentType") == "html":
            import re
            from html import unescape
            # Simple HTML stripping
            body = re.sub(r'<[^>]+>', '', body)
            body = unescape(body)
        
        return {
            "success": True,
            "message_id": thread_id,
            "thread_id": thread_id,
            "subject": subject,
            "from": from_address,
            "date": date,
            "body": body.strip(),
            "provider": self.provider_name,
        }
    
    def search_emails(
        self,
        query: str,
        max_results: int = 20,
    ) -> Dict[str, Any]:
        """Search emails in Outlook"""
        params = {
            "$top": max_results,
            "$orderby": "receivedDateTime desc",
            "$select": "id,conversationId,subject,from,bodyPreview,receivedDateTime",
            "$search": f'"{query}"',  # Outlook search syntax
        }
        
        result = self._make_request("GET", "/me/messages", params=params)
        
        if not result.get("success", True) or "value" not in result:
            return result
        
        messages = result.get("value", [])
        items = []
        
        for msg in messages:
            normalized = normalize_email_format(msg, self.provider_name)
            items.append(normalized)
        
        return {
            "success": True,
            "emails": items,
            "count": len(items),
            "query": query,
            "provider": self.provider_name,
        }

