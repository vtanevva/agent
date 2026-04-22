"""Compatibility shim to backend application agent."""

from backend.application.agents.aivis_core_agent import AivisCoreAgent  # noqa: F401

__all__ = ["AivisCoreAgent"]

"""
AivisCoreAgent - handles general productivity and chat requests.

This is the default agent for non-email, non-calendar requests.
"""

from typing import Dict, Any, Optional, List

from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


class AivisCoreAgent:
    """
    Agent for general productivity, tasks, and chat.
    
    This is the "default" agent that handles anything that's not
    specifically email or calendar related.
    """
    
    def __init__(self, llm_service, memory_service):
        """
        Initialize AivisCoreAgent.
        
        Parameters
        ----------
        llm_service : LLMService
            LLM service for text generation
        memory_service : MemoryService
            Memory service for conversation history
        """
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
        """
        Handle a general chat message.
        
        Parameters
        ----------
        user_id : str
            User identifier
        session_id : str
            Session identifier
        user_message : str
            User's message
        session_memory : list, optional
            Recent conversation history in OpenAI format
        metadata : dict, optional
            Additional metadata
            
        Returns
        -------
        dict
            Response with "reply" key
        """
        logger.info(f"AivisCoreAgent handling message for user {user_id}")
        
        # ===== RETRIEVE USER AWARENESS CONTEXT =====
        try:
            from app.memory.retrieval_service import get_retrieval_service
            from app.memory.prompt_builder import get_prompt_builder
            
            retrieval_service = get_retrieval_service()
            prompt_builder = get_prompt_builder()
            
            # Retrieve context bundle (facts, summaries, doc chunks, recent messages)
            context_bundle = retrieval_service.retrieve_context(
                user_id=user_id,
                thread_id=session_id,
                query_text=user_message if isinstance(user_message, str) else None,
            )
            
            # Build system prompt with injected context
            system_prompt = prompt_builder.build_system_prompt(
                bundle=context_bundle,
                assistant_name="Aivis",
                base_personality="""You are Aivis, a calm, practical, productivity-oriented AI assistant.
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
- When rewriting text, keep the user's intent and meaning, but improve clarity, tone, and structure.""",
            )
            
            logger.info(f"📚 Retrieved context: {context_bundle.retrieval_stats.get('total_items', 0)} items")
            
        except Exception as e:
            # Fallback to basic prompt if User Awareness fails
            logger.warning(f"User Awareness retrieval failed, using basic prompt: {e}")
            system_prompt = """You are Aivis, a calm, practical, productivity-oriented AI assistant.
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
        
        # Build messages array
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add session memory if available
        if session_memory:
            messages.extend(session_memory[-20:])  # Last 20 messages
        
        # Parse user message - check if it contains images
        try:
            import json
            parsed_message = json.loads(user_message)
            if isinstance(parsed_message, dict) and "content" in parsed_message:
                # Message with images (from chat route)
                messages.append({"role": "user", "content": parsed_message["content"]})
            else:
                # Regular text message
                messages.append({"role": "user", "content": user_message})
        except (json.JSONDecodeError, ValueError, TypeError):
            # Regular text message
            messages.append({"role": "user", "content": user_message})
        
        try:
            # Check if message contains images
            has_images = any(
                isinstance(msg.get("content"), list) and 
                any(isinstance(item, dict) and item.get("type") == "image_url" for item in msg.get("content", []))
                for msg in messages
            )
            
            if has_images:
                # Use chat_completion for images (returns response object)
                response = self.llm_service.chat_completion(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=768
                )
                reply = response.choices[0].message.content or ""
            else:
                # Use chat_completion_text for text-only (faster)
                reply = self.llm_service.chat_completion_text(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=768
                )
            
            return {"reply": reply}
        except Exception as e:
            logger.error(f"Error in AivisCoreAgent: {e}", exc_info=True)
            return {"reply": "I'm having trouble processing that right now. Please try again."}

