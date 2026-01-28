# Task Pipeline MVP - Documentation

## Overview

The **Task Pipeline MVP** implements a 3-stage system for extracting and prioritizing tasks from events (like emails):

```
Event (raw input) → TaskCandidate (LLM output) → AivisTask (user-facing task)
```

### Key Features

✅ **Automatic task extraction** from Gmail emails using LLM  
✅ **Smart prioritization** based on urgency, sender importance, and stakes  
✅ **Action suggestions** (reply, schedule, call, etc.)  
✅ **Context-aware reasoning** (explains why a task has a certain priority)  
✅ **Clean separation of concerns** (raw data → interpretation → UI)

---

## Architecture

### 1. Event (Raw Input)

Events represent raw inputs from various sources (Gmail, Calendar, Slack, etc.).

**Schema:**
```python
{
  "_id": "gmail_msg_abc123",          # Unique event ID
  "user_id": "user_123",              # User who owns this event
  "source": "gmail",                  # EventSource (gmail, calendar, slack, manual)
  "timestamp": datetime,              # When the event occurred
  "data": {                           # Source-specific data
    "sender": "sam@company.com",
    "subject": "Can we confirm tomorrow?",
    "snippet": "...",
    "thread_id": "t_123",
    "message_id": "msg_abc123"
  },
  "created_at": datetime
}
```

**Collections:** `events`

---

### 2. TaskCandidate (LLM Output)

TaskCandidates are potential tasks extracted by the LLM from events.

**Schema:**
```python
{
  "_id": "candidate_xyz789",
  "user_id": "user_123",
  "event_id": "gmail_msg_abc123",     # Links to source event
  "title": "Confirm meeting with Sam",
  "action_type": "reply",             # reply|schedule|call|review|complete|delegate
  "due_datetime": datetime,           # When the task is due (if mentioned)
  "stake": "relationship",            # What's at stake (relationship, deadline, opportunity, etc.)
  "confidence": 0.86,                 # 0.0-1.0 confidence score
  "extracted_at": datetime,
  "llm_model": "gpt-4o-mini",
  "raw_llm_output": {...}             # For debugging
}
```

**Collections:** `task_candidates`

---

### 3. AivisTask (User-Facing)

AivisTasks are the final prioritized tasks shown to users with actions and reasoning.

**Schema:**
```python
{
  "_id": "aivis_1",
  "user_id": "user_123",
  "priority": "NOW",                  # NOW|TODAY|THIS_WEEK|LATER|SOMEDAY
  "title": "Confirm meeting with Sam",
  "reason": "Due tomorrow + from Sam (VIP) + deliverable mentioned",
  "due_datetime": datetime,
  "source_event": "gmail_msg_abc123",
  "task_candidate": "candidate_xyz789",
  "actions": [                        # Available actions
    "draft_reply",
    "schedule",
    "open_in_gmail"
  ],
  "action_metadata": {                # Action-specific data
    "draft_reply": {
      "to": "sam@company.com",
      "thread_id": "t_123",
      "suggested_response": "..."
    },
    "open_in_gmail": {
      "url": "https://mail.google.com/mail/u/0/#inbox/t_123"
    }
  },
  "status": "pending",                # pending|in_progress|completed|cancelled
  "created_at": datetime,
  "updated_at": datetime,
  "completed_at": datetime
}
```

**Collections:** `aivis_tasks`

---

## Priority Calculation

The system calculates priority using multiple factors:

### Priority Levels

1. **NOW** 🔴
   - Due within 24 hours + from VIP sender
   - High confidence + relationship stake + VIP sender

2. **TODAY** 🟡
   - Due within 24 hours
   - High confidence + critical stake (deadline, opportunity, reputation)

3. **THIS_WEEK** 🟢
   - Due within 7 days
   - Medium confidence

4. **LATER** 🔵
   - Due after this week

5. **SOMEDAY** ⚪
   - No deadline or low confidence

### Factors Considered

- **Due date urgency**: Time until the task is due
- **Sender importance**: Is the sender marked as VIP in relationships?
- **Confidence**: How confident is the LLM that this is a real task?
- **Stake type**: What's at risk? (relationship, deadline, opportunity, reputation, money, routine)

---

## API Endpoints

### POST `/api/tasks/process-email`

Process a Gmail email through the task pipeline.

**Request:**
```json
{
  "user_id": "user_123",
  "email": {
    "message_id": "msg_abc",
    "thread_id": "thread_123",
    "sender": "sam@company.com",
    "sender_name": "Sam Chen",
    "subject": "Can we confirm tomorrow?",
    "snippet": "Hey, just wanted to confirm...",
    "body": "Full email body...",
    "timestamp": "2026-01-28T09:12:00",
    "labels": ["INBOX", "UNREAD"]
  }
}
```

**Response:**
```json
{
  "success": true,
  "task_id": "aivis_abc123",
  "task": {
    "_id": "aivis_abc123",
    "priority": "NOW",
    "title": "Confirm meeting with Sam",
    "reason": "Due tomorrow + from Sam (VIP)",
    "actions": ["draft_reply", "schedule", "open_in_gmail"],
    "status": "pending"
  }
}
```

---

### GET `/api/tasks`

Get user's tasks, optionally filtered by priority.

