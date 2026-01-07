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


def get_preferences_collection():
    """Get preferences collection"""
    from app.database import get_db
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["preferences"]
    return None


def get_projects_collection():
    """Get projects collection"""
    from app.database import get_db
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["projects"]
    return None


def get_tasks_collection():
    """Get tasks collection (unified, not just email)"""
    from app.database import get_db
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["tasks"]
    return None


def get_truth_ledger_collection():
    """Get truth_ledger collection"""
    from app.database import get_db
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["truth_ledger"]
    return None


def get_relationships_collection():
    """Get relationships collection"""
    from app.database import get_db
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["relationships"]
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
        
        # Preferences collection
        preferences = db.db["preferences"]
        preferences.create_index([("user_id", 1)], unique=True)
        preferences.create_index([("updated_at", -1)])
        
        # Projects collection
        projects = db.db["projects"]
        projects.create_index([("user_id", 1), ("status", 1)])
        projects.create_index([("user_id", 1), ("updated_at", -1)])
        projects.create_index([("user_id", 1), ("name", 1)])
        
        # Tasks collection
        tasks = db.db["tasks"]
        tasks.create_index([("user_id", 1), ("status", 1)])
        tasks.create_index([("user_id", 1), ("due_date", 1)])
        tasks.create_index([("user_id", 1), ("priority", 1)])
        tasks.create_index([("user_id", 1), ("created_at", -1)])
        tasks.create_index([("source", 1), ("source_ref", 1)])
        
        # Truth ledger collection
        truth_ledger = db.db["truth_ledger"]
        truth_ledger.create_index([("user_id", 1), ("fact_id", 1)])
        truth_ledger.create_index([("user_id", 1), ("changed_at", -1)])
        truth_ledger.create_index([("reason", 1)])
        
        # Relationships collection
        relationships = db.db["relationships"]
        relationships.create_index([("user_id", 1), ("contact_email", 1)], unique=True)
        relationships.create_index([("user_id", 1), ("importance", 1)])
        relationships.create_index([("user_id", 1), ("last_contact", -1)])
        relationships.create_index([("relationship_type", 1)])
        
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
    "source_ref": Optional[str],  # Reference to source message/doc (evidenceRef)
    "vector_id": Optional[str],  # Pinecone vector ID (for tracking)
    "valid_from": Optional[datetime],  # When fact became true
    "valid_to": Optional[datetime],  # When fact became false (null if still valid)
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

PREFERENCES_SCHEMA = {
    "_id": str,  # preference_id
    "user_id": str,
    "memory_namespace": str,  # Canonical Pinecone namespace
    "primary_email": Optional[str],
    "workspace_id": Optional[str],
    "timezone": Optional[str],
    "language": Optional[str],
    "notification_settings": Optional[Dict[str, Any]],
    "ai_personality": Optional[Dict[str, Any]],
    "created_at": datetime,
    "updated_at": datetime,
}

PROJECT_SCHEMA = {
    "_id": str,  # project_id
    "user_id": str,
    "name": str,
    "description": Optional[str],
    "status": str,  # "active", "archived", "completed"
    "related_contacts": List[str],
    "related_threads": List[str],
    "summary": Optional[str],
    "key_facts": List[str],
    "created_at": datetime,
    "updated_at": datetime,
    "last_activity": datetime,
}

TASK_SCHEMA = {
    "_id": str,  # task_id
    "user_id": str,
    "title": str,
    "description": Optional[str],
    "status": str,  # "pending", "in_progress", "completed", "cancelled"
    "priority": str,  # "low", "medium", "high", "urgent"
    "source": str,  # "email", "chat", "calendar", "manual"
    "source_ref": Optional[str],  # thread_id, message_id, etc.
    "due_date": Optional[datetime],
    "completed_at": Optional[datetime],
    "created_at": datetime,
    "updated_at": datetime,
}

TRUTH_LEDGER_SCHEMA = {
    "_id": str,  # ledger_id
    "user_id": str,
    "fact_id": str,  # Links to memory_facts._id
    "version": int,
    "previous_value": str,
    "new_value": str,
    "reason": str,  # "contradiction", "update", "refinement"
    "confidence_change": float,
    "evidence_ref": Optional[str],
    "changed_at": datetime,
}

RELATIONSHIP_SCHEMA = {
    "_id": str,  # relationship_id
    "user_id": str,
    "contact_email": str,
    "importance": str,  # "high", "medium", "low"
    "relationship_type": str,  # "colleague", "friend", "family", "client"
    "last_contact": Optional[datetime],
    "contact_frequency": int,  # messages per month
    "notes": List[str],  # Important notes about this person
    "projects": List[str],  # Shared projects
    "created_at": datetime,
    "updated_at": datetime,
}

