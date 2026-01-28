"""
Task Pipeline Service - Event → TaskCandidate → AivisTask

This service implements the MVP task extraction and prioritization pipeline:
1. Process events into task candidates (LLM extraction)
2. Prioritize task candidates into Aivis tasks (with context)
3. Generate action metadata for each task
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from uuid import uuid4

from app.memory.task_models import (
    get_events_collection,
    get_task_candidates_collection,
    get_aivis_tasks_collection,
    EventSource,
    ActionType,
    TaskPriority,
    StakeType,
)
from app.services.llm_service import get_llm_service
from app.memory.models import get_relationships_collection
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


class TaskPipelineService:
    """Handles the full task pipeline from events to prioritized tasks"""
    
    def __init__(self):
        self.llm = get_llm_service()
    
    def process_gmail_event(self, user_id: str, email_data: Dict[str, Any]) -> Optional[str]:
        """
        Process a Gmail email into an Event, extract TaskCandidate(s), and create AivisTask(s)
        
        Args:
            user_id: User ID
            email_data: Dict with keys: message_id, thread_id, sender, subject, snippet, body, timestamp
        
        Returns:
            task_id of the created AivisTask, or None if no task was created
        """
        # Step 1: Create Event
        event_id = self._create_event(
            user_id=user_id,
            source=EventSource.GMAIL,
            timestamp=email_data.get("timestamp", datetime.utcnow()),
            data={
                "sender": email_data.get("sender", ""),
                "sender_name": email_data.get("sender_name", ""),
                "subject": email_data.get("subject", ""),
                "snippet": email_data.get("snippet", ""),
                "body": email_data.get("body", ""),
                "thread_id": email_data.get("thread_id", ""),
                "message_id": email_data.get("message_id", ""),
                "labels": email_data.get("labels", []),
            }
        )
        
        if not event_id:
            logger.error("Failed to create event")
            return None
        
        # Step 2: Extract TaskCandidate(s)
        candidates = self._extract_task_candidates(user_id, event_id, email_data)
        
        if not candidates:
            logger.info(f"No task candidates extracted from event {event_id}")
            return None
        
        # Step 3: Create AivisTask(s) from candidates
        task_ids = []
        for candidate in candidates:
            task_id = self._create_aivis_task(user_id, candidate, email_data)
            if task_id:
                task_ids.append(task_id)
        
        # Return the first task ID (most important one)
        return task_ids[0] if task_ids else None
    
    def _create_event(self, user_id: str, source: str, timestamp: datetime, data: Dict[str, Any]) -> Optional[str]:
        """Create an Event document in MongoDB"""
        events_col = get_events_collection()
        if not events_col:
            logger.error("Events collection not available")
            return None
        
        # Generate event ID based on source
        if source == EventSource.GMAIL:
            event_id = f"gmail_{data.get('message_id', uuid4())}"
        else:
            event_id = f"{source}_{uuid4()}"
        
        # Check if event already exists (avoid duplicates)
        existing = events_col.find_one({"_id": event_id})
        if existing:
            logger.info(f"Event {event_id} already exists")
            return event_id
        
        event = {
            "_id": event_id,
            "user_id": user_id,
            "source": source,
            "timestamp": timestamp,
            "data": data,
            "created_at": datetime.utcnow(),
        }
        
        try:
            events_col.insert_one(event)
            logger.info(f"Created event {event_id}")
            return event_id
        except Exception as e:
            logger.error(f"Failed to create event: {e}", exc_info=True)
            return None
    
    def _extract_task_candidates(self, user_id: str, event_id: str, email_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Use LLM to extract TaskCandidate(s) from an email event
        
        Returns list of candidate dicts with: title, action_type, due_datetime, stake, confidence
        """
        subject = email_data.get("subject", "(No subject)")
        sender = email_data.get("sender", "")
        sender_name = email_data.get("sender_name", sender)
        body = email_data.get("body", email_data.get("snippet", ""))
        timestamp = email_data.get("timestamp", datetime.utcnow())
        
        if not body:
            return []
        
        # LLM prompt for task extraction
        prompt = f"""Extract actionable tasks from this email for the recipient.

Rules:
- Only extract concrete, specific actions that the recipient must take
- Do NOT create generic tasks like "Read this email" or "Handle this thread"
- Each task must have a clear action verb (reply, schedule, prepare, send, etc.)
- Estimate due date/time based on email content (e.g., "tomorrow" = next day)
- Assess what's at stake: relationship, deadline, opportunity, reputation, money, or routine
- Provide confidence score 0.0-1.0 based on how clear the task is
- Return at most 3 tasks

Email details:
From: {sender_name} <{sender}>
Subject: {subject}
Date: {timestamp.strftime("%Y-%m-%d %H:%M")}

Body:
{body[:3000]}

Return STRICT JSON:
{{
  "tasks": [
    {{
      "title": "Short task description (max 12 words)",
      "action_type": "reply|schedule|call|review|complete|delegate",
      "due_datetime": "YYYY-MM-DDTHH:MM:SS or null",
      "stake": "relationship|deadline|opportunity|reputation|money|routine",
      "confidence": 0.0-1.0,
      "reasoning": "Why this is a task"
    }}
  ]
}}

If no tasks, return {{"tasks": []}}"""
        
        try:
            response = self.llm.chat_completion_text(
                messages=[
                    {"role": "system", "content": "You are a task extraction expert. Extract only clear, actionable tasks. Return strict JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=800,
            )
            
            # Parse JSON response
            parsed = self._parse_llm_json(response)
            if not parsed or "tasks" not in parsed:
                return []
            
            # Store candidates in DB and return
            candidates = []
            for task_data in parsed.get("tasks", [])[:3]:  # Max 3 tasks
                candidate = self._store_task_candidate(
                    user_id=user_id,
                    event_id=event_id,
                    task_data=task_data,
                    raw_output=parsed,
                )
                if candidate:
                    candidates.append(candidate)
            
            return candidates
            
        except Exception as e:
            logger.error(f"Task extraction failed: {e}", exc_info=True)
            return []
    
    def _store_task_candidate(self, user_id: str, event_id: str, task_data: Dict[str, Any], raw_output: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Store a TaskCandidate in MongoDB"""
        candidates_col = get_task_candidates_collection()
        if not candidates_col:
            return None
        
        candidate_id = f"candidate_{uuid4()}"
        
        # Parse due_datetime
        due_datetime = None
        due_str = task_data.get("due_datetime")
        if due_str and due_str != "null":
            try:
                due_datetime = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
            except Exception:
                logger.warning(f"Failed to parse due_datetime: {due_str}")
        
        candidate = {
            "_id": candidate_id,
            "user_id": user_id,
            "event_id": event_id,
            "title": task_data.get("title", "")[:200],
            "action_type": task_data.get("action_type", "review"),
            "due_datetime": due_datetime,
            "stake": task_data.get("stake", "routine"),
            "confidence": float(task_data.get("confidence", 0.6)),
            "extracted_at": datetime.utcnow(),
            "llm_model": self.llm.default_model,
            "raw_llm_output": raw_output,
        }
        
        try:
            candidates_col.insert_one(candidate)
            logger.info(f"Created task candidate: {candidate['title'][:50]}")
            return candidate
        except Exception as e:
            logger.error(f"Failed to store task candidate: {e}", exc_info=True)
            return None
    
    def _create_aivis_task(self, user_id: str, candidate: Dict[str, Any], email_data: Dict[str, Any]) -> Optional[str]:
        """
        Create an AivisTask from a TaskCandidate with priority and actions
        """
        tasks_col = get_aivis_tasks_collection()
        if not tasks_col:
            return None
        
        task_id = f"aivis_{uuid4().hex[:8]}"
        
        # Calculate priority
        priority, reason = self._calculate_priority(user_id, candidate, email_data)
        
        # Generate actions
        actions, action_metadata = self._generate_actions(candidate, email_data)
        
        task = {
            "_id": task_id,
            "user_id": user_id,
            "priority": priority,
            "title": candidate["title"],
            "reason": reason,
            "due_datetime": candidate.get("due_datetime"),
            "source_event": candidate["event_id"],
            "task_candidate": candidate["_id"],
            "actions": actions,
            "action_metadata": action_metadata,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "completed_at": None,
        }
        
        try:
            tasks_col.insert_one(task)
            logger.info(f"✅ Created AivisTask [{priority}]: {task['title'][:50]}")
            return task_id
        except Exception as e:
            logger.error(f"Failed to create AivisTask: {e}", exc_info=True)
            return None
    
    def _calculate_priority(self, user_id: str, candidate: Dict[str, Any], email_data: Dict[str, Any]) -> tuple[str, str]:
        """
        Calculate task priority (NOW, TODAY, THIS_WEEK, LATER, SOMEDAY) with reasoning
        
        Priority rules:
        - NOW: Due within 24h + from VIP, OR high confidence + relationship stake
        - TODAY: Due today, OR high confidence + deadline stake
        - THIS_WEEK: Due this week
        - LATER: Due after this week
        - SOMEDAY: No deadline
        """
        due = candidate.get("due_datetime")
        confidence = candidate.get("confidence", 0.0)
        stake = candidate.get("stake", "routine")
        sender = email_data.get("sender", "")
        
        # Check if sender is VIP
        is_vip = self._is_vip_contact(user_id, sender)
        
        now = datetime.utcnow()
        reasons = []
        
        # Due date urgency
        if due:
            hours_until_due = (due - now).total_seconds() / 3600
            
            if hours_until_due < 24:
                reasons.append("due within 24h")
                if is_vip or stake in ["relationship", "deadline"]:
                    return TaskPriority.NOW, f"Due within 24h + {stake} stake" + (" + VIP sender" if is_vip else "")
                else:
                    return TaskPriority.TODAY, "Due within 24h"
            
            elif hours_until_due < 24 * 7:
                days = int(hours_until_due / 24)
                return TaskPriority.THIS_WEEK, f"Due in {days} days"
            
            else:
                return TaskPriority.LATER, "Due after this week"
        
        # No due date - assess by confidence and stake
        if confidence >= 0.8 and stake == "relationship" and is_vip:
            return TaskPriority.NOW, f"High confidence + relationship stake + VIP ({sender})"
        
        if confidence >= 0.7 and stake in ["relationship", "deadline", "opportunity"]:
            return TaskPriority.TODAY, f"High confidence + {stake} stake"
        
        if confidence >= 0.6:
            return TaskPriority.THIS_WEEK, "Medium confidence"
        
        return TaskPriority.SOMEDAY, "Low confidence or routine"
    
    def _is_vip_contact(self, user_id: str, email: str) -> bool:
        """Check if a contact is marked as VIP (high importance)"""
        relationships_col = get_relationships_collection()
        if not relationships_col:
            return False
        
        try:
            relationship = relationships_col.find_one({
                "user_id": user_id,
                "contact_email": email,
                "importance": "high"
            })
            return relationship is not None
        except Exception:
            return False
    
    def _generate_actions(self, candidate: Dict[str, Any], email_data: Dict[str, Any]) -> tuple[List[str], Dict[str, Any]]:
        """
        Generate available actions for a task based on action_type
        
        Returns: (actions_list, action_metadata_dict)
        """
        action_type = candidate.get("action_type", "review")
        thread_id = email_data.get("thread_id", "")
        sender = email_data.get("sender", "")
        
        actions = []
        metadata = {}
        
        # Always include "open in source"
        if thread_id:
            actions.append("open_in_gmail")
            metadata["open_in_gmail"] = {
                "thread_id": thread_id,
                "url": f"https://mail.google.com/mail/u/0/#inbox/{thread_id}",
            }
        
        # Action-specific actions
        if action_type == "reply":
            actions.insert(0, "draft_reply")
            metadata["draft_reply"] = {
                "to": sender,
                "thread_id": thread_id,
                "suggested_response": "Reply will be drafted in your style"
            }
        
        elif action_type == "schedule":
            actions.insert(0, "schedule")
            metadata["schedule"] = {
                "event_time": candidate.get("due_datetime"),
                "duration_minutes": 60,
            }
        
        elif action_type == "call":
            actions.insert(0, "call")
            metadata["call"] = {
                "contact": sender,
            }
        
        # Always add "mark as done"
        actions.append("mark_done")
        
        return actions, metadata
    
    def _parse_llm_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Best-effort JSON parsing from LLM response"""
        if not text:
            return None
        
        text = text.strip()
        
        # Try direct parse
        try:
            return json.loads(text)
        except Exception:
            pass
        
        # Try to extract JSON from markdown code block
        import re
        match = re.search(r"```(?:json)?\s*(\{[\s\S]*?```)", text)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        
        # Try to find first JSON object
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        
        return None
    
    def get_tasks_by_priority(self, user_id: str, priority: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get AivisTasks for a user, optionally filtered by priority
        
        Returns tasks sorted by priority order (NOW first, then TODAY, etc.)
        """
        tasks_col = get_aivis_tasks_collection()
        if not tasks_col:
            return []
        
        query = {
            "user_id": user_id,
            "status": "pending"  # Only active tasks
        }
        
        if priority:
            query["priority"] = priority
        
        try:
            # Define priority order
            priority_order = ["NOW", "TODAY", "THIS_WEEK", "LATER", "SOMEDAY"]
            
            tasks = list(tasks_col.find(query).limit(limit))
            
            # Sort by priority order
            tasks.sort(key=lambda t: (
                priority_order.index(t.get("priority", "SOMEDAY")),
                t.get("created_at", datetime.min)
            ))
            
            return tasks
            
        except Exception as e:
            logger.error(f"Failed to fetch tasks: {e}", exc_info=True)
            return []
    
    def mark_task_done(self, user_id: str, task_id: str) -> bool:
        """Mark an AivisTask as completed"""
        tasks_col = get_aivis_tasks_collection()
        if not tasks_col:
            return False
        
        try:
            result = tasks_col.update_one(
                {"_id": task_id, "user_id": user_id},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to mark task done: {e}", exc_info=True)
            return False


# Singleton instance
_task_pipeline_service = None

def get_task_pipeline_service() -> TaskPipelineService:
    """Get the global TaskPipelineService instance"""
    global _task_pipeline_service
    if _task_pipeline_service is None:
        _task_pipeline_service = TaskPipelineService()
    return _task_pipeline_service
