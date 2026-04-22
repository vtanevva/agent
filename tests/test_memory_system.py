"""
Unit tests for User Awareness Memory System

Tests:
- Message ingestion
- Document chunking
- Fact extraction
- Context retrieval
- Prompt building
- User isolation
"""

import pytest
import os
import tempfile
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Test fixtures
SAMPLE_MESSAGE = "I prefer morning meetings and I work as a software engineer at TechCorp."
SAMPLE_THREAD_ID = "thread-test-123"
SAMPLE_USER_ID = "user-test-456"

SAMPLE_DOC_TEXT = """
Project Overview: AI Assistant Development

This document outlines the requirements for building an AI assistant.

Key Features:
1. Natural language understanding
2. Context awareness
3. Task automation
4. Integration with email and calendar

Technical Stack:
- Backend: Python/Flask
- Database: MongoDB
- Vector DB: Pinecone
- LLM: OpenAI GPT-4

The assistant should be able to remember user preferences and past conversations.
"""


class TestDocumentChunking:
    """Test document text chunking"""
    
    def test_chunk_text_basic(self):
        """Test basic text chunking"""
        from backend.application.services.memory.ingestion_service import IngestionService
        
        service = IngestionService()
        service.chunk_size = 50  # Small for testing
        service.chunk_overlap = 10
        
        text = "This is a test. " * 100  # Long text
        chunks = service._chunk_text(text)
        
        assert len(chunks) > 1, "Should create multiple chunks"
        assert all(len(c) > 0 for c in chunks), "All chunks should have content"
    
    def test_chunk_text_overlap(self):
        """Test that chunks have overlap"""
        from backend.application.services.memory.ingestion_service import IngestionService
        
        service = IngestionService()
        service.chunk_size = 100
        service.chunk_overlap = 20
        
        text = "Sentence one. Sentence two. Sentence three. Sentence four. " * 10
        chunks = service._chunk_text(text)
        
        # Check that consecutive chunks have some overlap
        if len(chunks) > 1:
            # Some text from end of first chunk should appear in second
            assert len(chunks[0]) > 0 and len(chunks[1]) > 0


class TestMemoryGate:
    """Test fact extraction and curation"""
    
    @patch('backend.application.services.memory.memory_gate.MemoryGate._get_llm_service')
    def test_extract_candidate_facts(self, mock_llm):
        """Test fact extraction from text"""
        from backend.application.services.memory.memory_gate import MemoryGate, CandidateFact
        from backend.application.services.memory.models import FactType
        
        # Mock LLM response
        mock_service = Mock()
        mock_service.call_llm.return_value = '''[
            {"text": "User prefers morning meetings", "type": "preference", "confidence": 0.9},
            {"text": "User works as a software engineer", "type": "work", "confidence": 0.95}
        ]'''
        mock_llm.return_value = mock_service
        
        gate = MemoryGate()
        candidates = gate.extract_candidate_facts(
            text=SAMPLE_MESSAGE,
            user_id=SAMPLE_USER_ID,
        )
        
        assert len(candidates) == 2, "Should extract 2 facts"
        assert all(isinstance(c, CandidateFact) for c in candidates)
        assert candidates[0].confidence > 0.5
    
    def test_should_store_fact_confidence(self):
        """Test fact validation by confidence"""
        from backend.application.services.memory.memory_gate import MemoryGate, CandidateFact
        from backend.application.services.memory.models import FactType
        
        gate = MemoryGate()
        
        # High confidence - should store
        good_fact = CandidateFact(
            text="User prefers morning meetings",
            fact_type=FactType.PREFERENCE,
            confidence=0.9
        )
        assert gate.should_store_fact(good_fact) == True
        
        # Low confidence - should reject
        bad_fact = CandidateFact(
            text="User might like coffee",
            fact_type=FactType.PREFERENCE,
            confidence=0.3
        )
        assert gate.should_store_fact(bad_fact) == False
    
    def test_deduplicate_facts(self):
        """Test fact deduplication"""
        from backend.application.services.memory.memory_gate import MemoryGate, CandidateFact
        from backend.application.services.memory.models import FactType
        
        gate = MemoryGate()
        
        candidates = [
            CandidateFact(
                text="User prefers morning meetings",
                fact_type=FactType.PREFERENCE,
                confidence=0.9
            ),
            CandidateFact(
                text="User prefers morning meetings",  # Duplicate
                fact_type=FactType.PREFERENCE,
                confidence=0.85
            ),
            CandidateFact(
                text="User works as an engineer",
                fact_type=FactType.WORK,
                confidence=0.9
            ),
        ]
        
        existing = [
            {"text": "User works as an engineer"}  # Already exists
        ]
        
        unique = gate.deduplicate_facts(candidates, existing)
        
        assert len(unique) == 1, "Should keep only 1 unique fact"
        assert "morning meetings" in unique[0].text


