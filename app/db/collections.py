"""Shared database utilities for accessing MongoDB collections"""

import os
from typing import Optional
from pymongo.collection import Collection
from app.database import get_db

def get_tokens_collection() -> Optional[Collection]:
    """Get the tokens collection from the database manager"""
    db_manager = get_db()
    if db_manager.is_connected and db_manager.tokens is not None:
        return db_manager.tokens
    return None

def get_conversations_collection() -> Optional[Collection]:
    """Get the conversations collection from the database manager"""
    db_manager = get_db()
    if db_manager.is_connected and db_manager.conversations is not None:
        return db_manager.conversations
    return None

def get_calendar_events_collection() -> Optional[Collection]:
    """Get the calendar_events collection from the database manager"""
    db_manager = get_db()
    if db_manager.is_connected and db_manager.db is not None:
        return db_manager.db["calendar_events"]
    return None

def get_contacts_collection() -> Optional[Collection]:
    """Get the contacts collection"""
    db_manager = get_db()
    if db_manager.is_connected and db_manager.db is not None:
        return db_manager.db["contacts"]
    return None

def get_waitlist_collection() -> Optional[Collection]:
    """Get the waitlist collection"""
    db_manager = get_db()
    if db_manager.is_connected and db_manager.db is not None:
        return db_manager.db["waitlist"]
    return None


def get_email_todos_collection() -> Optional[Collection]:
    """Get the email_todos collection (extracted todo items from emails)."""
    db_manager = get_db()
    if db_manager.is_connected and db_manager.db is not None:
        return db_manager.db["email_todos"]
    return None


def get_gmail_watch_state_collection() -> Optional[Collection]:
    """
    Get the gmail_watch_state collection (historyId baselines for Pub/Sub watch).

    IMPORTANT:
    We scope watch baselines by environment to prevent dev/prod (or multiple deployments)
    from racing on the same `last_history_id` when they share a MongoDB.
    """
    db_manager = get_db()
    if db_manager.is_connected and db_manager.db is not None:
        env = (os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "development").strip().lower()
        # Normalize a few common values
        if env in ("prod",):
            env = "production"
        if env in ("dev",):
            env = "development"
        safe_env = "".join(ch for ch in env if ch.isalnum() or ch in ("_", "-")) or "development"
        return db_manager.db[f"gmail_watch_state__{safe_env}"]
    return None

