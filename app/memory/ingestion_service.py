"""
Ingestion Service - Ingests messages and documents into memory

This service handles:
- Message ingestion (from any channel)
- Document ingestion and chunking
- Triggering memory extraction
- Updating thread summaries
- Embedding and vectorizing content
"""

import logging
import os
import re
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import uuid4

from app.config import Config
from .models import (
    MessageDirection,
    DocumentSource,
    DocumentPermission,
    get_messages_collection,
    get_thread_summaries_collection,
    get_documents_collection,
    get_document_chunks_collection,
)
from .vector_store import get_vector_store
from .memory_gate import get_memory_gate

logger = logging.getLogger(__name__)


class IngestionService:
    """
    Service for ingesting messages and documents into memory system.
    """
    
    def __init__(self):
        """Initialize ingestion service"""
        self.vector_store = get_vector_store()
        self.memory_gate = get_memory_gate()
        self._llm_service = None
        
        # Chunking parameters
        self.chunk_size = 800  # tokens
        self.chunk_overlap = 100  # tokens
    
    def _get_llm_service(self):
        """Lazy load LLM service"""
        if self._llm_service is None:
            from app.services.llm_service import get_llm_service
            self._llm_service = get_llm_service()
        return self._llm_service
    
    def ingest_message(
        self,
        user_id: str,
        thread_id: str,
        channel: str,
        direction: MessageDirection,
        text: str,
        ts: Optional[datetime] = None,
        source_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        extract_facts: bool = True,
    ) -> Optional[str]:
        """
        Ingest a message into memory system.
        
        Args:
            user_id: User ID
            thread_id: Thread/conversation ID
            channel: Channel (whatsapp, email, web_chat, etc.)
            direction: Message direction (in/out)
            text: Message text
            ts: Timestamp (defaults to now)
            source_id: Original message ID from source system
            meta: Additional metadata
            extract_facts: Whether to extract facts (async)
        
        Returns:
            Message ID if successful, None otherwise
        """
        messages_col = get_messages_collection()
        if messages_col is None:
            logger.warning("Messages collection not available")
            return None
        
        try:
            message_id = str(uuid4())
            message_doc = {
                "_id": message_id,
                "user_id": user_id,
                "thread_id": thread_id,
                "channel": channel,
                "direction": direction.value if isinstance(direction, MessageDirection) else direction,
                "text": text,
                "ts": ts or datetime.utcnow(),
                "source_id": source_id,
                "meta": meta or {},
            }
            
            messages_col.insert_one(message_doc)
            logger.info(f"📥 Ingested message: user={user_id}, thread={thread_id}, channel={channel}")
            
            # Embed message to vector store (async in production)
            if len(text) > 20:  # Skip very short messages
                self._embed_message(user_id, message_id, thread_id, text, ts or datetime.utcnow())
            
            # Extract facts if enabled and message is from user
            if extract_facts and direction == MessageDirection.INCOMING:
                self._extract_and_store_facts(user_id, text, message_id)
            
            # Update thread summary (every 5 messages or so)
            self._maybe_update_thread_summary(user_id, thread_id)
            
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to ingest message: {e}")
            return None
    
    def _embed_message(
        self,
        user_id: str,
        message_id: str,
        thread_id: str,
        text: str,
        ts: datetime,
    ):
        """Embed and store message vector"""
        try:
            vectors = [{
                "id": message_id,
                "text": text,
                "metadata": {
                    "thread_id": thread_id,
                    "ts": ts.isoformat(),
                }
            }]
            
            self.vector_store.upsert_vectors(
                user_id=user_id,
                vectors=vectors,
                vector_type="message"
            )
            
        except Exception as e:
            logger.error(f"Failed to embed message: {e}")
    
    def _extract_and_store_facts(
        self,
        user_id: str,
        text: str,
        source_ref: str,
    ):
        """Extract and store facts from text"""
        try:
            # Extract candidate facts
            candidates = self.memory_gate.extract_candidate_facts(
                text=text,
                user_id=user_id,
                source_ref=source_ref,
            )
            
            if not candidates:
                return
            
            # Get existing facts for deduplication
            from .models import get_memory_facts_collection
            facts_col = get_memory_facts_collection()
            
            if facts_col:
                existing_facts = list(facts_col.find(
                    {"user_id": user_id, "is_active": True},
                    {"text": 1}
                ))
                
                # Deduplicate
                candidates = self.memory_gate.deduplicate_facts(candidates, existing_facts)
            
            # Store facts
            stored_count = self.memory_gate.store_facts(user_id, candidates)
            
            if stored_count > 0:
                # Also embed facts to vector store
                self._embed_facts(user_id, candidates)
                logger.info(f"✅ Extracted and stored {stored_count} facts")
            
        except Exception as e:
            logger.error(f"Failed to extract facts: {e}")
    
    def _embed_facts(self, user_id: str, candidates: List[Any]):
        """Embed facts to vector store"""
        try:
            vectors = []
            for candidate in candidates:
                vectors.append({
                    "id": f"fact-{uuid4().hex[:8]}",
                    "text": candidate.text,
                    "metadata": {
                        "fact_type": candidate.fact_type.value,
                        "confidence": candidate.confidence,
                    }
                })
            
            if vectors:
                self.vector_store.upsert_vectors(
                    user_id=user_id,
                    vectors=vectors,
                    vector_type="fact"
                )
                
        except Exception as e:
            logger.error(f"Failed to embed facts: {e}")
    
    def _maybe_update_thread_summary(self, user_id: str, thread_id: str):
        """Update thread summary if threshold reached"""
        try:
            messages_col = get_messages_collection()
            summaries_col = get_thread_summaries_collection()
            
            if not messages_col or not summaries_col:
                return
            
            # Check message count since last summary
            summary_doc = summaries_col.find_one({"user_id": user_id, "thread_id": thread_id})
            
            if summary_doc:
                last_summary_ts = summary_doc.get("window_end_ts")
                message_count = messages_col.count_documents({
                    "user_id": user_id,
                    "thread_id": thread_id,
                    "ts": {"$gt": last_summary_ts}
                })
            else:
                message_count = messages_col.count_documents({
                    "user_id": user_id,
                    "thread_id": thread_id,
                })
            
            # Update summary if threshold reached (5+ new messages)
            if message_count >= 5:
                self.update_thread_summary(user_id, thread_id)
                
        except Exception as e:
            logger.error(f"Failed to check thread summary: {e}")
    
    def update_thread_summary(self, user_id: str, thread_id: str) -> bool:
        """
        Generate or update thread summary.
        
        Args:
            user_id: User ID
            thread_id: Thread ID
        
        Returns:
            bool: True if successful
        """
        try:
            messages_col = get_messages_collection()
            summaries_col = get_thread_summaries_collection()
            
            if not messages_col or not summaries_col:
                return False
            
            # Get summary doc
            summary_doc = summaries_col.find_one({"user_id": user_id, "thread_id": thread_id})
            
            # Get messages to summarize
            if summary_doc:
                last_summary_ts = summary_doc.get("window_end_ts")
                query = {
                    "user_id": user_id,
                    "thread_id": thread_id,
                    "ts": {"$gt": last_summary_ts}
                }
            else:
                query = {"user_id": user_id, "thread_id": thread_id}
            
            messages = list(messages_col.find(query).sort("ts", 1).limit(50))
            
            if not messages:
                return False
            
            # Generate summary using LLM
            llm_service = self._get_llm_service()
            
            messages_text = "\n".join([
                f"[{msg['direction'].upper()}] {msg['text']}"
                for msg in messages
            ])
            
            prompt = f"""Summarize this conversation thread concisely (2-3 sentences).
Focus on key topics, decisions, and action items.

Thread messages:
{messages_text}

Summary:"""
            
            summary_text = llm_service.call_llm(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
            ).strip()
            
            # Store summary
            window_start = messages[0]["ts"]
            window_end = messages[-1]["ts"]
            
            summary_id = summary_doc.get("_id") if summary_doc else str(uuid4())
            
            summaries_col.update_one(
                {"user_id": user_id, "thread_id": thread_id},
                {
                    "$set": {
                        "_id": summary_id,
                        "user_id": user_id,
                        "thread_id": thread_id,
                        "summary_text": summary_text,
                        "updated_at": datetime.utcnow(),
                        "window_start_ts": window_start,
                        "window_end_ts": window_end,
                        "message_count": len(messages),
                    }
                },
                upsert=True
            )
            
            # Embed summary to vector store
            self.vector_store.upsert_vectors(
                user_id=user_id,
                vectors=[{
                    "id": summary_id,
                    "text": summary_text,
                    "metadata": {
                        "thread_id": thread_id,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                }],
                vector_type="summary"
            )
            
            logger.info(f"✅ Updated thread summary: {thread_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update thread summary: {e}")
            return False
    
    def ingest_document(
        self,
        user_id: str,
        file_path: str,
        title: str,
        source: DocumentSource = DocumentSource.UPLOAD,
        permissions: DocumentPermission = DocumentPermission.PRIVATE,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Ingest a document (extract, chunk, embed).
        
        Args:
            user_id: User ID
            file_path: Path to document file
            title: Document title
            source: Document source
            permissions: Access permissions
            meta: Additional metadata
        
        Returns:
            Document ID if successful, None otherwise
        """
        try:
            # Extract text from document
            text = self._extract_document_text(file_path)
            
            if not text or len(text.strip()) < 50:
                logger.warning(f"Document too short or empty: {file_path}")
                return None
            
            # Store document metadata
            doc_id = str(uuid4())
            documents_col = get_documents_collection()
            
            if documents_col is None:
                logger.warning("Documents collection not available")
                return None
            
            doc_metadata = {
                "_id": doc_id,
                "user_id": user_id,
                "title": title,
                "source": source.value if isinstance(source, DocumentSource) else source,
                "created_at": datetime.utcnow(),
                "permissions": permissions.value if isinstance(permissions, DocumentPermission) else permissions,
                "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else None,
                "mime_type": self._get_mime_type(file_path),
                "meta": meta or {},
            }
            
            documents_col.insert_one(doc_metadata)
            
            # Chunk text
            chunks = self._chunk_text(text)
            logger.info(f"📄 Document chunked: {len(chunks)} chunks")
            
            # Store chunks and embed
            self._store_and_embed_chunks(user_id, doc_id, title, chunks)
            
            logger.info(f"✅ Ingested document: {title} (id={doc_id})")
            return doc_id
            
        except Exception as e:
            logger.error(f"Failed to ingest document: {e}")
            return None
    
    def _extract_document_text(self, file_path: str) -> str:
        """Extract text from document file"""
        ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if ext == ".txt":
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            elif ext == ".pdf":
                # Try to use PyPDF2
                try:
                    import PyPDF2
                    text = ""
                    with open(file_path, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        for page in reader.pages:
                            text += page.extract_text() + "\n"
                    return text
                except ImportError:
                    logger.warning("PyPDF2 not installed - cannot extract PDF text")
                    return ""
            
            elif ext in [".doc", ".docx"]:
                # Try to use python-docx
                try:
                    import docx
                    doc = docx.Document(file_path)
                    return "\n".join([para.text for para in doc.paragraphs])
                except ImportError:
                    logger.warning("python-docx not installed - cannot extract DOCX text")
                    return ""
            
            else:
                logger.warning(f"Unsupported file type: {ext}")
                return ""
                
        except Exception as e:
            logger.error(f"Failed to extract text from {file_path}: {e}")
            return ""
    
    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type from file extension"""
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            ".txt": "text/plain",
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        return mime_map.get(ext, "application/octet-stream")
    
    def _chunk_text(self, text: str) -> List[str]:
        """
        Chunk text into overlapping segments.
        
        Args:
            text: Text to chunk
        
        Returns:
            List of text chunks
        """
        # Simple chunking by characters (approximate tokens)
        # 1 token ~= 4 characters for English
        char_chunk_size = self.chunk_size * 4
        char_overlap = self.chunk_overlap * 4
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + char_chunk_size
            chunk = text[start:end]
            
            # Try to break at sentence boundary
            if end < len(text):
                last_period = chunk.rfind('.')
                last_newline = chunk.rfind('\n')
                break_point = max(last_period, last_newline)
                
                if break_point > char_chunk_size * 0.7:  # At least 70% of chunk
                    chunk = chunk[:break_point + 1]
                    end = start + break_point + 1
            
            chunks.append(chunk.strip())
            start = end - char_overlap
        
        return [c for c in chunks if len(c) > 50]  # Filter very short chunks
    
    def _store_and_embed_chunks(
        self,
        user_id: str,
        doc_id: str,
        doc_title: str,
        chunks: List[str],
    ):
        """Store chunks to MongoDB and embed to vector store"""
        chunks_col = get_document_chunks_collection()
        if chunks_col is None:
            logger.warning("Chunks collection not available")
            return
        
        vectors = []
        
        for idx, chunk_text in enumerate(chunks):
            chunk_id = f"{doc_id}-chunk-{idx}"
            
            # Store to MongoDB
            chunk_doc = {
                "_id": chunk_id,
                "user_id": user_id,
                "doc_id": doc_id,
                "chunk_index": idx,
                "text": chunk_text,
                "meta": {},
                "created_at": datetime.utcnow(),
            }
            
            try:
                chunks_col.insert_one(chunk_doc)
            except Exception as e:
                logger.error(f"Failed to store chunk: {e}")
            
            # Prepare for vector embedding
            vectors.append({
                "id": chunk_id,
                "text": chunk_text,
                "metadata": {
                    "doc_id": doc_id,
                    "doc_title": doc_title,
                    "chunk_index": idx,
                }
            })
        
        # Embed all chunks
        if vectors:
            self.vector_store.upsert_vectors(
                user_id=user_id,
                vectors=vectors,
                vector_type="doc_chunk"
            )


# Singleton instance
_ingestion_service: Optional[IngestionService] = None


def get_ingestion_service() -> IngestionService:
    """Get singleton ingestion service instance"""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = IngestionService()
    return _ingestion_service

