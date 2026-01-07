"""
Vector Store Interface for Memory System

Provides a clean abstraction over Pinecone for storing and retrieving embeddings.
Uses email addresses as namespaces for data isolation and security.
"""

import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from uuid import uuid4

from app.config import Config

logger = logging.getLogger(__name__)


@dataclass
class VectorMatch:
    """Result from vector search"""
    id: str
    score: float
    metadata: Dict[str, Any]
    text: Optional[str] = None


class VectorStore:
    """
    Vector database interface with Pinecone backend.
    
    Features:
    - User-isolated namespaces (namespace = user email address)
    - Type-tagged vectors (fact, summary, doc_chunk, message)
    - Metadata filtering
    """
    
    def __init__(self, embedding_service=None):
        """
        Initialize vector store.
        
        Args:
            embedding_service: Service to generate embeddings
        """
        self.embedding_service = embedding_service
        self._index = None
        self._initialized = False
        self._dimension = 1536  # OpenAI ada-002 dimension
    
    def _get_embedding_service(self):
        """Lazy load embedding service"""
        if self.embedding_service is None:
            from app.services.llm_service import get_llm_service
            self.embedding_service = get_llm_service()
        return self.embedding_service
    
    def _get_canonical_namespace(self, user_id: str) -> str:
        """
        Get canonical Pinecone namespace for user.
        
        Strategy:
        1. Try to get from users.memory_namespace (canonical format)
        2. Fallback to email (via user_email_utils)
        3. Fallback to user_id
        
        Args:
            user_id: User identifier
            
        Returns:
            Canonical namespace (u:<userId> preferred, or email/user_id as fallback)
        """
        try:
            from app.memory.models import get_users_collection
            users_col = get_users_collection()
            
            if users_col:
                user = users_col.find_one({"user_id": user_id})
                if user and "memory_namespace" in user:
                    namespace = user["memory_namespace"]
                    logger.debug(f"Using canonical namespace for {user_id}: {namespace}")
                    return namespace
        except Exception as e:
            logger.debug(f"Could not get canonical namespace for {user_id}: {e}")
        
        # Fallback to email
        try:
            from app.utils.user_email_utils import get_user_email
            namespace = get_user_email(user_id)
            logger.debug(f"Using email namespace for {user_id}: {namespace}")
            return namespace
        except Exception as e:
            logger.debug(f"Could not get email for {user_id}: {e}")
        
        # Final fallback to user_id
        logger.debug(f"Using user_id as namespace fallback: {user_id}")
        return user_id.lower().strip()
    
    def initialize(self) -> bool:
        """
        Initialize Pinecone connection (lazy).
        
        Returns:
            bool: True if initialized successfully
        """
        if self._initialized:
            return True
        
        api_key = Config.PINECONE_API_KEY
        if not api_key:
            logger.warning("PINECONE_API_KEY not set - vector store disabled")
            self._initialized = True
            return False
        
        try:
            from pinecone import Pinecone, ServerlessSpec
            
            index_name = Config.PINECONE_INDEX_NAME
            pc = Pinecone(api_key=api_key)
            
            # Check if index exists
            existing_indexes = [idx.name for idx in pc.list_indexes()]
            
            if index_name not in existing_indexes:
                logger.info(f"Creating Pinecone index: {index_name}")
                pc.create_index(
                    name=index_name,
                    dimension=self._dimension,
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region=Config.PINECONE_ENV
                    )
                )
                logger.info(f"✅ Created Pinecone index: {index_name}")
            
            self._index = pc.Index(index_name)
            self._initialized = True
            logger.info(f"✅ Vector store initialized: {index_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            self._initialized = True  # Don't retry on every call
            return False
    
    def upsert_vectors(
        self,
        user_id: str,
        vectors: List[Dict[str, Any]],
        vector_type: str,
    ) -> bool:
        """
        Upsert vectors to user's namespace.
        
        Args:
            user_id: User ID (will be converted to email for namespace)
            vectors: List of dicts with keys: id, text, metadata
            vector_type: Type tag (fact, summary, doc_chunk, message)
        
        Returns:
            bool: True if successful
        """
        if not self.initialize() or self._index is None:
            return False
        
        try:
            # Get user email for namespace (fallback to user_id if email not available)
            from app.utils.user_email_utils import get_user_email
            namespace = get_user_email(user_id)
            
            embedding_service = self._get_embedding_service()
            records = []
            
            for vec in vectors:
                # Generate embedding
                text = vec.get("text", "")
                if not text:
                    continue
                
                embedding = embedding_service.generate_embedding(text)
                
                # Prepare metadata
                metadata = {
                    "user_id": user_id,
                    "type": vector_type,
                    "text": text[:1000],  # Limit text in metadata
                    **(vec.get("metadata", {}))
                }
                
                # Add to records
                vector_id = vec.get("id", f"{vector_type}-{uuid4().hex[:8]}")
                records.append({
                    "id": vector_id,
                    "values": embedding,
                    "metadata": metadata
                })
            
            if records:
                self._index.upsert(
                    vectors=records,
                    namespace=namespace
                )
                logger.info(f"✅ Upserted {len(records)} vectors for user {user_id} (namespace={namespace}, type={vector_type})")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to upsert vectors: {e}")
            return False
    
    def search(
        self,
        user_id: str,
        query_text: str,
        top_k: int = 10,
        vector_type: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[VectorMatch]:
        """
        Search vectors in user's namespace.
        
        Args:
            user_id: User ID (will be converted to email for namespace)
            query_text: Search query
            top_k: Number of results
            vector_type: Filter by type (fact, summary, doc_chunk, message)
            filters: Additional metadata filters
        
        Returns:
            List of VectorMatch objects
        """
        if not self.initialize() or self._index is None:
            return []
        
        try:
            # Get canonical namespace
            namespace = self._get_canonical_namespace(user_id)
            
            # Generate query embedding
            embedding_service = self._get_embedding_service()
            query_embedding = embedding_service.generate_embedding(query_text)
            
            # Build filter
            filter_dict = {"user_id": user_id}
            if vector_type:
                filter_dict["type"] = vector_type
            if filters:
                filter_dict.update(filters)
            
            # Query Pinecone
            response = self._index.query(
                namespace=namespace,
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                filter=filter_dict if len(filter_dict) > 1 else None
            )
            
            # Convert to VectorMatch objects
            matches = []
            for match in response.matches:
                matches.append(VectorMatch(
                    id=match.id,
                    score=match.score,
                    metadata=match.metadata or {},
                    text=match.metadata.get("text") if match.metadata else None
                ))
            
            logger.info(f"🔍 Vector search for user {user_id} (namespace={namespace}): {len(matches)} results")
            return matches
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def delete_vectors(
        self,
        user_id: str,
        vector_ids: List[str],
    ) -> bool:
        """
        Delete vectors from user's namespace.
        
        Args:
            user_id: User ID (will be converted to email for namespace)
            vector_ids: List of vector IDs to delete
        
        Returns:
            bool: True if successful
        """
        if not self.initialize() or self._index is None:
            return False
        
        try:
            # Get canonical namespace
            namespace = self._get_canonical_namespace(user_id)
            
            self._index.delete(
                ids=vector_ids,
                namespace=namespace
            )
            logger.info(f"🗑️ Deleted {len(vector_ids)} vectors for user {user_id} (namespace={namespace})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete vectors: {e}")
            return False
    
    def get_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get statistics for user's namespace.
        
        Args:
            user_id: User ID (will be converted to email for namespace)
        
        Returns:
            Dict with stats
        """
        if not self.initialize() or self._index is None:
            return {}
        
        try:
            # Get canonical namespace
            namespace = self._get_canonical_namespace(user_id)
            
            stats = self._index.describe_index_stats()
            namespace_stats = stats.namespaces.get(namespace, {})
            
            return {
                "total_vectors": namespace_stats.get("vector_count", 0),
                "dimension": stats.dimension,
            }
            
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}


# Singleton instance
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Get singleton vector store instance"""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store

