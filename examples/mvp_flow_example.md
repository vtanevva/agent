# MVP Task Pipeline - Complete Flow Example

## Scenario: Sam's Meeting Confirmation Email

### 📧 Input: Gmail Email

```
From: Sam Chen <sam@company.com>
To: you@company.com
Subject: Quick sync on Q1 presentation
Date: Jan 28, 2026, 9:12 AM

Hey!

Can we have a quick call tomorrow at 2pm to finalize the Q1 presentation? 

I reviewed the latest version and it looks great, but I have a few questions 
about the revenue projections on slide 8. Also, we should probably add a 
competitive analysis section.

Let me know if 2pm works for you. If not, I'm free anytime after 3pm.

Thanks!
Sam
```

---

## Stage 1: Event (Raw Input) 📥

The system stores the raw email as an **Event**.

```json
{
  "_id": "gmail_msg_abc123",
  "user_id": "user_123",
  "source": "gmail",
  "timestamp": "2026-01-28T09:12:00Z",
  "data": {
    "sender": "sam@company.com",
    "sender_name": "Sam Chen",
    "subject": "Quick sync on Q1 presentation",
    "snippet": "Hey! Can we have a quick call tomorrow at 2pm...",
    "body": "Hey!\n\nCan we have a quick call tomorrow at 2pm to finalize the Q1 presentation?\n\nI reviewed the latest version...",
    "thread_id": "thread_demo_001",
    "message_id": "msg_abc123",
    "labels": ["INBOX", "UNREAD"]
  },
  "created_at": "2026-01-28T09:12:05Z"
}
```

**Collection:** `events`  
**Purpose:** Store raw data, never modified

---

## Stage 2: TaskCandidate (LLM Extraction) 🤖

The LLM analyzes the email and extracts actionable tasks.

### LLM Prompt (simplified):

```
Extract actionable tasks from this email for the recipient.

Rules:
- Only concrete, specific actions
- No generic "read email" tasks
- Estimate due date/time from content
- Assess what's at stake
- Provide confidence score

Email:
From: Sam Chen <sam@company.com>
Subject: Quick sync on Q1 presentation
Body: Can we have a quick call tomorrow at 2pm to finalize the Q1 presentation?
```

### LLM Response:

```json
{
  "tasks": [
    {
      "title": "Call with Sam to finalize Q1 presentation",
      "action_type": "call",
      "due_datetime": "2026-01-29T14:00:00",
      "stake": "relationship",
      "confidence": 0.92,
      "reasoning": "Sam explicitly requests a call tomorrow at 2pm to discuss Q1 deck"
    }
  ]
}
```

### Stored TaskCandidate:

```json
{
  "_id": "candidate_xyz789",
  "user_id": "user_123",
  "event_id": "gmail_msg_abc123",
  "title": "Call with Sam to finalize Q1 presentation",
  "action_type": "call",
  "due_datetime": "2026-01-29T14:00:00Z",
  "stake": "relationship",
  "confidence": 0.92,
  "extracted_at": "2026-01-28T09:12:08Z",
  "llm_model": "gpt-4o-mini",
  "raw_llm_output": {
    "reasoning": "Sam explicitly requests a call tomorrow at 2pm to discuss Q1 deck"
  }
}
```

**Collection:** `task_candidates`  
**Purpose:** LLM interpretation, can be regenerated

---

## Stage 3: AivisTask (Prioritized Task) 🎯

The system calculates priority and generates actions.

### Priority Calculation:

```python
# Factors considered:
due_hours = (due_datetime - now).total_seconds() / 3600  # ~29 hours
is_vip = check_vip(sam@company.com)  # True (marked as important contact)
confidence = 0.92  # High
stake = "relationship"  # Important

# Logic:
if due_hours < 24 and is_vip:
    priority = "NOW"
    reason = "Due tomorrow + from Sam (VIP)"
```

### Action Generation:

```python
# Based on action_type = "call"
actions = [
  "call",           # Primary action
  "schedule",       # Secondary - add to calendar
  "open_in_gmail"   # View original email
]

action_metadata = {
  "call": {
    "contact": "sam@company.com",
    "scheduled_time": "2026-01-29T14:00:00Z"
  },
  "schedule": {
    "event_time": "2026-01-29T14:00:00Z",
    "duration_minutes": 30,
    "title": "Call with Sam - Q1 presentation"
  },
  "open_in_gmail": {
    "thread_id": "thread_demo_001",
    "url": "https://mail.google.com/mail/u/0/#inbox/thread_demo_001"
  }
}
```

### Final AivisTask:

```json
{
  "_id": "aivis_1a2b3c",
  "user_id": "user_123",
  "priority": "NOW",
  "title": "Call with Sam to finalize Q1 presentation",
  "reason": "Due tomorrow + from Sam (VIP) + relationship stake",
  "due_datetime": "2026-01-29T14:00:00Z",
  "source_event": "gmail_msg_abc123",
  "task_candidate": "candidate_xyz789",
  "actions": [
    "call",
    "schedule",
    "open_in_gmail"
  ],
  "action_metadata": {
    "call": {
      "contact": "sam@company.com",
      "scheduled_time": "2026-01-29T14:00:00Z"
    },
    "schedule": {
      "event_time": "2026-01-29T14:00:00Z",
      "duration_minutes": 30,
      "title": "Call with Sam - Q1 presentation"
    },
    "open_in_gmail": {
      "thread_id": "thread_demo_001",
      "url": "https://mail.google.com/mail/u/0/#inbox/thread_demo_001"
    }
  },
  "status": "pending",
  "created_at": "2026-01-28T09:12:10Z",
  "updated_at": "2026-01-28T09:12:10Z",
  "completed_at": null
}
```

