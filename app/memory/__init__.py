"""
User Awareness Memory System

This package implements a comprehensive memory and retrieval layer for Aivis,
enabling the assistant to respond with context from past conversations, user facts,
and uploaded documents.

Key Components:
- models: MongoDB data models for users, messages, facts, documents
- vector_store: Pinecone interface for embeddings storage and retrieval
- ingestion_service: Ingests messages and documents into memory
- memory_gate: Curates and validates facts before storage
- retrieval_service: Retrieves relevant context for prompts
- prompt_builder: Builds prompts with injected context
"""

from .ingestion_service import IngestionService, get_ingestion_service
from .memory_gate import MemoryGate, get_memory_gate
from .retrieval_service import RetrievalService, get_retrieval_service
from .prompt_builder import PromptBuilder, ContextBundle

__all__ = [
    'IngestionService',
    'MemoryGate',
    'RetrievalService',
    'PromptBuilder',
    'ContextBundle',
    'get_ingestion_service',
    'get_memory_gate',
    'get_retrieval_service',
]

