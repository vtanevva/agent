"""Compatibility exports for legacy app.agents imports."""

from app.agents.aivis_core_agent import AivisCoreAgent
from app.agents.gmail_agent import GmailAgent
from app.agents.orchestrator import Orchestrator, get_orchestrator
from app.agents.slack_agent import SlackAgent

__all__ = [
    "AivisCoreAgent",
    "GmailAgent",
    "SlackAgent",
    "Orchestrator",
    "get_orchestrator",
]

