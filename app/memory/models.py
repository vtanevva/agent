"""
Data models for User Awareness Memory System

MongoDB Collections:
- users: User profiles
- messages: All messages (chat, email, etc.)
- memory_facts: Curated facts about users
- thread_summaries: Rolling summaries of conversation threads
- documents: Uploaded documents metadata
- document_chunks: Text chunks from documents for RAG
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


class MessageDirection(str, Enum):
    """Direction of message flow"""
    INCOMING = "in"
    OUTGOING = "out"


class FactType(str, Enum):
    """Types of memory facts"""
    PREFERENCE = "preference"  # User likes/dislikes
    IDENTITY = "identity"      # Personal info (name, job, etc.)
    WORK = "work"             # Work-related info
    RELATIONSHIP = "relationship"  # Info about connections
    OTHER = "other"           # General facts


class DocumentSource(str, Enum):
    """Source of uploaded documents"""
    UPLOAD = "upload"
    DRIVE = "drive"
    NOTION = "notion"
    EMAIL = "email"


class DocumentPermission(str, Enum):
    """Document access permissions"""
    PRIVATE = "private"
    SHARED = "shared"


# MongoDB collection helpers
def get_users_collection():
    """Get users collection"""
    from app.database import get_db
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["users"]
    return None


def get_messages_collection():
    """Get messages collection"""
    from app.database import get_db
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["messages"]
    return None


def get_memory_facts_collection():
    """Get memory_facts collection"""
    from app.database import get_db
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["memory_facts"]
    return None


def get_thread_summaries_collection():
    """Get thread_summaries collection"""
    from app.database import get_db
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["thread_summaries"]
    return None


def get_documents_collection():
    """Get documents collection"""
    from app.database import get_db
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["documents"]
    return None


def get_document_chunks_collection():
    """Get document_chunks collection"""
    from app.database import get_db
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["document_chunks"]
    return None


def ensure_indexes():
    """Create indexes for all memory collections"""
    from app.database import get_db
    import logging
    
    logger = logging.getLogger(__name__)
    db = get_db()
    
    if not db.is_connected or db.db is None:
        logger.warning("Database not connected - skipping index creation")
        return
    
    try:
        # Users collection
        users = db.db["users"]
        users.create_index("created_at")
        
        # Messages collection - critical indexes
        messages = db.db["messages"]
        messages.create_index([("user_id", 1), ("ts", -1)])
        messages.create_index([("user_id", 1), ("thread_id", 1), ("ts", -1)])
        messages.create_index("thread_id")
        messages.create_index("channel")
        
        # Memory facts collection
        facts = db.db["memory_facts"]
        facts.create_index([("user_id", 1), ("is_active", 1), ("type", 1)])
        facts.create_index([("user_id", 1), ("updated_at", -1)])
        facts.create_index("confidence")
        
        # Thread summaries collection
        summaries = db.db["thread_summaries"]
        summaries.create_index([("user_id", 1), ("thread_id", 1)], unique=True)
        summaries.create_index([("user_id", 1), ("updated_at", -1)])
        
        # Documents collection
        documents = db.db["documents"]
        documents.create_index([("user_id", 1), ("created_at", -1)])
        documents.create_index("source")
        
        # Document chunks collection
        chunks = db.db["document_chunks"]
        chunks.create_index([("user_id", 1), ("doc_id", 1), ("chunk_index", 1)])
        chunks.create_index("doc_id")
        
        logger.info("✅ Memory system indexes created successfully")
        
    except Exception as e:
        logger.warning(f"Failed to create memory indexes (may already exist): {e}")


# Schema templates for validation
USER_SCHEMA = {
    "_id": str,  # user_id
    "name": Optional[str],
    "email": Optional[str],
    "created_at": datetime,
    "updated_at": datetime,
    "meta": Optional[Dict[str, Any]],
}

MESSAGE_SCHEMA = {
    "_id": str,  # message_id
    "user_id": str,
    "thread_id": str,
    "channel": str,  # "whatsapp", "email", "web_chat", etc.
    "direction": str,  # MessageDirection
    "text": str,
    "ts": datetime,
    "source_id": Optional[str],  # Original message ID from source system
    "meta": Optional[Dict[str, Any]],
}

MEMORY_FACT_SCHEMA = {
    "_id": str,  # fact_id
    "user_id": str,
    "text": str,
    "type": str,  # FactType
    "confidence": float,  # 0.0 to 1.0
    "source_ref": Optional[str],  # Reference to source message/doc
    "created_at": datetime,
    "updated_at": datetime,
    "is_active": bool,
}

THREAD_SUMMARY_SCHEMA = {
    "_id": str,  # summary_id
    "user_id": str,
    "thread_id": str,
    "summary_text": str,
    "updated_at": datetime,
    "window_start_ts": datetime,
    "window_end_ts": datetime,
    "message_count": int,
}

DOCUMENT_SCHEMA = {
    "_id": str,  # doc_id
    "user_id": str,
    "title": str,
    "source": str,  # DocumentSource
    "created_at": datetime,
    "permissions": str,  # DocumentPermission
    "file_size": Optional[int],
    "mime_type": Optional[str],
    "meta": Optional[Dict[str, Any]],
}

DOCUMENT_CHUNK_SCHEMA = {
    "_id": str,  # chunk_id
    "user_id": str,
    "doc_id": str,
    "chunk_index": int,
    "text": str,
    "meta": Optional[Dict[str, Any]],  # page, section, etc.
    "created_at": datetime,
}

