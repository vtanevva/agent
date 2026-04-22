"""Compatibility shim — implementation in ``backend.integrations.llm``."""

from backend.integrations.llm.llm_client import LLMService, get_llm_service  # noqa: F401

__all__ = ["LLMService", "get_llm_service"]
