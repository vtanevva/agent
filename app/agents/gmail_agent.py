"""Compatibility shim to backend application agent."""

from backend.application.agents.gmail_agent import GmailAgent  # noqa: F401

__all__ = ["GmailAgent"]

