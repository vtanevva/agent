import os
from typing import List, Dict, Any, Optional

from openai import OpenAI


_CLIENT: Optional[OpenAI] = None


# ──────────────────────────────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────────────────────────────

AIVIS_SYSTEM_PROMPT: str = """
You are Aivis, a calm, practical, productivity-oriented AI assistant.
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
- Prefer structured answers (bullets, steps, short sections) for planning and
  organization.
- Ask clarifying questions only when absolutely necessary to move forward.
- When rewriting text, keep the user’s intent and meaning, but improve clarity,
  tone, and structure.
""".strip()


def _get_client() -> OpenAI:
    """
    Return a singleton OpenAI client instance.
    Relies on OPENAI_API_KEY being set in the environment.
    """
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenAI()
    return _CLIENT


def _build_messages(
    user_message: str,
    session_memory: Optional[List[Dict[str, Any]]] = None,
    max_history: int = 20,
) -> List[Dict[str, str]]:
    """
    Build the chat messages array for the Aivis Core assistant.

    - Prepends the Aivis system prompt.
    - Optionally includes a short list of prior messages as context (already in OpenAI format).
    """
    messages: List[Dict[str, str]] = [{"role": "system", "content": AIVIS_SYSTEM_PROMPT}]

    # Session memory is already in OpenAI message format: [{"role": "...", "content": "..."}]
    if session_memory:
        for msg in session_memory[-max_history:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})
    return messages


def chat_with_aivis_core(
    user_message: str,
    session_memory: list | None = None,
    model: str | None = None,
) -> str:
    """
    General Aivis Core chat entrypoint.

    Parameters
    ----------
    user_message: str
        The latest user utterance.
    session_memory: list | None
        Optional short conversation history in OpenAI messages format.
    model: str | None
        Optional override for the model name; defaults to OPENAI_MODEL env or a sensible default.

    Returns
    -------
    str
        Assistant reply text.
    """
    client = _get_client()
    model_name = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    messages = _build_messages(user_message=user_message, session_memory=session_memory)

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.3,
            max_tokens=768,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        # Log to stdout/stderr if needed in the future; for now, keep it silent for callers.
        print(f"[ERROR] Aivis Core chat failed: {e}", flush=True)
        return "I'm having trouble reaching the AI model right now. Please try again in a moment."

