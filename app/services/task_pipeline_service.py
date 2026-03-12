"""
Task Pipeline Service - Event → TaskCandidate → AivisTask

This service implements the MVP task extraction and prioritization pipeline:
1. Process events into task candidates (LLM extraction)
2. Prioritize task candidates into Aivis tasks (with context)
3. Generate action metadata for each task
"""

import json
from datetime import datetime, timedelta, timezone
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
    """
    Handles the full task pipeline from events to prioritized tasks
    
    MVP Pipeline:
    1. Ingest: Pull unread emails + calendar events
    2. Extract: LLM extracts tasks (structured JSON only)
    3. Score: Deterministic priority scoring
    """
    
    def __init__(self):
        self.llm = get_llm_service()
    
    def ingest_and_process(self, user_id: str, max_emails: int = 20) -> Dict[str, Any]:
        """
        DEPRECATED (replaced by worker-based pipeline).

        Use `app.services.email_processing_pipeline.enqueue_login_email_pipeline()` instead.
        This avoids deleting `body_temp` too early and allows parallel workers
        (facts, relationships, tasks, linking).
        """
        try:
            from app.services.email_processing_pipeline import enqueue_login_email_pipeline

            job_id = enqueue_login_email_pipeline(user_id=user_id, max_emails=max_emails, provider="gmail")
            return {"success": True, "job_id": job_id}
        except Exception as e:
            logger.error(f"Failed to enqueue email processing: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # NOTE: bootstrap fast-path removed in favor of worker-based pipeline.
    
    def _extract_name(self, email_str: str) -> str:
        """Extract name from 'John Doe <john@example.com>' format"""
        if not email_str:
            return ""
        if '<' in email_str:
            return email_str.split('<')[0].strip()
        return email_str.strip()

    def _display_name_from_sender(self, sender_name: str, sender_email: str) -> str:
        """
        Best-effort display name for meeting titles.
        Prefers a real display name; falls back to the email username.
        """
        name = self._extract_name(sender_name or "").strip()
        if name and "@" not in name:
            return name
        raw = (sender_email or sender_name or "").strip()
        if "<" in raw and ">" in raw:
            # "Name <user@example.com>"
            inner = raw.split("<", 1)[1].split(">", 1)[0].strip()
            raw = inner or raw
        if "@" in raw:
            return raw.split("@", 1)[0].strip()
        return (name or raw).strip()
    
    def _empty_result(self, error: str = "") -> Dict[str, Any]:
        """Return empty result structure"""
        return {
            "success": False,
            "error": error,
            "emails_processed": 0,
            "calendar_events": 0,
            "tasks_created": 0,
            "task_ids": []
        }
    
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
        if events_col is None:
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
        
        # LLM prompt for task extraction (MVP: structured extraction only, no reasoning)
        prompt = f"""Extract actionable tasks from this email. Output JSON only.

RULES:
• If no clear action → ignore
• If no implied deadline → mark due_datetime = null
• Only concrete tasks (reply, schedule, call, etc.)
• Max 3 tasks
• IMPORTANT TITLE RULES:
  - Do NOT include dates/times in "title" (no "tomorrow at 8:30", no weekdays).
  - If this is a meeting/scheduling/call request, set title EXACTLY to: "Meeting with {sender_name}"
  - If you can infer a topic, include it as a separate field "topic" (max 6 words). Otherwise null.

Email:
From: {sender_name} <{sender}>
Subject: {subject}
Date: {timestamp.strftime("%Y-%m-%d %H:%M")}

{body[:3000]}

OUTPUT (strict JSON):
{{
  "tasks": [
    {{
      "title": "task description (max 12 words, no dates/times)",
      "action_type": "reply|schedule|call|review|complete|delegate",
      "due_datetime": "YYYY-MM-DDTHH:MM:SS or null",
      "topic": "string or null"
    }}
  ]
}}

If no clear action, return {{"tasks": []}}"""
        
        try:
            response = self.llm.chat_completion_text(
                messages=[
                    {"role": "system", "content": "You extract tasks from emails. Return only JSON, no explanation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,  # Deterministic
                max_tokens=500,
            )
            
            # Parse JSON response
            parsed = self._parse_llm_json(response)
            if not parsed or "tasks" not in parsed:
                return []

            # Log every extracted task (debuggable, no email body logged)
            extracted_tasks = parsed.get("tasks", []) or []
            logger.info(
                f"🧠 Extracted {min(len(extracted_tasks), 3)} task(s) from event {event_id} "
                f"(subject: {subject[:80]!r})"
            )
            for i, task_data in enumerate(extracted_tasks[:3], start=1):
                try:
                    logger.info(
                        f"  [{i}] title={str(task_data.get('title', '')).strip()[:120]!r} "
                        f"action_type={task_data.get('action_type')!r} "
                        f"due_datetime={task_data.get('due_datetime')!r}"
                    )
                except Exception:
                    # Never fail extraction because of logging issues
                    pass
            
            # Store candidates in DB and return
            candidates = []
            for task_data in parsed.get("tasks", [])[:3]:  # Max 3 tasks
                candidate = self._store_task_candidate(
                    user_id=user_id,
                    event_id=event_id,
                    task_data=task_data,
                    raw_output=parsed,
                    email_data=email_data,
                )
                if candidate:
                    candidates.append(candidate)
            
            return candidates
            
        except Exception as e:
            logger.error(f"Task extraction failed: {e}", exc_info=True)
            return []
    
    def _store_task_candidate(
        self,
        user_id: str,
        event_id: str,
        task_data: Dict[str, Any],
        raw_output: Dict[str, Any],
        email_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Store a TaskCandidate in MongoDB"""
        candidates_col = get_task_candidates_collection()
        if candidates_col is None:
            return None
        
        candidate_id = f"candidate_{uuid4()}"
        
        # Parse due_datetime (LLM-provided) with a safety fallback:
        # If the extracted due date lands *before* the email timestamp but the title implies
        # a forward-looking relative day ("this Friday", "tomorrow", etc.), re-parse from title.
        due_datetime = None
        due_str = task_data.get("due_datetime")
        if due_str and due_str != "null":
            try:
                due_datetime = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
            except Exception:
                logger.warning(f"Failed to parse due_datetime: {due_str}")

        # Fallback parse from title if the LLM date seems obviously wrong.
        try:
            title = str(task_data.get("title") or "")
            title_lower = title.lower()
            timestamp = (email_data or {}).get("timestamp", datetime.utcnow())
            has_relative_day = any(
                k in title_lower
                for k in (
                    "tomorrow",
                    "today",
                    "next ",
                    "this ",
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday",
                    "sunday",
                )
            )
            if due_datetime and has_relative_day:
                # Compare in naive space to avoid tz gotchas; we only care about “before email”.
                due_cmp = due_datetime.replace(tzinfo=None) if isinstance(due_datetime, datetime) else None
                ts_cmp = timestamp.replace(tzinfo=None) if isinstance(timestamp, datetime) else None
                if due_cmp and ts_cmp and due_cmp < (ts_cmp - timedelta(hours=1)):
                    from app.tools.calendar.detect_requests import parse_datetime_from_text

                    parsed_start, _parsed_end = parse_datetime_from_text(title, reference_dt=ts_cmp)
                    if parsed_start:
                        # Preserve tz-awareness if parse returns aware.
                        due_datetime = parsed_start
        except Exception:
            # Never fail candidate creation due to fallback parsing.
            pass
        
        # FILTER: Skip tasks that are overdue by more than X days.
        # (We do NOT skip based on email timestamp; we skip based on task due date.)
        OVERDUE_CUTOFF_DAYS = 2
        if due_datetime:
            now_utc = datetime.now(timezone.utc)
            # Normalize due_datetime to aware UTC for safe comparisons
            if due_datetime.tzinfo is None:
                due_utc = due_datetime.replace(tzinfo=timezone.utc)
            else:
                due_utc = due_datetime.astimezone(timezone.utc)

            if due_utc < (now_utc - timedelta(days=OVERDUE_CUTOFF_DAYS)):
                logger.info(
                    f"⏭️  Skipping overdue task (> {OVERDUE_CUTOFF_DAYS}d): "
                    f"'{task_data.get('title', '')}' (was due {due_utc.strftime('%Y-%m-%d')})"
                )
                return None
        
        # Prefer stable, user-friendly titles for meeting-like tasks.
        # For meetings coming from email, we standardize to: "Meeting with <sender>".
        title = str(task_data.get("title", "")).strip()
        action_type = str(task_data.get("action_type", "review") or "review")
        subject = str((email_data or {}).get("subject") or "").strip()

        import re

        def _looks_generic_meeting_phrase(text: str) -> bool:
            s = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
            s = re.sub(r"\s+", " ", s).strip()
            if not s:
                return True

            tokens = [t for t in s.split(" ") if t]
            if not tokens:
                return True

            date_time_words = {
                "today",
                "tomorrow",
                "next",
                "this",
                "at",
                "on",
                "in",
                "am",
                "pm",
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
                "jan",
                "january",
                "feb",
                "february",
                "mar",
                "march",
                "apr",
                "april",
                "may",
                "jun",
                "june",
                "jul",
                "july",
                "aug",
                "august",
                "sep",
                "sept",
                "september",
                "oct",
                "october",
                "nov",
                "november",
                "dec",
                "december",
            }

            core = [t for t in tokens if t not in date_time_words and not t.isdigit()]
            if not core:
                core = tokens
            core_s = " ".join(core)

            generic_set = {
                "lets meet",
                "let us meet",
                "let s meet",
                "meet",
                "meeting",
                "quick meeting",
                "call",
                "quick call",
                "chat",
                "quick chat",
                "catch up",
                "sync",
                "sync up",
            }
            if core_s in generic_set or core_s.startswith("lets meet") or core_s.startswith("meet "):
                return True

            verbs = {"meet", "meeting", "call", "chat", "sync"}
            verbish = [t for t in core if t in verbs]
            nonverb = [t for t in core if t not in verbs]
            return bool(verbish) and len(nonverb) <= 1

        # Prefer email subject over LLM title when available (more stable wording).
        cleaned_subject = re.sub(r"^\s*(re|fwd)\s*:\s*", "", subject, flags=re.IGNORECASE).strip()
        if cleaned_subject:
            title = cleaned_subject

        # Standardize meeting-ish titles to "Meeting with <sender>".
        # Apply regardless of action_type because the LLM may label meeting tasks as "call" or "schedule".
        if _looks_generic_meeting_phrase(cleaned_subject or title):
            sender_name_raw = str((email_data or {}).get("sender_name") or "")
            sender_raw = str((email_data or {}).get("sender") or "")
            who = self._display_name_from_sender(sender_name_raw, sender_raw)
            if who:
                title = f"Meeting with {who}"

        candidate = {
            "_id": candidate_id,
            "user_id": user_id,
            "event_id": event_id,
            "title": title[:200],
            "action_type": action_type,
            "due_datetime": due_datetime,
            "extracted_at": datetime.utcnow(),
            "llm_model": self.llm.default_model,
            "raw_llm_output": raw_output,
        }
        
        try:
            candidates_col.insert_one(candidate)
            logger.info(
                f"✅ Stored TaskCandidate {candidate_id}: "
                f"title={candidate.get('title','')[:80]!r} "
                f"action_type={candidate.get('action_type')!r} "
                f"due_datetime={candidate.get('due_datetime')}"
            )
            return candidate
        except Exception as e:
            logger.error(f"Failed to store task candidate: {e}", exc_info=True)
            return None
    
    def _create_aivis_task(self, user_id: str, candidate: Dict[str, Any], email_data: Dict[str, Any]) -> Optional[str]:
        """
        Create an AivisTask from a TaskCandidate with priority and actions
        """
        tasks_col = get_aivis_tasks_collection()
        if tasks_col is None:
            return None
        
        task_id = f"aivis_{uuid4().hex[:8]}"
        
        # Calculate priority using deterministic scoring
        priority, score, reason = self._calculate_priority(user_id, candidate, email_data)
        
        # Generate actions
        actions, action_metadata = self._generate_actions(candidate, email_data)
        
        task = {
            "_id": task_id,
            "user_id": user_id,
            "priority": priority,
            "priority_score": score,
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
            logger.info(f"✅ Created AivisTask [{priority}] (score: {score}): {task['title'][:50]}")
            return task_id
        except Exception as e:
            logger.error(f"Failed to create AivisTask: {e}", exc_info=True)
            return None
    
    def _calculate_priority(self, user_id: str, candidate: Dict[str, Any], email_data: Dict[str, Any]) -> tuple[str, int, str]:
        """
        Calculate task priority using deterministic scoring (MVP logic)
        
        Scoring weights:
        - Due <24h: +4 points
        - Due 1-3 days: +2 points
        - Sender VIP: +3 points
        - Action required (reply/confirm): +2 points
        - Calendar conflict: +1 point
        
        Buckets:
        - score ≥ 6 → NOW
        - score 3-5 → SOON
        - score ≤ 2 → LATER
        
        Returns: (priority, score, reason_sentence)
        """
        score = 0
        reason_parts = []
        
        due = candidate.get("due_datetime")
        action_type = candidate.get("action_type", "")
        sender = email_data.get("sender", "")
        sender_name = email_data.get("sender_name", sender)
        
        now = datetime.now(timezone.utc)
        
        # 1. Due date scoring
        if due:
            # Normalize due to aware UTC to avoid naive/aware comparison errors
            if isinstance(due, datetime):
                if due.tzinfo is None:
                    due_utc = due.replace(tzinfo=timezone.utc)
                else:
                    due_utc = due.astimezone(timezone.utc)
            else:
                due_utc = None

            if due_utc is not None:
                hours_until_due = (due_utc - now).total_seconds() / 3600
            
                if hours_until_due < 24:
                    score += 4
                    hours = int(hours_until_due)
                    reason_parts.append(f"due in {hours}h")
                elif hours_until_due < 72:  # 1-3 days
                    score += 2
                    days = int(hours_until_due / 24)
                    reason_parts.append(f"due in {days}d")
        
        # 2. VIP sender scoring
        is_vip = self._is_vip_contact(user_id, sender)
        if is_vip:
            score += 3
            reason_parts.append(f"from {sender_name} (VIP)")
        
        # 3. Action required scoring
        if action_type in ["reply", "schedule", "call"]:
            score += 2
            reason_parts.append(f"{action_type} needed")
        
        # 4. Calendar conflict (check if task time conflicts with existing events)
        if due:
            has_conflict = self._check_calendar_conflict(user_id, due)
            if has_conflict:
                score += 1
                reason_parts.append("calendar conflict")
        
        # Determine priority bucket
        if score >= 6:
            priority = TaskPriority.NOW
        elif score >= 3:
            priority = TaskPriority.SOON
        else:
            priority = TaskPriority.LATER
        
        # Generate human-readable reason
        if reason_parts:
            reason = " + ".join(reason_parts).capitalize()
        else:
            reason = "No urgency signals"
        
        return priority, score, reason
    
    def _is_vip_contact(self, user_id: str, email: str) -> bool:
        """Check if a contact is marked as VIP (high importance)"""
        relationships_col = get_relationships_collection()
        if relationships_col is None:
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
    
    def _check_calendar_conflict(self, user_id: str, task_due: datetime) -> bool:
        """
        Check if task due time conflicts with calendar events
        
        Returns True if there's an event within ±30 minutes of the task time
        """
        try:
            from app.db.collections import get_calendar_events_collection
            
            cal_col = get_calendar_events_collection()
            if cal_col is None:
                return False
            
            # Check for events within ±30 minutes of task due time
            time_window_start = task_due - timedelta(minutes=30)
            time_window_end = task_due + timedelta(minutes=30)
            
            conflict = cal_col.find_one({
                "user_id": user_id,
                "$or": [
                    {
                        "start_time": {
                            "$gte": time_window_start,
                            "$lt": time_window_end
                        }
                    },
                    {
                        "end_time": {
                            "$gt": time_window_start,
                            "$lte": time_window_end
                        }
                    }
                ]
            })
            
            return conflict is not None
            
        except Exception as e:
            logger.warning(f"Calendar conflict check failed: {e}")
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
        
        Returns tasks sorted by priority order (NOW first, then SOON, etc.)
        """
        tasks_col = get_aivis_tasks_collection()
        if tasks_col is None:
            return []
        
        query = {
            "user_id": user_id,
            "status": "pending"  # Only active tasks
        }
        
        if priority:
            query["priority"] = priority
        
        try:
            # Define priority order (MVP: 3 levels)
            priority_order = ["NOW", "SOON", "LATER"]
            
            tasks = list(tasks_col.find(query).limit(limit))
            
            # Sort by priority order, then by score (descending), then by created_at
            # Handle old priority values gracefully (map to LATER)
            def get_priority_index(task):
                priority = task.get("priority", "LATER")
                try:
                    return priority_order.index(priority)
                except ValueError:
                    # Old priority values (TODAY, THIS_WEEK, SOMEDAY) -> map to LATER
                    logger.warning(f"Unknown priority '{priority}' for task {task.get('_id')}, treating as LATER")
                    return len(priority_order)  # Put at end
            
            tasks.sort(key=lambda t: (
                get_priority_index(t),
                -t.get("priority_score", 0),  # Higher score first within same priority
                t.get("created_at", datetime.min)
            ))
            
            return tasks
            
        except Exception as e:
            logger.error(f"Failed to fetch tasks: {e}", exc_info=True)
            return []
    
    def mark_task_done(self, user_id: str, task_id: str) -> bool:
        """Mark an AivisTask as completed"""
        tasks_col = get_aivis_tasks_collection()
        if tasks_col is None:
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
