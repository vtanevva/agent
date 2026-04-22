"""
MVP Task Data Models - Event → TaskCandidate → AivisTask pipeline

This module defines the three-stage task extraction and prioritization system:
1. Event: Raw input from sources (Gmail, Calendar, Slack, etc.)
2. TaskCandidate: LLM-extracted potential tasks with confidence
3. AivisTask: Final prioritized task with actions for the UI
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from .runtime_paths import get_db


class EventSource(str, Enum):
    """Source of events"""
    GMAIL = "gmail"
    CALENDAR = "calendar"
    SLACK = "slack"
    OUTLOOK = "outlook"
    MANUAL = "manual"


class ActionType(str, Enum):
    """Types of actions that can be taken on a task"""
    REPLY = "reply"
    FORWARD = "forward"
    SCHEDULE = "schedule"
    CALL = "call"
    REVIEW = "review"
    COMPLETE = "complete"
    DELEGATE = "delegate"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class TaskPriority(str, Enum):
    """Task priority levels for Aivis UI (MVP: 3 levels)"""
    NOW = "NOW"          # Score ≥ 6: Urgent, due soon, from VIP
    SOON = "SOON"        # Score 3-5: Important but not urgent
    LATER = "LATER"      # Score ≤ 2: No deadline or low priority


class StakeType(str, Enum):
    """What's at stake if the task isn't done"""
    RELATIONSHIP = "relationship"  # Important contact/relationship
    DEADLINE = "deadline"          # Hard deadline
    OPPORTUNITY = "opportunity"    # Business opportunity
    REPUTATION = "reputation"      # Professional reputation
    MONEY = "money"                # Financial impact
    ROUTINE = "routine"            # Regular maintenance
    NOTIFICATION = "notification"  # Notification to the user
    NEWSLETTER = "newsletter"  # Newsletter to the user
    INVOICE = "invoice"  # Invoice to the userSOCIAL
# MongoDB Collection Helpers

def get_events_collection():
    """Get events collection (raw inputs from sources)"""
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["events"]
    return None


def get_task_candidates_collection():
    """Get task_candidates collection (LLM outputs)"""
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["task_candidates"]
    return None


def get_aivis_tasks_collection():
    """Get aivis_tasks collection (prioritized user-facing tasks)"""
    db = get_db()
    if db.is_connected and db.db is not None:
        return db.db["aivis_tasks"]
    return None


# Schema Templates

EVENT_SCHEMA = {
    "_id": str,  # event_id (e.g., "gmail_123")
    "user_id": str,
    "source": str,  # EventSource
    "timestamp": datetime,  # When the event occurred
    "data": Dict[str, Any],  # Source-specific data
    "created_at": datetime,
  
}

TASK_CANDIDATE_SCHEMA = {
    "_id": str,  # candidate_id
    "user_id": str,
    "event_id": str,  # Links to events._id
    "title": str,
    "action_type": str,  # ActionType (reply, schedule, call, review, complete, delegate)
    "due_datetime": Optional[datetime],  # null if no deadline mentioned
    "extracted_at": datetime,
    "llm_model": str,  # Which model extracted this
    "raw_llm_output": Optional[Dict[str, Any]],  # For debugging
}

AIVIS_TASK_SCHEMA = {
    "_id": str,  # task_id (e.g., "aivis_1")
    "user_id": str,
    "priority": str,  # TaskPriority (NOW, SOON, LATER)
    "priority_score": int,  # Deterministic score (0-10+)
    "title": str,
    "reason": str,  # Human sentence explaining priority (e.g., "Due in 6h + from VIP + reply needed")
    "due_datetime": Optional[datetime],
    "source_event": str,  # event_id
    "task_candidate": str,  # candidate_id
    "actions": List[str],  # List of ActionType values
    "action_metadata": Dict[str, Any],  # Action-specific data (e.g., draft_reply text)
    "status": str,  # "pending", "in_progress", "completed", "cancelled"
    "created_at": datetime,
    "updated_at": datetime,
    "completed_at": Optional[datetime],
}


def ensure_task_pipeline_indexes():
    """Create indexes for task pipeline collections"""
    import logging
    
    logger = logging.getLogger(__name__)
    db = get_db()
    
    if not db.is_connected or db.db is None:
        logger.warning("Database not connected - skipping task pipeline index creation")
        return
    
    try:
        # Events collection
        events = db.db["events"]
        events.create_index([("user_id", 1), ("timestamp", -1)])
        events.create_index([("user_id", 1), ("source", 1), ("timestamp", -1)])
        events.create_index("source")
        
        # Task candidates collection
        candidates = db.db["task_candidates"]
        candidates.create_index([("user_id", 1), ("extracted_at", -1)])
        candidates.create_index([("user_id", 1), ("confidence", -1)])
        candidates.create_index("event_id")
        
        # Aivis tasks collection
        aivis_tasks = db.db["aivis_tasks"]
        aivis_tasks.create_index([("user_id", 1), ("priority", 1), ("created_at", -1)])
        aivis_tasks.create_index([("user_id", 1), ("status", 1)])
        aivis_tasks.create_index([("user_id", 1), ("due_datetime", 1)])
        aivis_tasks.create_index("source_event")
        aivis_tasks.create_index("task_candidate")
        
        logger.info("✅ Task pipeline indexes created successfully")
        
    except Exception as e:
        logger.warning(f"Failed to create task pipeline indexes (may already exist): {e}")


# Example document structures for reference

EXAMPLE_GMAIL_EVENT = {
    "_id": "gmail_msg_abc123",
    "user_id": "user_123",
    "source": "gmail",
    "timestamp": datetime(2026, 1, 28, 9, 12),
    "data": {
        "sender": "vanesa@company.com",
        "sender_name": "Vanesa Taneva",
        "subject": "Can we confirm tomorrow?",
        "snippet": "Hey, just wanted to confirm our meeting tomorrow at 2pm. Do you have the deck ready?",
        "thread_id": "t_123",
        "message_id": "msg_abc123",
        "labels": ["INBOX", "UNREAD"],
    },
    "created_at": datetime.utcnow(),
}

EXAMPLE_TASK_CANDIDATE = {
    "_id": "candidate_xyz789",
    "user_id": "user_123",
    "event_id": "gmail_msg_abc123",
    "title": "Confirm meeting with Vanesa",
    "action_type": "reply",
    "due_datetime": datetime(2026, 1, 29, 10, 0),  # Tomorrow morning
    "extracted_at": datetime.utcnow(),
    "llm_model": "gpt-4o-mini",
    "raw_llm_output": {
        "tasks": [
            {
                "title": "Confirm meeting with Vanesa",
                "action_type": "reply",
                "due_datetime": "2026-01-29T10:00:00"
            }
        ]
    },
}

EXAMPLE_AIVIS_TASK = {
    "_id": "aivis_1",
    "user_id": "user_123",
    "priority": "NOW",
    "priority_score": 9,  # 4 (due <24h) + 3 (VIP) + 2 (reply needed) = 9
    "title": "Confirm meeting with Vanesa",
    "reason": "Due in 18h + from Vanesa Taneva (VIP) + reply needed",
    "due_datetime": datetime(2026, 1, 29, 10, 0),
    "source_event": "gmail_msg_abc123",
    "task_candidate": "candidate_xyz789",
    "actions": ["draft_reply", "schedule", "open_in_gmail"],
    "action_metadata": {
        "draft_reply": {
            "to": "vanesa@company.com",
            "thread_id": "t_123",
            "suggested_response": "Hi Vanesa, yes confirmed for tomorrow at 2pm. The deck is ready, I'll bring it along.",
        },
        "schedule": {
            "event_time": datetime(2026, 1, 29, 14, 0),
            "duration_minutes": 60,
        },
        "open_in_gmail": {
            "thread_id": "t_123",
            "url": "https://mail.google.com/mail/u/0/#inbox/t_123",
        },
    },
    "status": "pending",
    "created_at": datetime.utcnow(),
    "updated_at": datetime.utcnow(),
    "completed_at": None,
}
