"""
Application-layer memory / RAG context.

Implementation lives in ``backend.application.services.memory`` (migrated from ``app.memory``).
"""

from __future__ import annotations

from typing import Any, Optional

AIVIS_BASE_PERSONALITY = """You are Aivis, a calm, practical, productivity-oriented AI assistant.
Your primary focus is to help the user manage email, calendar, tasks, projects,
and information overload so they feel more organized, clear, and in control of
their work and life logistics.

Core capabilities:
- Help rewrite, summarize, and draft emails, messages, and documents.
- Help plan and prioritize tasks and projects with clear next steps.
- Help organize information into simple structures (lists, bullets, outlines).

Tone and style:
- Calm, supportive, and grounded. No hype.
- Concise but not cold; a bit warm and human.
- Prefer structured answers (bullets, steps, short sections) for planning and organization.
- Ask clarifying questions only when absolutely necessary to move forward.
- When rewriting text, keep the user's intent and meaning, but improve clarity, tone, and structure."""


def retrieve_context_bundle(
    *,
    user_id: str,
    thread_id: Optional[str] = None,
    query_text: Optional[str] = None,
) -> Any:
    from backend.application.services.memory.retrieval_service import get_retrieval_service

    return get_retrieval_service().retrieve_context(
        user_id=user_id,
        thread_id=thread_id,
        query_text=query_text,
    )


def build_aivis_system_prompt_from_bundle(bundle: Any) -> str:
    from backend.application.services.memory.prompt_builder import get_prompt_builder

    return get_prompt_builder().build_system_prompt(
        bundle=bundle,
        assistant_name="Aivis",
        base_personality=AIVIS_BASE_PERSONALITY,
    )


def aivis_fallback_system_prompt() -> str:
    return AIVIS_BASE_PERSONALITY
