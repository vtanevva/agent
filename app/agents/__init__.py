"""
Agents module - domain-specific agents for handling different types of requests.

Available agents:
- AivisCoreAgent: General productivity and chat
- GmailAgent: Email operations
- CalendarAgent: Calendar management
- ContactsAgent: Contact management (stub)
- Orchestrator: Routes requests to appropriate agents
"""

from app.agents.aivis_core_agent import AivisCoreAgent
from app.agents.gmail_agent import GmailAgent
from app.agents.calendar_agent import CalendarAgent
from app.agents.contacts_agent import ContactsAgent
from app.agents.orchestrator import Orchestrator, get_orchestrator

__all__ = [
    "AivisCoreAgent",
    "GmailAgent",
    "CalendarAgent",
    "ContactsAgent",
    "Orchestrator",
    "get_orchestrator",
]

