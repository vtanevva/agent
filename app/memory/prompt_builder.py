"""
Prompt Builder - Builds prompts with injected context

This module constructs prompts with:
- System instructions
- User profile
- Relevant facts
- Thread summaries
- Document excerpts
- Recent messages
"""

import logging
from typing import Optional, List, Dict, Any
from .retrieval_service import ContextBundle

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    Builds prompts with context injection for RAG.
    """
    
    def __init__(self):
        """Initialize prompt builder"""
        pass
    
    def build_system_prompt(
        self,
        bundle: ContextBundle,
        assistant_name: str = "Aivis",
        base_personality: str = None,
    ) -> str:
        """
        Build system prompt with injected context.
        
        Args:
            bundle: ContextBundle with retrieved context
            assistant_name: Name of the assistant
            base_personality: Custom personality/instructions (optional)
        
        Returns:
            System prompt string
        """
        sections = []
        
        # System instructions (use custom or default)
        if base_personality:
            sections.append(base_personality)
        else:
            sections.append(f"""You are {assistant_name}, a personal AI assistant.

Your role:
- Help the user with their tasks, questions, and requests
- Use the provided context about the user to personalize responses
- If context is missing or unclear, ask clarifying questions
- Do not invent information or file contents
- Be concise, helpful, and match the user's preferred tone""")
        
        # User profile
        if bundle.profile_summary:
            sections.append(f"""
USER PROFILE:
{bundle.profile_summary}""")
        
        # Facts about user
        if bundle.top_facts:
            facts_text = "\n".join([
                f"- {fact.get('text', '')}"
                for fact in bundle.top_facts[:10]
            ])
            sections.append(f"""
FACTS ABOUT USER:
{facts_text}""")
        
        # Thread summaries (past context)
        if bundle.top_summaries:
            summaries_text = "\n".join([
                f"- [Thread {s.get('thread_id', 'unknown')}] {s.get('summary_text', '')}"
                for s in bundle.top_summaries[:5]
            ])
            sections.append(f"""
EPISODIC SUMMARIES (past conversations):
{summaries_text}""")
        
        # Document excerpts
        if bundle.top_doc_chunks:
            chunks_text = "\n".join([
                f"- (Doc: {chunk.get('doc_title', 'Unknown')}, chunk {chunk.get('chunk_index', 0)})\n  {chunk.get('text', '')[:200]}..."
                for chunk in bundle.top_doc_chunks[:8]
            ])
            sections.append(f"""
DOCUMENT EXCERPTS (from user's files):
{chunks_text}""")
        
        # Combine sections
        prompt = "\n".join(sections)
        return prompt
    
    def build_messages_with_context(
        self,
        bundle: ContextBundle,
        user_message: str,
        assistant_name: str = "Aivis",
        base_personality: str = None,
        include_recent_messages: bool = True,
    ) -> List[Dict[str, str]]:
        """
        Build OpenAI-format messages array with context.
        
        Args:
            bundle: ContextBundle with retrieved context
            user_message: Latest user message
            assistant_name: Name of the assistant
            base_personality: Custom personality/instructions (optional)
            include_recent_messages: Whether to include recent thread messages
        
        Returns:
            List of message dicts in OpenAI format
        """
        messages = []
        
        # System message with context
        system_prompt = self.build_system_prompt(bundle, assistant_name, base_personality)
        messages.append({
            "role": "system",
            "content": system_prompt
        })
        
        # Recent thread messages (for conversation continuity)
        if include_recent_messages and bundle.recent_messages:
            for msg in bundle.recent_messages[-10:]:  # Last 10 turns
                role = "user" if msg.get("direction") == "in" else "assistant"
                messages.append({
                    "role": role,
                    "content": msg.get("text", "")
                })
        
        # Current user message
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return messages
    
    def build_simple_prompt(
        self,
        bundle: ContextBundle,
        user_message: str,
        assistant_name: str = "Aivis",
    ) -> str:
        """
        Build a simple string prompt (for non-chat models).
        
        Args:
            bundle: ContextBundle with retrieved context
            user_message: Latest user message
            assistant_name: Name of the assistant
        
        Returns:
            Complete prompt string
        """
        sections = []
        
        # System section
        sections.append(f"SYSTEM: You are {assistant_name}, a personal AI assistant.")
        
        # Context section
        if bundle.profile_summary:
            sections.append(f"\nUSER PROFILE:\n{bundle.profile_summary}")
        
        if bundle.top_facts:
            facts_text = "\n".join([f"- {fact.get('text', '')}" for fact in bundle.top_facts[:10]])
            sections.append(f"\nFACTS:\n{facts_text}")
        
        if bundle.top_summaries:
            summaries_text = "\n".join([f"- {s.get('summary_text', '')}" for s in bundle.top_summaries[:5]])
            sections.append(f"\nPAST CONVERSATIONS:\n{summaries_text}")
        
        if bundle.top_doc_chunks:
            chunks_text = "\n".join([
                f"- (Doc: {c.get('doc_title', 'Unknown')})\n  {c.get('text', '')[:200]}..."
                for c in bundle.top_doc_chunks[:8]
            ])
            sections.append(f"\nDOCUMENT EXCERPTS:\n{chunks_text}")
        
        # Recent messages
        if bundle.recent_messages:
            messages_text = "\n".join([
                f"[{msg.get('direction', 'in').upper()}] {msg.get('text', '')}"
                for msg in bundle.recent_messages[-10:]
            ])
            sections.append(f"\nRECENT MESSAGES:\n{messages_text}")
        
        # User message
        sections.append(f"\nUSER: {user_message}")
        sections.append(f"\n{assistant_name}:")
        
        return "\n".join(sections)
    
    def estimate_token_count(self, bundle: ContextBundle) -> int:
        """
        Estimate token count of context bundle.
        
        Args:
            bundle: ContextBundle
        
        Returns:
            Approximate token count
        """
        # Rough estimation: 1 token = 4 characters
        total_chars = 0
        
        total_chars += len(bundle.profile_summary)
        
        for fact in bundle.top_facts:
            total_chars += len(fact.get("text", ""))
        
        for summary in bundle.top_summaries:
            total_chars += len(summary.get("summary_text", ""))
        
        for chunk in bundle.top_doc_chunks:
            total_chars += len(chunk.get("text", ""))
        
        for msg in bundle.recent_messages:
            total_chars += len(msg.get("text", ""))
        
        return total_chars // 4


