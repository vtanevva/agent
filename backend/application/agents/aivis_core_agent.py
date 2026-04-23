"""
AivisCoreAgent - handles general productivity and chat requests.
"""

import os
from typing import Any, Dict, List, Optional

from backend.application.services import memory_service
from backend.utils.logger import get_logger

logger = get_logger("aivis_core_agent")


def _reply_draft_signoff_rules(user_id: str) -> str:
    """Tell the model how to close without fake placeholders."""
    u = (user_id or "").strip()
    if not u:
        return (
            "End with a real closing: e.g. 'Best regards' then one line with a plausible first name only if you "
            "can infer it from the conversation. Never use bracket placeholders like [Your Name], "
            "[signature], [Contact], or similar."
        )
    if "@" in u:
        local, _, _ = u.partition("@")
        raw = local.replace(".", " ").replace("_", " ").replace("-", " ")
        parts = [p for p in raw.split() if p]
        label = " ".join((p[:1].upper() + p[1:].lower()) if p else "" for p in parts[:3]).strip() or local
        return (
            f"The sender's login email local-part is '{local}'; a reasonable sign-off name may be '{label}' "
            "if that looks like a person's name (otherwise use only 'Best regards' with no fake name). "
            "Never use bracket placeholders like [Your Name], [LinkedIn], [Company], or TBD markers."
        )
    return (
        f"Sign off naturally. Never use bracket placeholders. Account hint (truncated): {u[:80]}."
    )


def _chat_rag_enabled() -> bool:
    """Set ``AIVIS_CHAT_RAG=1`` to load memory/RAG (Mongo + embeddings) before each reply."""
    return (os.getenv("AIVIS_CHAT_RAG") or "").strip().lower() in {"1", "true", "yes", "on"}


class AivisCoreAgent:
    def __init__(self, llm_service, memory_service):
        self.llm_service = llm_service
        self.memory_service = memory_service

    def handle_chat(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        session_memory: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        logger.info("AivisCoreAgent handling message for user %s", user_id)

        if _chat_rag_enabled():
            try:
                context_bundle = memory_service.retrieve_context_bundle(
                    user_id=user_id,
                    thread_id=session_id,
                    query_text=user_message if isinstance(user_message, str) else None,
                )
                system_prompt = memory_service.build_aivis_system_prompt_from_bundle(context_bundle)
            except Exception as e:
                logger.warning("User Awareness retrieval failed, using basic prompt: %s", e)
                system_prompt = memory_service.aivis_fallback_system_prompt()
        else:
            system_prompt = memory_service.aivis_fallback_system_prompt()

        messages = [{"role": "system", "content": system_prompt}]
        rd = (metadata or {}).get("reply_draft") if isinstance(metadata, dict) else None
        polish = (metadata or {}).get("draft_polish") if isinstance(metadata, dict) else None
        dp_is = isinstance(polish, dict) and bool(str(polish.get("draft") or "").strip())

        if isinstance(rd, dict) and not dp_is:
            src = str(rd.get("source") or "").strip()
            subj = str(rd.get("subject") or "").strip()
            frm = str(rd.get("from_header") or "").strip()
            snip = str(rd.get("snippet") or "").strip()
            signoff = _reply_draft_signoff_rules(user_id)
            draft_addon = (
                "\n\n## Reply drafting mode\n"
                "The user will send your output as their reply. Respond with ONLY the outgoing "
                "message body: plain text, suitable for email or chat. Do not add a preamble "
                '(no "Sure", "Here is a draft", or similar). Do not wrap the text in markdown '
                "code fences.\n"
                "Output the message once: no duplicate versions, no alternatives list.\n"
                f"{signoff}\n\n"
                f"Source channel: {src or '(unknown)'}\n"
                f"Subject / title: {subj or '(none)'}\n"
                f"From: {frm or '(unknown)'}\n\n"
                f"Message to respond to:\n{snip or '(no excerpt stored — infer from subject/from.)'}\n"
            )
            messages[0] = {
                "role": "system",
                "content": (messages[0].get("content") or "") + draft_addon,
            }
        elif dp_is:
            signoff = _reply_draft_signoff_rules(user_id)
            polish_addon = (
                "\n\n## Polish email draft mode\n"
                "The user has an outgoing email (or chat) draft and wants it rewritten per their note. "
                "Respond with ONLY the improved message body: plain text, ready to send. "
                "No preamble, no markdown code fences, no before/after commentary.\n"
                "Preserve factual content unless the user explicitly asks to change facts.\n"
                f"{signoff}\n"
            )
            messages[0] = {
                "role": "system",
                "content": (messages[0].get("content") or "") + polish_addon,
            }
        if session_memory:
            messages.extend(session_memory[-20:])

        try:
            import json

            if dp_is:
                instr = str(polish.get("instruction") or "").strip()
                draft = str(polish.get("draft") or "").strip()
                um = (user_message or "").strip()
                direction = instr or "General polish: clearer, warmer, and ready to send."
                body = (
                    (f"{um}\n\n" if um else "")
                    + "Rewrite the draft following this direction (keep meaning unless asked to change it):\n"
                    + direction
                    + "\n\n--- current draft ---\n"
                    + draft
                )
                messages.append({"role": "user", "content": body})
            else:
                parsed_message = json.loads(user_message)
                if isinstance(parsed_message, dict) and "content" in parsed_message:
                    messages.append({"role": "user", "content": parsed_message["content"]})
                else:
                    messages.append({"role": "user", "content": user_message})
        except (json.JSONDecodeError, ValueError, TypeError):
            if not dp_is:
                messages.append({"role": "user", "content": user_message})

        try:
            has_images = any(
                isinstance(msg.get("content"), list)
                and any(isinstance(item, dict) and item.get("type") == "image_url" for item in msg.get("content", []))
                for msg in messages
            )
            max_tokens = 1200 if (isinstance(rd, dict) and not dp_is) or dp_is else 768
            if has_images:
                response = self.llm_service.chat_completion(messages=messages, temperature=0.3, max_tokens=max_tokens)
                reply = response.choices[0].message.content or ""
            else:
                reply = self.llm_service.chat_completion_text(messages=messages, temperature=0.3, max_tokens=max_tokens)
            return {"reply": reply}
        except Exception as e:
            logger.error("Error in AivisCoreAgent: %s", e, exc_info=True)
            return {"reply": "I'm having trouble processing that right now. Please try again."}