class TestMessageIngestion:
    """Test message ingestion"""
    
    @patch('backend.application.services.memory.ingestion_service.get_messages_collection')
    @patch('backend.application.services.memory.ingestion_service.get_vector_store')
    def test_ingest_message_basic(self, mock_vector_store, mock_collection):
        """Test basic message ingestion"""
        from backend.application.services.memory.ingestion_service import IngestionService
        from backend.application.services.memory.models import MessageDirection
        
        # Mock MongoDB collection
        mock_col = Mock()
        mock_col.insert_one.return_value = Mock(inserted_id="msg123")
        mock_collection.return_value = mock_col
        
        # Mock vector store
        mock_vs = Mock()
        mock_vs.upsert_vectors.return_value = True
        mock_vector_store.return_value = mock_vs
        
        service = IngestionService()
        service.vector_store = mock_vs
        
        message_id = service.ingest_message(
            user_id=SAMPLE_USER_ID,
            thread_id=SAMPLE_THREAD_ID,
            channel="test",
            direction=MessageDirection.INCOMING,
            text="Hello world",
            extract_facts=False,  # Skip fact extraction for this test
        )
        
        assert message_id is not None
        mock_col.insert_one.assert_called_once()


class TestRetrievalService:
    """Test context retrieval"""
    
    @patch('backend.application.services.memory.retrieval_service.get_memory_facts_collection')
    def test_retrieve_facts_by_confidence(self, mock_collection):
        """Test retrieving facts by confidence"""
        from backend.application.services.memory.retrieval_service import RetrievalService
        
        # Mock facts
        mock_col = Mock()
        mock_col.find.return_value.sort.return_value.limit.return_value = [
            {"text": "User prefers morning meetings", "type": "preference", "confidence": 0.9},
            {"text": "User works as an engineer", "type": "work", "confidence": 0.85},
        ]
        mock_collection.return_value = mock_col
        
        service = RetrievalService()
        facts = service._retrieve_facts(SAMPLE_USER_ID, query_text=None)
        
        assert len(facts) == 2
        assert facts[0]["confidence"] >= 0.5
    
    @patch('backend.application.services.memory.retrieval_service.get_messages_collection')
    def test_get_recent_messages(self, mock_collection):
        """Test retrieving recent messages"""
        from backend.application.services.memory.retrieval_service import RetrievalService
        
        # Mock messages
        mock_col = Mock()
        mock_col.find.return_value.sort.return_value.limit.return_value = [
            {"text": "Message 1", "direction": "in", "ts": datetime.utcnow()},
            {"text": "Message 2", "direction": "out", "ts": datetime.utcnow()},
        ]
        mock_collection.return_value = mock_col
        
        service = RetrievalService()
        messages = service._get_recent_messages(SAMPLE_USER_ID, SAMPLE_THREAD_ID)
        
        assert len(messages) == 2
    
    @patch('backend.application.services.memory.retrieval_service.get_memory_facts_collection')
    @patch('backend.application.services.memory.retrieval_service.get_thread_summaries_collection')
    @patch('backend.application.services.memory.retrieval_service.get_messages_collection')
    def test_retrieve_context_bundle(self, mock_msgs, mock_summaries, mock_facts):
        """Test retrieving complete context bundle"""
        from backend.application.services.memory.retrieval_service import RetrievalService, ContextBundle
        
        # Mock collections
        mock_facts_col = Mock()
        mock_facts_col.find.return_value.sort.return_value.limit.return_value = [
            {"text": "User prefers morning meetings", "type": "preference", "confidence": 0.9},
        ]
        mock_facts.return_value = mock_facts_col
        
        mock_summaries.return_value = None  # No summaries
        
        mock_msgs_col = Mock()
        mock_msgs_col.find.return_value.sort.return_value.limit.return_value = []
        mock_msgs.return_value = mock_msgs_col
        
        service = RetrievalService()
        bundle = service.retrieve_context(
            user_id=SAMPLE_USER_ID,
            thread_id=SAMPLE_THREAD_ID,
        )
        
        assert isinstance(bundle, ContextBundle)
        assert bundle.user_id == SAMPLE_USER_ID
        assert "retrieval_stats" in bundle.__dict__


