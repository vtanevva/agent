"""
Memory Service - handles conversation memory and fact storage.

This service is responsible for:
- Storing and retrieving conversation history (MongoDB)
- Managing user facts and context (Pinecone/FAISS)
- Vector search for relevant memories
"""

import os
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv()


class MemoryService:
    """
    Service for memory and conversation management.
    
    Handles both:
    - Structured storage (MongoDB for conversations)
    - Vector storage (Pinecone for semantic search)
    """
    
    def __init__(self, llm_service=None):
        """
        Initialize the Memory service.
        
        Parameters
        ----------
        llm_service : LLMService, optional
            LLM service for embeddings (will create if not provided)
        """
        self.llm_service = llm_service
        self._pinecone_index = None
        self._pinecone_initialized = False
        self._init_pinecone()
    
    def _init_pinecone(self):
        """Initialize Pinecone client if API key is available (lazy initialization)."""
        # Don't actually initialize here - do it on first use
        # This prevents hanging during app startup
        self._pinecone_initialized = False
    
    def _ensure_pinecone(self):
        """Lazy initialization of Pinecone on first use."""
        if self._pinecone_initialized:
            return
        
        pinecone_key = os.getenv("PINECONE_API_KEY", "").strip()
        
        if not pinecone_key:
            print("⚠️ PINECONE_API_KEY not set - vector memory disabled")
            self._pinecone_initialized = True
            return
        
        try:
            from pinecone import Pinecone
            
            index_name = os.getenv("PINECONE_INDEX_NAME", "chatbot-facts").strip()
            pc = Pinecone(api_key=pinecone_key)
            
            # Check if index exists, create if not
            existing = [ix["name"] for ix in pc.list_indexes()]
            if index_name not in existing:
                pc.create_index(
                    name=index_name,
                    dimension=1536,
                    metric="cosine"
                )
                print(f"✅ Created Pinecone index: {index_name}")
            
            self._pinecone_index = pc.Index(index_name)
            print(f"✅ Pinecone initialized: {index_name}")
        except Exception as e:
            print(f"❌ Error initializing Pinecone: {e}")
            print("⚠️ Continuing without vector memory")
        finally:
            self._pinecone_initialized = True
    
    def _get_llm_service(self):
        """Get or create LLM service for embeddings."""
        if self.llm_service is None:
            from app.services.llm_service import get_llm_service
            self.llm_service = get_llm_service()
        return self.llm_service
    
    def _should_embed(self, text: str) -> bool:
        """Check if text is worth embedding."""
        ignore_phrases = ("thank you", "hi", "ok", "sure", "bye", "thanks")
        if any(phrase in text.lower() for phrase in ignore_phrases):
            return False
        return len(text.split()) >= 3
    
    def save_conversation(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        bot_reply: str,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Save a conversation turn to MongoDB.
        
        Parameters
        ----------
        user_id : str
            User identifier
        session_id : str
            Session identifier
        user_message : str
            User's message
        bot_reply : str
            Bot's reply
        metadata : dict, optional
            Additional metadata (emotion, flags, etc.)
            
        Returns
        -------
        bool
            True if saved successfully
        """
        from app.db.collections import get_conversations_collection
        
        conversations = get_conversations_collection()
        if conversations is None:
            return False
        
        try:
            metadata = metadata or {}
            message_pair = {
                "timestamp": datetime.utcnow().isoformat(),
                "role": "user",
                "text": user_message,
                **metadata,
            }
            bot_response = {
                "timestamp": datetime.utcnow().isoformat(),
                "role": "bot",
                "text": bot_reply,
            }
            
            conversations.update_one(
                {"user_id": user_id, "session_id": session_id},
                {
                    "$setOnInsert": {
                        "user_id": user_id,
                        "session_id": session_id,
                        "created_at": datetime.utcnow(),
                    },
                    "$push": {"messages": {"$each": [message_pair, bot_response]}},
                },
                upsert=True,
            )
            return True
        except Exception as e:
            print(f"[ERROR] MemoryService.save_conversation failed: {e}", flush=True)
            return False
    
    def get_session_history(
        self,
        user_id: str,
        session_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve session history in OpenAI message format.
        
        Parameters
        ----------
        user_id : str
            User identifier
        session_id : str
            Session identifier
        limit : int
            Maximum number of messages to retrieve
            
        Returns
        -------
        list of dict
            Messages in format [{"role": "user", "content": "..."},  ...]
        """
        from app.db.collections import get_conversations_collection
        
        conversations = get_conversations_collection()
        if conversations is None:
            return []
        
        try:
            doc = conversations.find_one(
                {"user_id": user_id, "session_id": session_id},
                {"messages": {"$slice": -limit}}
            )
            
            if not doc or "messages" not in doc:
                return []
            
            # Convert to OpenAI format
            messages = []
            for msg in doc["messages"]:
                role = msg.get("role", "user")
                content = msg.get("text") or msg.get("content", "")
                if role in ("user", "assistant", "bot"):
                    messages.append({
                        "role": "assistant" if role == "bot" else role,
                        "content": content,
                    })
            
            return messages
        except Exception as e:
            print(f"[ERROR] MemoryService.get_session_history failed: {e}", flush=True)
            return []
    
    def save_fact(
        self,
        user_id: str,
        fact: str,
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Save a fact about the user to vector storage.
        
        Parameters
        ----------
        user_id : str
            User identifier
        fact : str
            Fact text to save
        session_id : str, optional
            Session where fact was extracted
        metadata : dict, optional
            Additional metadata
            
        Returns
        -------
        bool
            True if saved successfully
        """
        self._ensure_pinecone()
        
        if not self._pinecone_index or not self._should_embed(fact):
            return False
        
        try:
            # Generate embedding
            llm_service = self._get_llm_service()
            embedding = llm_service.generate_embedding(fact)
            
            # Create vector ID
            vector_id = f"{session_id or 'fact'}-{uuid4().hex[:6]}"
            
            # Prepare metadata
            meta = {
                "text": fact,
                "user_id": user_id,
                **(metadata or {}),
            }
            if session_id:
                meta["session_id"] = session_id
            
            # Upsert to Pinecone
            self._pinecone_index.upsert(
                vectors=[{"id": vector_id, "values": embedding, "metadata": meta}],
                namespace=user_id,
            )
            
            print(f"✅ [🧠 FACT SAVED] {fact!r} (id={vector_id}, user={user_id})")
            return True
        except Exception as e:
            print(f"[ERROR] MemoryService.save_fact failed: {e}", flush=True)
            return False
    
    def retrieve_facts(
        self,
        user_id: str,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> List[str]:
        """
        Retrieve facts about the user.
        
        If query is provided, does semantic search.
        Otherwise, retrieves recent facts.
        
        Parameters
        ----------
        user_id : str
            User identifier
        query : str, optional
            Search query for semantic search
        limit : int
            Maximum number of facts to retrieve
            
        Returns
        -------
        list of str
            List of fact texts
        """
        self._ensure_pinecone()
        
        if not self._pinecone_index:
            return []
        
        try:
            if query:
                # Semantic search with query embedding
                llm_service = self._get_llm_service()
                embedding = llm_service.generate_embedding(query)
            else:
                # Random vector for general retrieval
                embedding = np.random.rand(1536).tolist()
            
            response = self._pinecone_index.query(
                namespace=user_id,
                vector=embedding,
                top_k=min(limit, 200),
                include_metadata=True,
            )
            
            facts = []
            for match in response.matches:
                if match.metadata:
                    text = match.metadata.get("text") or match.metadata.get("fact")
                    if text and text not in facts:
                        facts.append(text)
            
            return facts[:limit]
        except Exception as e:
            print(f"[ERROR] MemoryService.retrieve_facts failed: {e}", flush=True)
            return []
    
    def search_memory(
        self,
        user_id: str,
        query: str,
        top_k: int = 3,
    ) -> List[str]:
        """
        Search conversation memory using semantic search.
        
        Alias for retrieve_facts with a query.
        
        Parameters
        ----------
        user_id : str
            User identifier
        query : str
            Search query
        top_k : int
            Number of results to return
            
        Returns
        -------
        list of str
            Matching fact texts
        """
        return self.retrieve_facts(user_id=user_id, query=query, limit=top_k)


# Singleton instance
_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    """Get the singleton Memory service instance."""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service

