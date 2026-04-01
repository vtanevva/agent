import os
from typing import Any

from openai import OpenAI


def _get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[REPLY_WRITER] OPENAI_API_KEY missing")
        return None
    return OpenAI(api_key=api_key)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _format_project_context(project_context: dict | None) -> str:
    if not project_context:
        return "None"

    parts: list[str] = []

    summary = _safe_text(project_context.get("summary"))
    current_status = _safe_text(project_context.get("current_status"))
    current_priorities = _safe_text(project_context.get("current_priorities"))
    blockers = _safe_text(project_context.get("blockers"))
    next_steps = _safe_text(project_context.get("next_steps"))

    if summary:
        parts.append(f"- Summary: {summary}")
    if current_status:
        parts.append(f"- Current Status: {current_status}")
    if current_priorities:
        parts.append(f"- Current Priorities: {current_priorities}")
    if blockers:
        parts.append(f"- Blockers: {blockers}")
    if next_steps:
        parts.append(f"- Next Steps: {next_steps}")

    return "\n".join(parts) if parts else "None"


def _format_project_update_candidate(project_update_candidate: dict | None) -> str:
    if not project_update_candidate:
        return "None"

    has_project_update = bool(project_update_candidate.get("has_project_update"))
    confidence = project_update_candidate.get("confidence", 0.0)
    fields = project_update_candidate.get("fields") or {}

    if not has_project_update:
        return "None"

    lines = [f"- has_project_update: {has_project_update}", f"- confidence: {confidence}"]

    if isinstance(fields, dict):
        for key, value in fields.items():
            lines.append(f"- {key}: {_safe_text(value)}")

    return "\n".join(lines)


def generate_reply(
    original_text: str,
    reply_type: str,
    summary: str | None = None,
    sender: str | None = None,
    project_name: str | None = None,
    project_context: dict | None = None,
    project_update_candidate: dict | None = None,
    classification: dict | None = None,
    channel: str = "generic",
) -> str | None:
    if not original_text or reply_type == "none":
        print("[REPLY_WRITER] skipped: empty text or reply_type=none")
        return None

    client = _get_client()
    if client is None:
        print("[REPLY_WRITER] skipped: OPENAI client is None")
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    sender_text = _safe_text(sender)
    project_name_text = _safe_text(project_name) or "Unknown"
    summary_text = _safe_text(summary)
    project_context_text = _format_project_context(project_context)
    project_update_text = _format_project_update_candidate(project_update_candidate)

    classification_json = classification or {}
    channel = (channel or "generic").strip().lower()

    blockers_text = _safe_text(project_context.get("blockers") if project_context else "")
    next_steps_text = _safe_text(project_context.get("next_steps") if project_context else "")

    context_guidance = ""
    if reply_type in {"context_relevant", "time_relevant"} and (blockers_text or next_steps_text):
        # Encourage using context as supporting detail, not as "new tasks".
        context_guidance = "\n".join(
            [
                "If helpful, you may reference the project context below:",
                f"- Blockers: {blockers_text or 'None'}",
                f"- Next steps: {next_steps_text or 'None'}",
                "Only mention these if they directly help answer the incoming message.",
                "Do not treat 'Next steps' as a new request unless the incoming message asks for it.",
            ]
        )

    if channel == "slack":
        style_rules = """
Channel style:
- Write like a short professional Slack reply
- Keep it concise
- No email greeting
- No sign-off
- 1 to 3 short sentences max
"""
    else:
        style_rules = """
Channel style:
- Write like a professional email reply body
- Greeting is optional
- Sign-off is optional
- Keep it concise and natural
"""

    system_prompt = f"""You write natural professional reply drafts.

Write a natural, human-sounding reply.
Do not sound robotic.
Use the provided project context when it helps.
Do not invent facts not supported by the message or context.
Do not create or imply new tasks unless the incoming message explicitly requests an action.

Match the reply type:
- short: brief acknowledgement
- time_relevant: acknowledge urgency, timing, or deadline
- context_relevant: answer thoughtfully but concisely

{style_rules}

Rules:
- Return only the reply body text
- No subject line
- No placeholders like [Name]
- If the context includes blockers or next steps, you may mention them only if they are relevant
- Do not over-explain
- If the message is just a follow-up, respond like a follow-up, not like a new task confirmation
- If the message is a blocker/status update, acknowledge it naturally
"""

    user_prompt = f"""
Reply type: {reply_type}
Sender: {sender_text}
Project: {project_name_text}

Incoming message:
{original_text}

Classification summary:
{summary_text}

Classification object:
{classification_json}

Project context:
{project_context_text}

Extracted project update candidate:
{project_update_text}

Extra context guidance:
{context_guidance or "None"}

Write the best reply draft now.
"""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
        )

        content = resp.choices[0].message.content
        if not content:
            print("[REPLY_WRITER] empty model response")
            return None

        result = content.strip()
        print(f"[REPLY_WRITER] generated: {result!r}")
        return result

    except Exception as e:
        print(f"[REPLY_WRITER] error: {e}")
        return None