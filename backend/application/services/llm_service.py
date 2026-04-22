"""Re-export: canonical LLM implementation lives in ``backend.integrations.llm``."""

from backend.integrations.llm.llm_client import LLMService, get_llm_service

__all__ = ["LLMService", "get_llm_service"]
