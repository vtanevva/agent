from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Tuple

from backend.utils.logger import get_logger

logger = get_logger("ai_chat_orchestrator")

IntentType = Literal["email", "slack", "general"]

EMAIL_KEYWORDS = [
    "emails",
    "email",
    "inbox",
    "reply to",
    "gmail",
    "send a message to",
    "send message to",
]

SLACK_KEYWORDS = [
    "slack",
    "dm",
    "direct message",
    "channel",
    "post in",
    "send in",
]


def detect_intent(user_message: str) -> IntentType:
    from backend.integrations.llm.llm_client import get_llm_service

    text = (user_message or "").lower()
    advice_questions = ["when should", "what time", "how should", "can i schedule", "should i", "should we"]
    if any(q in text for q in advice_questions):
        return "general"

    has_email_kw = any(k in text for k in EMAIL_KEYWORDS)
    has_slack_kw = any(k in text for k in SLACK_KEYWORDS)
    if has_email_kw and not has_slack_kw:
        return "email"
    if has_slack_kw and not has_email_kw:
        return "slack"
    if not has_email_kw and not has_slack_kw:
        return "general"

    # Both keyword families present — disambiguate with a small LLM call.
    try:
        llm_service = get_llm_service()
        prompt = f"""Classify this user message into ONE category:

Message: "{user_message}"

Categories:
- email: user wants to send, read, or manage emails.
- slack: user wants to send/summarize/handle Slack updates.
- general: advice or general chat.

IMPORTANT:
- "When should I..." and "How should I..." are general.
- Only choose email/slack if there is a clear action.

Return only one word: email, slack, or general.
Category:"""
        response = llm_service.chat_completion_text(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        intent = response.strip().lower()
        if intent in {"email", "slack", "general"}:
            if intent == "general" and has_email_kw:
                return "email"
            if intent == "general" and has_slack_kw:
                return "slack"
            return intent  # type: ignore[return-value]
    except Exception as e:
        logger.warning("LLM intent detection failed: %s", e)

    return "general"


class Orchestrator:
    def __init__(
        self,
        aivis_core_agent,
        llm_service,
        memory_service,
        gmail_agent=None,
        slack_agent=None,
    ):
        self.aivis_core = aivis_core_agent
        self.llm_service = llm_service
        self.memory_service = memory_service
        self.gmail_agent = gmail_agent
        self.slack_agent = slack_agent

    def handle_chat(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        metadata: Optional[Dict[str, Any]] = None,
        message_type: Optional[IntentType] = None,
    ) -> Tuple[str, str]:
        md = metadata if isinstance(metadata, dict) else {}
        rd = md.get("reply_draft")
        dp = md.get("draft_polish")
        has_reply_context = isinstance(rd, dict) and bool(
            (str(rd.get("snippet") or "").strip())
            or (str(rd.get("subject") or "").strip())
            or (str(rd.get("from_header") or "").strip())
        )
        has_draft_polish = isinstance(dp, dict) and bool(str(dp.get("draft") or "").strip())
        if has_reply_context or has_draft_polish:
            intent: IntentType = "general"
        else:
            intent = message_type if message_type in {"email", "slack", "general"} else detect_intent(user_message)
        session_memory = self.memory_service.get_session_history(
            user_id=user_id,
            session_id=session_id,
            limit=20,
        )

        if intent == "email":
            if not self.gmail_agent:
                return intent, "Gmail features are not available right now. Please try again later."
            reply = self.gmail_agent.handle_chat(
                user_id=user_id,
                message=user_message,
                session_memory=session_memory,
                metadata=metadata,
                session_id=session_id,
            )
            return intent, reply

        if intent == "slack":
            if not self.slack_agent:
                return intent, "Slack features are not available right now. Please try again later."
            reply = self.slack_agent.handle_chat(
                user_id=user_id,
                message=user_message,
                session_id=session_id,
                metadata=metadata,
            )
            return intent, reply

        if intent == "general":
            try:
                if not has_draft_polish:
                    from backend.application.services.calendar_meeting_action import try_create_meeting_from_chat
                    from backend.application.services.chat_task_action import try_create_task_from_chat

                    meeting_reply = try_create_meeting_from_chat(user_message, metadata)
                    if meeting_reply:
                        return intent, meeting_reply
                    task_reply = try_create_task_from_chat(
                        user_message, metadata, session_id=session_id
                    )
                    if task_reply:
                        return intent, task_reply
            except Exception as e:
                logger.warning("Meeting/task chat shortcut skipped: %s", e)

        result = self.aivis_core.handle_chat(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            session_memory=session_memory,
            metadata=metadata,
        )
        return intent, result.get("reply", "")


def build_orchestrator() -> Orchestrator:
    from backend.integrations.llm.llm_client import get_llm_service
    from backend.application.agents.aivis_core_agent import AivisCoreAgent
    from backend.application.agents.gmail_agent import GmailAgent
    from backend.application.agents.slack_agent import SlackAgent

    class _NullMemoryService:
        def get_session_history(self, *args, **kwargs):
            return []

    llm_service = get_llm_service()
    memory_service = _NullMemoryService()

    aivis_core_agent = AivisCoreAgent(llm_service=llm_service, memory_service=memory_service)
    gmail_agent = GmailAgent(llm_service=llm_service, memory_service=memory_service)
    slack_agent = SlackAgent(llm_service=llm_service, memory_service=memory_service)

    return Orchestrator(
        aivis_core_agent=aivis_core_agent,
        llm_service=llm_service,
        memory_service=memory_service,
        gmail_agent=gmail_agent,
        slack_agent=slack_agent,
    )


_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_orchestrator()
    return _orchestrator

