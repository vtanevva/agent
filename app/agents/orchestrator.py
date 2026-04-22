"""
Compatibility shim.

Primary orchestrator implementation now lives in:
    backend.application.orchestrators.ai_chat_orchestrator
"""

from backend.application.orchestrators.ai_chat_orchestrator import (  # noqa: F401
    Orchestrator,
    build_orchestrator,
    detect_intent,
    get_orchestrator,
)

__all__ = [
    "Orchestrator",
    "build_orchestrator",
    "detect_intent",
    "get_orchestrator",
]