**Collection:** `aivis_tasks`  
**Purpose:** User-facing task with priority and actions

---

## UI Display 📱

### Task Card:

```
┌──────────────────────────────────────────────────────────────┐
│ 🔴 NOW                                           [⋮ Menu]     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ Call with Sam to finalize Q1 presentation                   │
│                                                              │
│ 💡 Due tomorrow + from Sam (VIP) + relationship stake       │
│ ⏰ Tomorrow at 2:00 PM                                       │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ Actions:                                                      │
│                                                              │
│ [📞 Call Sam]   [📅 Add to Calendar]   [📧 Open Email]     │
│                                                              │
│ [ ✓ Mark as Done ]                                          │
└──────────────────────────────────────────────────────────────┘
```

### Actions When Clicked:

1. **📞 Call Sam**
   - Opens dialer/phone app with `sam@company.com`
   - Pre-fills note: "Q1 presentation sync"

2. **📅 Add to Calendar**
   - Creates calendar event:
     - Title: "Call with Sam - Q1 presentation"
     - Time: Tomorrow at 2:00 PM
     - Duration: 30 minutes

3. **📧 Open Email**
   - Opens Gmail thread: `thread_demo_001`
   - URL: `https://mail.google.com/mail/u/0/#inbox/thread_demo_001`

4. **✓ Mark as Done**
   - Updates `status` to "completed"
   - Sets `completed_at` timestamp
   - Removes from active task list

---

## Complete Flow Summary

```
📧 Email arrives
    ↓
1️⃣ Event stored (raw data preserved)
    ↓
2️⃣ LLM extracts TaskCandidate (title, action_type, due, stake, confidence)
    ↓
3️⃣ System calculates priority (NOW/TODAY/THIS_WEEK/LATER/SOMEDAY)
    ↓
4️⃣ System generates actions (call, schedule, open_in_gmail)
    ↓
5️⃣ AivisTask created (user-facing task)
    ↓
📱 User sees task card with priority and actions
    ↓
✅ User takes action or marks done
```

---

## Priority Examples

### 🔴 NOW
```
• "Board deck needed by EOD" (due in 6 hours + urgent)
• "Call with Sam tomorrow" (due in 24h + VIP sender)
• "Sign contract ASAP" (high confidence + deadline stake)
```

### 🟡 TODAY
```
• "Review document by tonight" (due in 12 hours)
• "Prepare presentation" (high confidence + opportunity stake)
• "Follow up on proposal" (high confidence + business impact)
```

### 🟢 THIS_WEEK
```
• "Lunch next week?" (due in 5 days)
• "Review quarterly report" (medium confidence)
• "Update project docs" (routine task)
```

### 🔵 LATER
```
• "Plan Q2 strategy" (due in 2 weeks)
• "Read research paper" (no urgency)
```

### ⚪ SOMEDAY
```
• "Check out new tool" (low priority)
• "Coffee sometime?" (no deadline)
```

---

## Why This Design?

### ✅ Separation of Concerns
- **Event**: Raw data (for audit/replay)
- **TaskCandidate**: LLM interpretation (can regenerate)
- **AivisTask**: Final UI (with business logic)

### ✅ Traceability
- Can trace back: Task → Candidate → Event
- Can see LLM reasoning
- Can debug/improve extraction

### ✅ Flexibility
- Can re-extract tasks from events (if prompt improves)
- Can reprioritize tasks (if rules change)
- Can add new action types

### ✅ Scalability
- Works with any event source (Gmail, Calendar, Slack)
- Can batch process events
- Can deduplicate similar tasks

---

## Testing the Flow

### Using Python:

```python
from app.services.task_pipeline_service import get_task_pipeline_service
from datetime import datetime

pipeline = get_task_pipeline_service()

# The email data
email = {
    "message_id": "msg_abc123",
    "thread_id": "thread_demo_001",
    "sender": "sam@company.com",
    "sender_name": "Sam Chen",
    "subject": "Quick sync on Q1 presentation",
    "body": "Can we have a quick call tomorrow at 2pm to finalize the Q1 presentation?",
    "timestamp": datetime.utcnow()
}

# Process through pipeline
task_id = pipeline.process_gmail_event("user_123", email)

# Get the task
tasks = pipeline.get_tasks_by_priority("user_123", priority="NOW")
print(tasks[0])  # See the AivisTask
```

### Using API:

```bash
curl -X POST http://localhost:10000/api/tasks/process-email \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "email": {
      "message_id": "msg_abc123",
      "thread_id": "thread_demo_001",
      "sender": "sam@company.com",
      "sender_name": "Sam Chen",
      "subject": "Quick sync on Q1 presentation",
      "body": "Can we have a quick call tomorrow at 2pm?",
      "timestamp": "2026-01-28T09:12:00"
    }
  }'
```

---

**Result:** A complete, working MVP that turns emails into prioritized, actionable tasks! 🎉