# Convenience function
def build_context_aware_messages(
    user_id: str,
    thread_id: Optional[str],
    user_message: str,
    query_text: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Convenience function to retrieve context and build messages in one call.
    
    Args:
        user_id: User ID
        thread_id: Thread ID
        user_message: User's message
        query_text: Query for semantic search (defaults to user_message)
    
    Returns:
        List of message dicts for LLM
    """
    from .retrieval_service import get_retrieval_service
    
    # Retrieve context
    retrieval_service = get_retrieval_service()
    bundle = retrieval_service.retrieve_context(
        user_id=user_id,
        thread_id=thread_id,
        query_text=query_text or user_message,
    )
    
    # Build messages
    builder = PromptBuilder()
    messages = builder.build_messages_with_context(
        bundle=bundle,
        user_message=user_message,
    )
    
    logger.info(f"📝 Built context-aware prompt: ~{builder.estimate_token_count(bundle)} tokens")
    
    return messages


# Singleton instance
_prompt_builder: Optional[PromptBuilder] = None


def get_prompt_builder() -> PromptBuilder:
    """
    Get singleton instance of PromptBuilder.
    
    Returns:
        PromptBuilder instance
    """
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = PromptBuilder()
        logger.info("✅ PromptBuilder initialized")
    return _prompt_builder