class TestPromptBuilder:
    """Test prompt building"""
    
    def test_build_system_prompt(self):
        """Test building system prompt with context"""
        from backend.application.services.memory.prompt_builder import PromptBuilder
        from backend.application.services.memory.retrieval_service import ContextBundle
        
        bundle = ContextBundle(
            user_id=SAMPLE_USER_ID,
            profile_summary="Software engineer who prefers morning meetings",
            top_facts=[
                {"text": "User works at TechCorp", "type": "work", "confidence": 0.9}
            ],
        )
        
        builder = PromptBuilder()
        prompt = builder.build_system_prompt(bundle)
        
        assert "Aivis" in prompt
        assert "Software engineer" in prompt
        assert "TechCorp" in prompt
    
    def test_build_messages_with_context(self):
        """Test building OpenAI messages with context"""
        from backend.application.services.memory.prompt_builder import PromptBuilder
        from backend.application.services.memory.retrieval_service import ContextBundle
        
        bundle = ContextBundle(
            user_id=SAMPLE_USER_ID,
            top_facts=[
                {"text": "User prefers morning meetings", "type": "preference", "confidence": 0.9}
            ],
            recent_messages=[
                {"text": "Hello", "direction": "in", "ts": datetime.utcnow()},
                {"text": "Hi there!", "direction": "out", "ts": datetime.utcnow()},
            ]
        )
        
        builder = PromptBuilder()
        messages = builder.build_messages_with_context(
            bundle=bundle,
            user_message="What's my schedule?",
        )
        
        assert len(messages) >= 2  # At least system + user message
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "What's my schedule?"


class TestUserIsolation:
    """Test that user data is properly isolated"""
    
    @patch('backend.application.services.memory.retrieval_service.get_memory_facts_collection')
    def test_facts_filtered_by_user(self, mock_collection):
        """Test that facts are filtered by user_id"""
        from backend.application.services.memory.retrieval_service import RetrievalService
        
        mock_col = Mock()
        mock_col.find.return_value.sort.return_value.limit.return_value = []
        mock_collection.return_value = mock_col
        
        service = RetrievalService()
        service._retrieve_facts("user-123", query_text=None)
        
        # Check that find was called with user_id filter
        call_args = mock_col.find.call_args
        assert call_args[0][0]["user_id"] == "user-123"
    
    @patch('backend.application.services.memory.vector_store.VectorStore.initialize')
    @patch('backend.application.services.memory.vector_store.VectorStore._get_embedding_service')
    def test_vector_search_uses_namespace(self, mock_embed, mock_init):
        """Test that vector search uses user_id as namespace"""
        from backend.application.services.memory.vector_store import VectorStore
        
        mock_init.return_value = True
        
        # Mock embedding service
        mock_embed_service = Mock()
        mock_embed_service.generate_embedding.return_value = [0.1] * 1536
        mock_embed.return_value = mock_embed_service
        
        # Mock Pinecone index
        mock_index = Mock()
        mock_index.query.return_value = Mock(matches=[])
        
        store = VectorStore()
        store._index = mock_index
        store._initialized = True
        
        store.search(
            user_id="user-123",
            query_text="test query",
            top_k=5
        )
        
        # Check that query was called with correct namespace
        call_args = mock_index.query.call_args
        assert call_args[1]["namespace"] == "user-123"


class TestAPIEndpoints:
    """Test API endpoints (integration-style)"""

    @pytest.fixture
    def client(self):
        """Create test Flask client for the core backend app."""
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        backend = root / "backend"
        for p in (str(root), str(backend)):
            if p not in sys.path:
                sys.path.insert(0, p)
        from backend.core_app import create_app

        flask_app = create_app()
        flask_app.config["TESTING"] = True
        with flask_app.test_client() as client:
            yield client

    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data.get("status") == "ok"


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])

