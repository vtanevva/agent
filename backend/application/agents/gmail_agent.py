"""
GmailAgent - handles email-related requests.
"""

import json
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.application.services import memory_service
from backend.application.services.core_backend_client import ingest_gmail
from backend.utils.logger import get_logger

logger = get_logger("gmail_agent")


class GmailAgent:
    def __init__(self, llm_service, memory_service):
        self.llm_service = llm_service
        self.memory_service = memory_service

    def _detect_email_intent(self, message: str) -> str:
        lower = message.lower()
        if any(phrase in lower for phrase in [
            "recent email", "last email", "latest email", "show my emails",
            "show inbox", "check emails", "check my emails", "check inbox",
            "past email", "old emails", "show me emails", "list emails",
            "emails from", "show emails from", "reply to",
        ]):
            return "list"
        if any(phrase in lower for phrase in [
            "send email to", "send an email to", "email to", "compose email",
            "write email", "send a message to", "send message to",
        ]):
            return "send"
        if "thread" in lower and any(phrase in lower for phrase in ["reply", "respond"]):
            return "reply"
        if any(phrase in lower for phrase in ["show thread", "thread detail", "open thread"]):
            return "detail"
        return "unknown"

    def _extract_recipient_and_message(self, message: str) -> Dict[str, str]:
        text = (message or "").strip()
        patterns = [
            r"send\s+(?:a\s+)?message\s+to\s+(?P<to>.+?)\s+(?:saying|that\s+says)\s+(?P<body>.+)$",
            r"send\s+(?:a\s+)?message\s+to\s+(?P<to>.+?)\s*:\s*(?P<body>.+)$",
            r"send\s+an?\s+email\s+to\s+(?P<to>.+?)\s+(?:saying|that\s+says)\s+(?P<body>.+)$",
            r"send\s+email\s+to\s+(?P<to>.+?)\s+(?:saying|that\s+says)\s+(?P<body>.+)$",
            r"email\s+(?P<to>.+?)\s+(?:saying|that\s+says)\s+(?P<body>.+)$",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return {"to": (m.group("to") or "").strip(), "body": (m.group("body") or "").strip()}

        recipient_patterns = [
            r"send\s+an?\s+email\s+to\s+(.+)",
            r"send\s+email\s+to\s+(.+)",
            r"send\s+(?:a\s+)?message\s+to\s+(.+)",
            r"email\s+(.+)",
        ]
        raw_to = ""
        for pat in recipient_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                candidate = (m.group(1) or "").strip()
                split_tokens = [" saying ", " that says ", " about ", " regarding ", " re: ", " re ", " with ", " on ", " for ", ":"]
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
        if raw_to:
            return {"to": raw_to, "body": ""}

        m = re.search(
            r"\bto\s+(?P<to>.+?)(?:\s+(?:saying|that\s+says|about|regarding|re:|with|on|for)\b|:|,|$)",
            text,
            re.IGNORECASE,
        )
        if m:
            return {"to": (m.group("to") or "").strip(), "body": ""}
        return {"to": "", "body": ""}

    def handle_chat(
        self,
        user_id: str,
        message: str,
        session_memory: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> str:
        context_bundle = None
        try:
            context_bundle = memory_service.retrieve_context_bundle(
                user_id=user_id,
                thread_id=None,
                query_text=message,
            )
        except Exception as e:
            logger.warning("User Awareness retrieval failed for GmailAgent: %s", e)

        intent = self._detect_email_intent(message)
        if intent == "send":
            extracted = self._extract_recipient_and_message(message)
            raw_to = extracted.get("to", "").strip()
            user_note = extracted.get("body", "").strip()
            resolved_to = raw_to

            system_prompt = "You are an email composition assistant. Generate professional email content."
            if context_bundle and context_bundle.top_facts:
                facts_text = "\n".join([f"- {fact.get('text', '')}" for fact in context_bundle.top_facts[:5]])
                system_prompt += f"\n\nKNOWN FACTS ABOUT USER:\n{facts_text}\n\nUse these facts to personalize the email when relevant."

            if user_note:
                prompt = (
                    f"User wants to send an email to {raw_to or resolved_to}. "
                    f'The email should say: "{user_note}".\n\n'
                    "Generate a brief subject line and email body."
                )
            else:
                prompt = (
                    f"User wants to send an email to {raw_to or resolved_to}. "
                    f"Request: {message}\n\nGenerate a brief subject line and email body."
                )

            try:
                llm_response = self.llm_service.chat_completion_text(
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
                    max_tokens=200,
                )
                lines = llm_response.split("\n", 1)
                subject = lines[0].replace("Subject:", "").strip()
                body = lines[1].strip() if len(lines) > 1 else ""
                return json.dumps({"action": "open_compose", "to": resolved_to, "subject": subject, "body": body})
            except Exception as e:
                logger.error("Error composing email: %s", e, exc_info=True)
                return "I had trouble composing that email. Please try again."

        try:
            core_payload = {
                "source": "gmail_chat",
                "workspace_id": user_id,
                "message_id": f"chat-{(session_id or 'session')}-{uuid4().hex[:12]}",
                "thread_id": session_id or "",
                "from": "",
                "to": "",
                "subject": "",
                "text": message,
                "timestamp": "",
            }
            res = ingest_gmail(core_payload)
            if not res.get("success"):
                return f"I couldn't process that via the core backend: {res.get('error', 'unknown error')}."
            reply_text = res.get("reply_text")
            if reply_text:
                return str(reply_text)
            classification = res.get("classification") if isinstance(res.get("classification"), dict) else {}
            summary = (classification or {}).get("summary")
            if summary:
                return str(summary)
            status = res.get("status")
            created_task_id = res.get("grafik_task_id") or res.get("linked_grafik_task_id")
            if created_task_id:
                return f"Processed. Status: {status}. Created/linked task: {created_task_id}."
            return f"Processed. Status: {status}."
        except Exception as e:
            logger.error("Core backend delegation failed in GmailAgent: %s", e, exc_info=True)
            return "I had trouble processing that email request. Please try again."

