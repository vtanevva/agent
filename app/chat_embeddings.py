import os
import numpy as np
from uuid import uuid4
from typing import List

from dotenv import load_dotenv
from tiktoken import get_encoding

load_dotenv()

# Keep encoding for backward compatibility
encoding = get_encoding("cl100k_base")

# Keep index variable for backward compatibility (will be deprecated)
index = None


def _get_memory_service():
    """Get the Memory service instance."""
    from app.services.memory_service import get_memory_service
    return get_memory_service()


def _get_llm_service():
    """Get the LLM service instance."""
    from app.services.llm_service import get_llm_service
    return get_llm_service()


def should_embed(text: str) -> bool:
    """Check if text is worth embedding (used by MemoryService internally)."""
    IGNORE = ("thank you", "hi", "ok", "sure", "bye")
    if any(k in text.lower() for k in IGNORE):
        return False
    return len(text.split()) >= 3


def embed_text(text: str) -> List[float]:
    """Generate embedding for text using LLM service."""
    llm_service = _get_llm_service()
    return llm_service.generate_embedding(text)


def save_chat_to_memory(message_text, session_id, user_id="default", emotion="neutral"):
    """
    Save a fact/message to memory using MemoryService.
    
    Legacy wrapper - delegates to MemoryService.
    emotion parameter kept for backward compatibility but not used.
    """
    if not should_embed(message_text):
        return
    
    memory_service = _get_memory_service()
    memory_service.save_fact(
        user_id=user_id,
        fact=message_text,
        session_id=session_id,
        metadata={},
    )


def search_chat_memory(query, top_k=3, user_id="default"):
    """
    Search memory for relevant facts using MemoryService.
    
    Legacy wrapper - delegates to MemoryService.
    """
    memory_service = _get_memory_service()
    return memory_service.search_memory(user_id=user_id, query=query, top_k=top_k)


def get_user_facts(user_id, namespace=None):
    """
    Get all saved facts for this user using MemoryService.
    
    Legacy wrapper - delegates to MemoryService.
    """
    memory_service = _get_memory_service()
    return memory_service.retrieve_facts(user_id=user_id, limit=200)

# ---------------------------------------------------------------------------
def summarize_old_facts(context_text: str) -> str:
    """
    Summarize facts using LLMService.
    
    Legacy wrapper - delegates to LLMService.
    """
    llm_service = _get_llm_service()
    return llm_service.summarize_facts(context_text)


def extract_facts_with_gpt(user_input: str) -> str:
    """
    Extract facts from user input using LLMService.
    
    Legacy wrapper - delegates to LLMService.
    """
    llm_service = _get_llm_service()
    return llm_service.extract_facts(user_input)
