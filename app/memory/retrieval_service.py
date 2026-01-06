"""
Retrieval Service - Retrieves relevant context for prompts

This service handles:
- Retrieving user profile summary
- Searching for relevant facts
- Finding relevant thread summaries
- Searching document chunks
- Getting recent thread messages
- Hybrid ranking (recency + relevance)
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .models import (
    get_messages_collection,
    get_memory_facts_collection,
    get_thread_summaries_collection,
    get_document_chunks_collection,
)
from .vector_store import get_vector_store

logger = logging.getLogger(__name__)


@dataclass
class ContextBundle:
    """Bundle of retrieved context for prompt injection"""
    user_id: str
    thread_id: Optional[str] = None
    
    # Context components
    profile_summary: str = ""
    top_facts: List[Dict[str, Any]] = field(default_factory=list)
    top_summaries: List[Dict[str, Any]] = field(default_factory=list)
    top_doc_chunks: List[Dict[str, Any]] = field(default_factory=list)
    recent_messages: List[Dict[str, Any]] = field(default_factory=list)
    
    # Metadata
    retrieval_stats: Dict[str, Any] = field(default_factory=dict)


class RetrievalService:
    """
    Service for retrieving relevant context for prompts.
    
    Uses hybrid ranking:
    - Semantic similarity (vector search)
    - Recency boost for messages
    - Confidence weighting for facts
    """
    
    def __init__(self):
        """Initialize retrieval service"""
        self.vector_store = get_vector_store()
        
        # Hard limits for token control
        self.max_facts = 10
        self.max_summaries = 5
        self.max_doc_chunks = 8
        self.max_recent_messages = 20
    
    def retrieve_context(
        self,
        user_id: str,
        thread_id: Optional[str] = None,
        query_text: Optional[str] = None,
    ) -> ContextBundle:
        """
        Retrieve comprehensive context for user.
        
        Args:
            user_id: User ID
            thread_id: Thread ID (optional)
            query_text: Query for semantic search (optional)
        
        Returns:
            ContextBundle with all relevant context
        """
        bundle = ContextBundle(user_id=user_id, thread_id=thread_id)
        
        try:
            # 1. Generate profile summary
            bundle.profile_summary = self._generate_profile_summary(user_id)
            
            # 2. Retrieve relevant facts
            bundle.top_facts = self._retrieve_facts(user_id, query_text)
            
            # 3. Retrieve relevant thread summaries
            bundle.top_summaries = self._retrieve_summaries(user_id, thread_id, query_text)
            
            # 4. Retrieve relevant document chunks
            if query_text:
                bundle.top_doc_chunks = self._retrieve_doc_chunks(user_id, query_text)
            
            # 5. Get recent thread messages
            if thread_id:
                bundle.recent_messages = self._get_recent_messages(user_id, thread_id)
            
            # 6. Collect stats
            bundle.retrieval_stats = {
                "facts_count": len(bundle.top_facts),
                "summaries_count": len(bundle.top_summaries),
                "doc_chunks_count": len(bundle.top_doc_chunks),
                "recent_messages_count": len(bundle.recent_messages),
            }
            
            logger.info(f"🔍 Retrieved context for user {user_id}: {bundle.retrieval_stats}")
            
        except Exception as e:
            logger.error(f"Failed to retrieve context: {e}")
        
        return bundle
    
    def _generate_profile_summary(self, user_id: str) -> str:
        """
        Generate a short profile summary from top facts.
        
        Args:
            user_id: User ID
        
        Returns:
            Profile summary string
        """
        try:
            facts_col = get_memory_facts_collection()
            if facts_col is None:
                return ""
            
            # Get top identity and preference facts
            facts = list(facts_col.find(
                {
                    "user_id": user_id,
                    "is_active": True,
                    "type": {"$in": ["identity", "preference"]}
                },
                {"text": 1, "confidence": 1}
            ).sort("confidence", -1).limit(5))
            
            if not facts:
                return "No profile information available."
            
            # Combine into summary
            fact_texts = [f["text"] for f in facts]
            summary = " ".join(fact_texts[:3])  # Top 3 facts
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to generate profile summary: {e}")
            return ""
    
    def _retrieve_facts(
        self,
        user_id: str,
        query_text: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant facts.
        
        Uses vector search if query provided, otherwise returns top facts by confidence.
        
        Args:
            user_id: User ID
            query_text: Query for semantic search
        
        Returns:
            List of fact dicts
        """
        try:
            if query_text:
                # Vector search
                matches = self.vector_store.search(
                    user_id=user_id,
                    query_text=query_text,
                    top_k=self.max_facts,
                    vector_type="fact"
                )
                
                # Convert to fact format
                facts = []
                for match in matches:
                    facts.append({
                        "text": match.text or match.metadata.get("text", ""),
                        "type": match.metadata.get("fact_type", "other"),
                        "confidence": match.metadata.get("confidence", 0.5),
                        "score": match.score,
                    })
                
                return facts
            
            else:
                # Get top facts by confidence
                facts_col = get_memory_facts_collection()
                if facts_col is None:
                    return []
                
                facts = list(facts_col.find(
                    {"user_id": user_id, "is_active": True},
                    {"text": 1, "type": 1, "confidence": 1}
                ).sort("confidence", -1).limit(self.max_facts))
                
                return facts
                
        except Exception as e:
            logger.error(f"Failed to retrieve facts: {e}")
            return []
    
    def _retrieve_summaries(
        self,
        user_id: str,
        thread_id: Optional[str] = None,
        query_text: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant thread summaries.
        
        Args:
            user_id: User ID
            thread_id: Current thread ID (prioritized)
            query_text: Query for semantic search
        
        Returns:
            List of summary dicts
        """
        try:
            summaries = []
            
            # First, get current thread summary if available
            if thread_id:
                summaries_col = get_thread_summaries_collection()
                if summaries_col:
                    current_summary = summaries_col.find_one({
                        "user_id": user_id,
                        "thread_id": thread_id
                    })
                    
                    if current_summary:
                        summaries.append({
                            "thread_id": current_summary["thread_id"],
                            "summary_text": current_summary["summary_text"],
                            "updated_at": current_summary["updated_at"],
                            "is_current": True,
                        })
            
            # Then search for related summaries
            if query_text and len(summaries) < self.max_summaries:
                matches = self.vector_store.search(
                    user_id=user_id,
                    query_text=query_text,
                    top_k=self.max_summaries - len(summaries),
                    vector_type="summary"
                )
                
                for match in matches:
                    if match.metadata.get("thread_id") != thread_id:  # Don't duplicate
                        summaries.append({
                            "thread_id": match.metadata.get("thread_id"),
                            "summary_text": match.text or "",
                            "score": match.score,
                            "is_current": False,
                        })
            
            return summaries[:self.max_summaries]
            
        except Exception as e:
            logger.error(f"Failed to retrieve summaries: {e}")
            return []
    
    def _retrieve_doc_chunks(
        self,
        user_id: str,
        query_text: str,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant document chunks.
        
        Args:
            user_id: User ID
            query_text: Query for semantic search
        
        Returns:
            List of chunk dicts with doc metadata
        """
        try:
            matches = self.vector_store.search(
                user_id=user_id,
                query_text=query_text,
                top_k=self.max_doc_chunks,
                vector_type="doc_chunk"
            )
            
            chunks = []
            for match in matches:
                chunks.append({
                    "text": match.text or "",
                    "doc_title": match.metadata.get("doc_title", "Unknown"),
                    "chunk_index": match.metadata.get("chunk_index", 0),
                    "score": match.score,
                })
            
            return chunks
            
        except Exception as e:
            logger.error(f"Failed to retrieve doc chunks: {e}")
            return []
    
    def _get_recent_messages(
        self,
        user_id: str,
        thread_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get recent messages from thread.
        
        Args:
            user_id: User ID
            thread_id: Thread ID
        
        Returns:
            List of message dicts (recent first)
        """
        try:
            messages_col = get_messages_collection()
            if messages_col is None:
                return []
            
            messages = list(messages_col.find(
                {"user_id": user_id, "thread_id": thread_id},
                {"text": 1, "direction": 1, "ts": 1}
            ).sort("ts", -1).limit(self.max_recent_messages))
            
            # Reverse to chronological order
            messages.reverse()
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get recent messages: {e}")
            return []
    
    def search_facts(
        self,
        user_id: str,
        query: Optional[str] = None,
        fact_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search user facts (for API endpoint).
        
        Args:
            user_id: User ID
            query: Search query
            fact_type: Filter by fact type
            limit: Max results
        
        Returns:
            List of facts
        """
        try:
            facts_col = get_memory_facts_collection()
            if facts_col is None:
                return []
            
            # Build MongoDB query
            mongo_query = {"user_id": user_id, "is_active": True}
            if fact_type:
                mongo_query["type"] = fact_type
            
            if query:
                # Vector search
                matches = self.vector_store.search(
                    user_id=user_id,
                    query_text=query,
                    top_k=limit,
                    vector_type="fact"
                )
                
                facts = []
                for match in matches:
                    facts.append({
                        "_id": match.id,
                        "text": match.text or match.metadata.get("text", ""),
                        "type": match.metadata.get("fact_type", "other"),
                        "confidence": match.metadata.get("confidence", 0.5),
                        "score": match.score,
                    })
                
                return facts
            else:
                # Regular DB query
                facts = list(facts_col.find(
                    mongo_query,
                    {"text": 1, "type": 1, "confidence": 1, "created_at": 1}
                ).sort("confidence", -1).limit(limit))
                
                return facts
                
        except Exception as e:
            logger.error(f"Failed to search facts: {e}")
            return []


# Singleton instance
_retrieval_service: Optional[RetrievalService] = None


def get_retrieval_service() -> RetrievalService:
    """Get singleton retrieval service instance"""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service

