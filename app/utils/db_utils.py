"""Shared database utilities for accessing MongoDB collections"""

from typing import Optional
from pymongo.collection import Collection
from app.database import get_db

def get_tokens_collection() -> Optional[Collection]:
    """Get the tokens collection from the database manager"""
    db_manager = get_db()
    if db_manager.is_connected:
        return db_manager.tokens
    return None

def get_conversations_collection() -> Optional[Collection]:
    """Get the conversations collection from the database manager"""
    db_manager = get_db()
    if db_manager.is_connected:
        return db_manager.conversations
    return None

def get_calendar_events_collection() -> Optional[Collection]:
    """Get the calendar_events collection from the database manager"""
    db_manager = get_db()
    if db_manager.is_connected:
        return db_manager.db["calendar_events"]
    return None

