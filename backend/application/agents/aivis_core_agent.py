"""
AivisCoreAgent - handles general productivity and chat requests.
"""

from typing import Any, Dict, List, Optional

from backend.application.services import memory_service
from backend.utils.logger import get_logger

logger = get_logger("aivis_core_agent")


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

        messages = [{"role": "system", "content": system_prompt}]
        if session_memory:
            messages.extend(session_memory[-20:])

        try:
            import json
            parsed_message = json.loads(user_message)
            if isinstance(parsed_message, dict) and "content" in parsed_message:
                messages.append({"role": "user", "content": parsed_message["content"]})
            else:
                messages.append({"role": "user", "content": user_message})
        except (json.JSONDecodeError, ValueError, TypeError):
            messages.append({"role": "user", "content": user_message})

        try:
            has_images = any(
                isinstance(msg.get("content"), list)
                and any(isinstance(item, dict) and item.get("type") == "image_url" for item in msg.get("content", []))
                for msg in messages
            )
            if has_images:
                response = self.llm_service.chat_completion(messages=messages, temperature=0.3, max_tokens=768)
                reply = response.choices[0].message.content or ""
            else:
                reply = self.llm_service.chat_completion_text(messages=messages, temperature=0.3, max_tokens=768)
            return {"reply": reply}
        except Exception as e:
            logger.error("Error in AivisCoreAgent: %s", e, exc_info=True)
            return {"reply": "I'm having trouble processing that right now. Please try again."}

