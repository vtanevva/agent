"""Compatibility shim to backend application agent."""

from backend.application.agents.slack_agent import SlackAgent  # noqa: F401

__all__ = ["SlackAgent"]