**Query Parameters:**
- `user_id` (required): User ID
- `priority` (optional): `NOW|TODAY|THIS_WEEK|LATER|SOMEDAY`
- `limit` (optional): Max tasks to return (default: 50)

**Response:**
```json
{
  "success": true,
  "tasks": [
    {
      "_id": "aivis_1",
      "priority": "NOW",
      "title": "Confirm meeting with Sam",
      "reason": "Due tomorrow + from Sam (VIP)",
      "actions": ["draft_reply", "open_in_gmail"],
      "status": "pending"
    }
  ],
  "count": 1
}
```

---

### POST `/api/tasks/:id/complete`

Mark a task as completed.

**Request:**
```json
{
  "user_id": "user_123"
}
```

**Response:**
```json
{
  "success": true,
  "task_id": "aivis_abc123"
}
```

---

## Usage Example

### 1. Via API

```bash
# Process an email
curl -X POST http://localhost:10000/api/tasks/process-email \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "email": {
      "message_id": "msg_001",
      "thread_id": "thread_001",
      "sender": "boss@company.com",
      "subject": "Urgent: Board deck needed",
      "body": "Can you send the board deck by 5pm today?",
      "timestamp": "2026-01-28T09:00:00"
    }
  }'

# Get all tasks
curl "http://localhost:10000/api/tasks?user_id=user_123"

# Get only NOW tasks
curl "http://localhost:10000/api/tasks?user_id=user_123&priority=NOW"

# Mark task as done
curl -X POST http://localhost:10000/api/tasks/aivis_abc123/complete \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_123"}'
```

### 2. Via Python Script

```python
from app.services.task_pipeline_service import get_task_pipeline_service
from datetime import datetime

pipeline = get_task_pipeline_service()

# Process an email
email_data = {
    "message_id": "msg_001",
    "thread_id": "thread_001",
    "sender": "sam@company.com",
    "subject": "Can we sync tomorrow?",
    "body": "Let's have a quick call tomorrow at 2pm to discuss the Q1 deck.",
    "timestamp": datetime.utcnow()
}

task_id = pipeline.process_gmail_event("user_123", email_data)

# Get tasks by priority
now_tasks = pipeline.get_tasks_by_priority("user_123", priority="NOW")
all_tasks = pipeline.get_tasks_by_priority("user_123")

# Mark task as done
pipeline.mark_task_done("user_123", task_id)
```

### 3. Via Demo Script

```bash
# Run the interactive demo
python examples/task_pipeline_demo.py
```

---

## Integration with Existing System

The Task Pipeline MVP integrates seamlessly with your existing system:

### Gmail Integration

When emails are received, you can automatically process them:

```python
from app.services.task_pipeline_service import get_task_pipeline_service

def on_new_email(user_id, email_data):
    """Called when a new email arrives"""
    pipeline = get_task_pipeline_service()
    task_id = pipeline.process_gmail_event(user_id, email_data)
    
    if task_id:
        # Notify user about new task
        notify_user(user_id, f"New task created: {task_id}")
```

### Relationships Integration

The system checks if senders are marked as VIP in the `relationships` collection:

```python
# A contact marked as VIP (importance="high") will boost task priority
{
  "user_id": "user_123",
  "contact_email": "boss@company.com",
  "importance": "high",  # <- VIP marker
  "relationship_type": "colleague"
}
```

---

## Database Collections

The MVP adds 3 new MongoDB collections:

1. **`events`** - Raw input events from all sources
2. **`task_candidates`** - LLM-extracted task candidates
3. **`aivis_tasks`** - Final prioritized user-facing tasks

All collections have proper indexes for performance:
- Sorted by timestamp/priority
- Filtered by user_id
- Linked by event_id/candidate_id

---

## Files Created

```
app/
  memory/
    task_models.py              # Data models and schemas
  services/
    task_pipeline_service.py    # Core pipeline logic
  api/
    tasks_routes.py             # REST API endpoints

examples/
  task_pipeline_demo.py         # Interactive demo script

docs/
  TASK_PIPELINE_MVP.md          # This documentation
```

---

## Future Enhancements

### Phase 2 Ideas

1. **Multi-source events**
   - Calendar events → "Prepare for meeting" tasks
   - Slack messages → Action items
   - Manual task creation

2. **Smarter prioritization**
   - Learn from user behavior (which tasks they do first)
   - Context from past interactions
   - Project/goal alignment

3. **Batch processing**
   - Process multiple emails at once
   - Deduplicate similar tasks
   - Group related tasks

4. **Action execution**
   - Actually send drafts
   - Create calendar events
   - Make phone calls

5. **Task templates**
   - Common task patterns
   - Quick actions
   - Workflows

---

## Testing

Run the demo to verify everything works:

```bash
# Basic demo
python examples/task_pipeline_demo.py

# Start the server
python server.py

# Test API endpoints
curl "http://localhost:10000/api/tasks?user_id=demo_user"
```

---

## Summary

The MVP provides a **clean, extensible foundation** for task extraction and prioritization:

✅ **3-stage pipeline** (Event → TaskCandidate → AivisTask)  
✅ **LLM-powered extraction** (automatic task detection)  
✅ **Context-aware prioritization** (smart urgency calculation)  
✅ **Actionable tasks** (with suggested actions and metadata)  
✅ **API-ready** (REST endpoints for integration)  

This is a **small but powerful** system that can scale to handle multiple sources, complex prioritization logic, and intelligent task management.
