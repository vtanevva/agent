"""
GmailAgent - handles email-related requests.

This agent:
1. Detects what the user wants (list emails, reply, send, etc.)
2. Calls appropriate tools directly (no external agent_core)
3. Returns formatted responses
"""

import json
import re
from typing import Dict, Any, Optional, List

from app.tools.email import (
    list_recent_emails,
    get_thread_detail,
    reply_email,
    send_email,
)
from app.services.contacts_service import resolve_contact_email
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


class GmailAgent:
    """
    Agent for handling Gmail operations.
    
    Directly calls tools based on user intent without using agent_core.
    """
    
    def __init__(self, llm_service, memory_service):
        """
        Initialize GmailAgent.
        
        Parameters
        ----------
        llm_service : LLMService
            LLM service for text generation
        memory_service : MemoryService
            Memory service for conversation history
        """
        self.llm_service = llm_service
        self.memory_service = memory_service
    
    def _detect_email_intent(self, message: str) -> str:
        """
        Detect what the user wants to do with email.
        
        Returns: "list", "reply", "send", "detail", or "unknown"
        """
        lower = message.lower()
        
        # List emails
        if any(phrase in lower for phrase in [
            "recent email", "last email", "latest email", "show my emails",
            "show inbox", "check emails", "check my emails", "check inbox",
            "past email", "old emails", "show me emails", "list emails",
            "emails from", "show emails from", "reply to"  # "reply to X" means list their emails
        ]):
            return "list"
        
        # Send new email
        if any(phrase in lower for phrase in [
            "send email to", "email to", "compose email", "write email"
        ]):
            return "send"
        
        # Reply to thread
        if "thread" in lower and any(phrase in lower for phrase in ["reply", "respond"]):
            return "reply"
        
        # Get thread detail
        if any(phrase in lower for phrase in ["show thread", "thread detail", "open thread"]):
            return "detail"
        
        return "unknown"
    
    def _extract_contact_name(self, message: str) -> Optional[str]:
        """
        Extract contact name from phrases like:
        - "reply to marin"
        - "emails from deya"
        - "show me emails from john"
        """
        lower = message.lower()
        
        # Pattern: "reply to X" or "emails from X" or "show emails from X"
        patterns = [
            r'reply to\s+([a-zA-Z\s\-]+?)(?:\s|$)',
            r'emails? from\s+([a-zA-Z\s\-]+?)(?:\s|$)',
            r'show\s+(?:me\s+)?emails?\s+from\s+([a-zA-Z\s\-]+?)(?:\s|$)',
            r'check\s+emails?\s+from\s+([a-zA-Z\s\-]+?)(?:\s|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, lower)
            if match:
                name = match.group(1).strip()
                # Remove common trailing words
                name = re.sub(r'\s+(please|thanks|thank you)$', '', name, flags=re.IGNORECASE)
                return name
        
        return None
    
    def handle_chat(
        self,
        user_id: str,
        message: str,
        session_memory: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Handle an email-related chat message.
        
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
        str
            Response (may be JSON for UI to parse)
        """
        intent = self._detect_email_intent(message)
        logger.info(f"GmailAgent detected intent: {intent} for message: {message[:50]}")
        
        if intent == "list":
            # List recent emails, optionally filtered by contact
            contact_name = self._extract_contact_name(message)
            
            try:
                if contact_name:
                    logger.info(f"Listing emails from contact: {contact_name}")
                    result = list_recent_emails(
                        user_id=user_id,
                        max_results=5,
                        contact_name=contact_name
                    )
                else:
                    logger.info("Listing recent emails (no filter)")
                    result = list_recent_emails(user_id=user_id, max_results=5)
                
                # Return raw JSON for UI to parse
                return result
            except Exception as e:
                logger.error(f"Error listing emails: {e}", exc_info=True)
                return json.dumps([{
                    "error": "Failed to list emails",
                    "message": str(e)
                }])
        
        elif intent == "send":
            # Extract recipient and compose email
            # Support natural phrases like:
            #   "send an email to Marin - Fontys about the meeting"
            #   "email Marin about the report"
            #   "send email to marin@example.com"
            lower_msg = message.lower()
            raw_to = ""

            # Try several patterns in order of specificity
            patterns = [
                r"send\s+an\s+email\s+to\s+(.+)",   # send an email to X...
                r"send\s+email\s+to\s+(.+)",        # send email to X...
                r"send\s+an\s+email\s+(.+)",        # send an email X...
                r"email\s+(.+)",                    # email X...
            ]

            for pat in patterns:
                m = re.search(pat, message, re.IGNORECASE)
                if m:
                    candidate = m.group(1).strip()
                    # Strip common trailing phrases after the name/nickname
                    # e.g. "Marin about the meeting" -> "Marin"
                    split_tokens = [" about ", " regarding ", " re: ", " re ", " with ", " on ", " for "]
                    cand_lower = candidate.lower()
                    cut_idx = None
                    for tok in split_tokens:
                        pos = cand_lower.find(tok)
                        if pos != -1:
                            cut_idx = pos
                            break
                    if cut_idx is not None:
                        candidate = candidate[:cut_idx].strip()
                    raw_to = candidate
                    break

            # Fallback: simple "to X" extraction if patterns failed
            if not raw_to:
                m = re.search(r"\bto\s+([^\n,]+)", message, re.IGNORECASE)
                if m:
                    raw_to = m.group(1).strip()

            # Resolve nickname/name to actual email using contacts
            resolved_to = raw_to
            if raw_to:
                try:
                    resolve_result = resolve_contact_email(user_id=user_id, name_or_email=raw_to)
                    if resolve_result.get("success"):
                        resolved_to = resolve_result.get("resolved_email", raw_to)
                except Exception as e:
                    logger.warning(f"Failed to resolve contact email for '{raw_to}': {e}")
                    resolved_to = raw_to
            
            # Use LLM to generate subject and body
            prompt = (
                f"User wants to send an email to {raw_to or resolved_to}. "
                f"Message: {message}\n\nGenerate a brief subject line and email body."
            )
            
            try:
                llm_response = self.llm_service.chat_completion_text(
                    messages=[
                        {"role": "system", "content": "You are an email composition assistant. Generate professional email content."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=200
                )
                
                # Parse response into subject and body
                lines = llm_response.split("\n", 1)
                subject = lines[0].replace("Subject:", "").strip()
                body = lines[1].strip() if len(lines) > 1 else ""
                
                # Return compose modal data
                return json.dumps(
                    {
                        "action": "open_compose",
                        # Use resolved email so the Compose modal "To" field shows the real address
                        "to": resolved_to,
                        "subject": subject,
                        "body": body,
                    }
                )
            except Exception as e:
                logger.error(f"Error composing email: {e}", exc_info=True)
                return "I had trouble composing that email. Please try again."
        
        elif intent == "reply":
            # Reply to a thread (requires threadId)
            thread_match = re.search(r'thread[:\s]+([a-f0-9]+)', message, re.IGNORECASE)
            if not thread_match:
                return "Please specify the thread ID to reply to."
            
            thread_id = thread_match.group(1)
            # Extract reply body
            body_match = re.search(r':\s*(.+)$', message)
            body = body_match.group(1).strip() if body_match else ""
            
            if not body:
                return "Please provide the reply message."
            
            try:
                result = reply_email(
                    user_id=user_id,
                    thread_id=thread_id,
                    body=body
                )
                return result
            except Exception as e:
                logger.error(f"Error replying to email: {e}", exc_info=True)
                return f"Failed to send reply: {str(e)}"
        
        elif intent == "detail":
            # Get thread detail
            thread_match = re.search(r'thread[:\s]+([a-f0-9]+)', message, re.IGNORECASE)
            if not thread_match:
                return "Please specify the thread ID."
            
            thread_id = thread_match.group(1)
            
            try:
                result = get_thread_detail(user_id=user_id, thread_id=thread_id)
                return result
            except Exception as e:
                logger.error(f"Error getting thread detail: {e}", exc_info=True)
                return f"Failed to get thread details: {str(e)}"
        
        else:
            # Unknown intent - use LLM to generate a helpful response
            return "I can help you with your emails. Try asking me to:\n- Show recent emails\n- List emails from a specific person\n- Send an email\n- Reply to a thread"

