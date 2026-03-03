"""
Gmail provider implementation.

Wraps existing Gmail functionality into the provider interface.
"""

import json
import base64
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from app.utils.google_api_helpers import get_gmail_service
from app.utils.logging_utils import get_logger
from app.services.cache_service import (
    cache_email_list,
    get_cached_email_list,
    cache_thread_detail,
    get_cached_thread_detail,
)
from .base_provider import EmailProvider
from .common import (
    lookup_contact_emails,
    normalize_email_format,
    store_email_metadata,
    extract_email_from_header,
)

logger = get_logger(__name__)


class GmailProvider(EmailProvider):
    """Gmail provider implementation using Gmail API"""
    
    def _get_provider_name(self) -> str:
        return "gmail"
    
    def list_recent_emails(
        self,
        max_results: int = 5,
        from_email: Optional[str] = None,
        contact_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List recent emails from Gmail inbox"""
        try:
            svc = get_gmail_service(self.user_id)
        except Exception as e:
            return {
                "success": False,
                "error": f"Gmail service unavailable: {e}",
                "provider": self.provider_name,
            }
        
        # Look up contact emails if contact_name provided
        contact_emails = []
        if contact_name and not from_email:
            contact_emails = lookup_contact_emails(self.user_id, contact_name)
        elif from_email:
            contact_emails = [from_email]
        
        # Build Gmail query
        query = "in:inbox to:me -from:me -from:mailer-daemon@googlemail.com"
        if contact_emails:
            if len(contact_emails) == 1:
                query = f"{query} from:{contact_emails[0]}"
            else:
                email_list = " OR ".join(contact_emails)
                query = f"{query} from:({email_list})"
        
        # Check cache
        cached_result = get_cached_email_list(self.user_id, query, max_results)
        if cached_result:
            # Add source to cached results
            for item in cached_result:
                item["source"] = self.provider_name
            return {
                "success": True,
                "emails": cached_result,
                "count": len(cached_result),
                "provider": self.provider_name,
            }
        
        # Fetch from Gmail API
        try:
            resp = svc.users().messages().list(
                userId="me",
                q=query,
                maxResults=50,
            ).execute()
            
            messages = resp.get("messages", [])
            
            # Keep first message per thread
            threads_seen = OrderedDict()
            message_ids = [m["id"] for m in messages[:max_results * 2]]
            
            for m_id in message_ids:
                # Check cache
                cached_msg = get_cached_thread_detail(self.user_id, m_id)
                if cached_msg:
                    msg = cached_msg
                else:
                    msg = (
                        svc.users()
                        .messages()
                        .get(userId="me", id=m_id, format="metadata", metadataHeaders=["Subject", "From"])
                        .execute()
                    )
                    cache_thread_detail(self.user_id, m_id, msg)
                
                t_id = msg["threadId"]
                if t_id not in threads_seen:
                    threads_seen[t_id] = msg
                if len(threads_seen) >= max_results:
                    break
            
            # Build normalized email list
            items = []
            for idx, (t_id, msg) in enumerate(threads_seen.items(), start=1):
                hdrs = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
                from_header = hdrs.get("From", "")
                
                # Filter by contact emails if provided
                if contact_emails:
                    header_email = extract_email_from_header(from_header)
                    header_email_lower = header_email.lower()
                    matches = False
                    for contact_email in contact_emails:
                        if contact_email.lower() in header_email_lower or header_email_lower in contact_email.lower():
                            matches = True
                            break
                    if not matches:
                        continue
                
                email_data = {
                    "idx": idx,
                    "threadId": t_id,
                    "from": from_header,
                    "subject": hdrs.get("Subject", "(No subject)"),
                    "snippet": msg.get("snippet", "")[:120],
                }
                
                # Normalize and add source
                normalized = normalize_email_format(email_data, self.provider_name)
                normalized["idx"] = idx
                
                # Store metadata in database
                store_email_metadata(
                    user_id=self.user_id,
                    thread_id=t_id,
                    from_address=from_header,
                    subject=normalized["subject"],
                    snippet=normalized["snippet"],
                    source=self.provider_name,
                )
                
                items.append(normalized)
            
            # Cache the result
            cache_email_list(self.user_id, query, max_results, items)
            
            return {
                "success": True,
                "emails": items,
                "count": len(items),
                "provider": self.provider_name,
            }
            
        except Exception as e:
            logger.error(f"Error listing Gmail emails: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "provider": self.provider_name,
            }
    
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> Dict[str, Any]:
        """Send email via Gmail"""
        try:
            from email.mime.text import MIMEText
            from googleapiclient.errors import HttpError
            
            svc = get_gmail_service(self.user_id)
            
            mime = MIMEText(body)
            mime["to"] = to
            mime["subject"] = subject or "(No subject)"
            
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
            message = {"raw": raw}
            
            result = svc.users().messages().send(userId="me", body=message).execute()
            message_id = result.get("id", "")
            
            return {
                "success": True,
                "message_id": message_id,
                "provider": self.provider_name,
            }
            
        except HttpError as e:
            error_msg = f"Gmail API error: {e}"
            if e.resp.status == 403:
                error_msg = "Permission denied. Please check Gmail API permissions."
            elif e.resp.status == 400:
                error_msg = "Invalid request. Please check recipient email address."
            return {
                "success": False,
                "error": error_msg,
                "provider": self.provider_name,
            }
        except Exception as e:
            logger.error(f"Error sending Gmail: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "provider": self.provider_name,
            }
    
    def reply_email(
        self,
        thread_id: str,
        to: str,
        body: str,
        subj_prefix: str = "Re:",
    ) -> Dict[str, Any]:
        """Reply to email thread via Gmail"""
        try:
            from email.mime.text import MIMEText
            from googleapiclient.errors import HttpError
            
            svc = get_gmail_service(self.user_id)
            
            # Resolve messageId → threadId and get Subject
            try:
                msg_meta = (
                    svc.users()
                    .messages()
                    .get(
                        userId="me",
                        id=thread_id,
                        format="metadata",
                        metadataHeaders=["Subject", "Message-ID"],
                    )
                    .execute()
                )
                real_thread_id = msg_meta.get("threadId", thread_id)
                subj = next(
                    (h["value"] for h in msg_meta["payload"]["headers"] if h["name"] == "Subject"),
                    "(No subject)"
                )
            except HttpError as e:
                if e.resp.status in (400, 404):
                    # Assume we already had a threadId
                    thread_resp = (
                        svc.users()
                        .threads()
                        .get(userId="me", id=thread_id, format="metadata")
                        .execute()
                    )
                    real_thread_id = thread_id
                    first_msg = thread_resp["messages"][0]
                    subj = next(
                        (h["value"] for h in first_msg["payload"]["headers"] if h["name"] == "Subject"),
                        "(No subject)"
                    )
                    msg_meta = first_msg
                else:
                    raise
            
            # Build MIME reply
            mime = MIMEText(body)
            mime["to"] = to
            mime["subject"] = subj if subj_prefix in subj else f"{subj_prefix} {subj}"
            
            # Use Message-ID for threading
            msg_id = next(
                (h["value"] for h in msg_meta["payload"]["headers"] if h["name"] in ("Message-ID", "Message-Id")),
                None
            )
            if msg_id:
                mime["In-Reply-To"] = msg_id
                mime["References"] = msg_id
            
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
            result = svc.users().messages().send(
                userId="me",
                body={"raw": raw, "threadId": real_thread_id},
            ).execute()
            
            return {
                "success": True,
                "message_id": result.get("id", ""),
                "thread_id": real_thread_id,
                "provider": self.provider_name,
            }
            
        except Exception as e:
            logger.error(f"Error replying to Gmail: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "provider": self.provider_name,
            }
    
    def get_thread_detail(
        self,
        thread_id: str,
    ) -> Dict[str, Any]:
        """Get thread detail from Gmail"""
        try:
            from app.tools.email.detail import (
                _extract_plain_text,
                _clean_text,
                _strip_leading_subject,
            )
            
            svc = get_gmail_service(self.user_id)
            
            # Try as message first
            try:
                msg = (
                    svc.users()
                    .messages()
                    .get(userId="me", id=thread_id, format="full")
                    .execute()
                )
                msg_id = msg.get("id", thread_id)
                real_thread_id = msg.get("threadId", thread_id)
                payload = msg.get("payload", {})
                headers = payload.get("headers", [])
                header_map = {h["name"].lower(): h["value"] for h in headers}
                subject = header_map.get("subject", "(No subject)")
                sender = header_map.get("from", "")
                date = header_map.get("date", "")
                body = _clean_text(_extract_plain_text(payload).strip())
                body = _strip_leading_subject(body, subject)
                
                return {
                    "success": True,
                    "message_id": msg_id,
                    "thread_id": real_thread_id,
                    "subject": subject,
                    "from": sender,
                    "date": date,
                    "body": body,
                    "provider": self.provider_name,
                }
            except Exception:
                # Fallback to thread
                th = (
                    svc.users()
                    .threads()
                    .get(userId="me", id=thread_id, format="full")
                    .execute()
                )
                real_thread_id = th.get("id", thread_id)
                messages = th.get("messages", [])
                if not messages:
                    return {
                        "success": False,
                        "error": "Thread has no messages",
                        "provider": self.provider_name,
                    }
                
                last = messages[-1]
                msg_id = last.get("id", "")
                payload = last.get("payload", {})
                headers = payload.get("headers", [])
                header_map = {h["name"].lower(): h["value"] for h in headers}
                subject = header_map.get("subject", "(No subject)")
                sender = header_map.get("from", "")
                date = header_map.get("date", "")
                body = _clean_text(_extract_plain_text(payload).strip())
                body = _strip_leading_subject(body, subject)
                
                return {
                    "success": True,
                    "message_id": msg_id or real_thread_id,
                    "thread_id": real_thread_id,
                    "subject": subject,
                    "from": sender,
                    "date": date,
                    "body": body,
                    "provider": self.provider_name,
                }
                
        except Exception as e:
            logger.error(f"Error getting Gmail thread detail: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "provider": self.provider_name,
            }
    
    def search_emails(
        self,
        query: str,
        max_results: int = 20,
    ) -> Dict[str, Any]:
        """Search emails in Gmail"""
        try:
            svc = get_gmail_service(self.user_id)
            
            resp = svc.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results,
            ).execute()
            
            messages = resp.get("messages", [])
            items = []
            
            for msg_data in messages:
                msg = (
                    svc.users()
                    .messages()
                    .get(userId="me", id=msg_data["id"], format="metadata", metadataHeaders=["Subject", "From"])
                    .execute()
                )
                hdrs = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
                
                email_data = {
                    "threadId": msg["threadId"],
                    "from": hdrs.get("From", ""),
                    "subject": hdrs.get("Subject", "(No subject)"),
                    "snippet": msg.get("snippet", "")[:120],
                }
                
                normalized = normalize_email_format(email_data, self.provider_name)
                items.append(normalized)
            
            return {
                "success": True,
                "emails": items,
                "count": len(items),
                "query": query,
                "provider": self.provider_name,
            }
            
        except Exception as e:
            logger.error(f"Error searching Gmail: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "provider": self.provider_name,
            }



