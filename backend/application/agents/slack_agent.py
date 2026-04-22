"""
SlackAgent - delegates Slack-related processing to the core backend.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.application.services.core_backend_client import ingest_slack
from backend.utils.logger import get_logger

logger = get_logger("slack_agent")


class SlackAgent:
    def __init__(self, llm_service=None, memory_service=None):
        self.llm_service = llm_service
        self.memory_service = memory_service

    def handle_chat(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        try:
            ts = datetime.now(timezone.utc).timestamp()
            payload = {
                "source": "slack_chat",
                "workspace_id": user_id,
                "text": message,
                "channel": f"web_chat:{session_id or user_id}",
                "ts": str(ts),
                "user_id": user_id,
            }
            res = ingest_slack(payload)
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
            logger.error("Core backend delegation failed in SlackAgent: %s", e, exc_info=True)
            return "I had trouble processing that Slack request. Please try again."

