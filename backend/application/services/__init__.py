"""
Application services package.

Heavy modules that assume ``backend/`` is on ``sys.path`` as top-level
``services`` / ``storage`` (e.g. ``action_tools``, ``reply_service``) are
**not** imported here — import them from their submodules explicitly, e.g.
``from backend.application.services import action_tools``.
"""

from .llm_service import LLMService, get_llm_service
from .memory_service import (
    AIVIS_BASE_PERSONALITY,
    aivis_fallback_system_prompt,
    build_aivis_system_prompt_from_bundle,
    retrieve_context_bundle,
)

__all__ = [
    "LLMService",
    "get_llm_service",
    "AIVIS_BASE_PERSONALITY",
    "retrieve_context_bundle",
    "build_aivis_system_prompt_from_bundle",
    "aivis_fallback_system_prompt",
]
