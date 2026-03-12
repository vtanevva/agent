# ✅ MVP Task Pipeline - Deterministic Scoring Implementation

## Overview

Updated implementation with **deterministic, points-based priority scoring** as specified in MVP requirements.

---

## 3-Step Pipeline

### STEP 1: Ingest 📥

**What:** Pull data from sources

```python
# Pull last N unread Gmail threads
unread_emails = gmail.list_threads(query="is:unread", max_results=20)

# Pull today + tomorrow calendar events
calendar_events = calendar.get_events(
    time_min=today,
    time_max=tomorrow_end
)
```

**API Endpoint:**
```bash
POST /api/tasks/ingest
{
  "user_id": "user_123",
  "max_emails": 20
}

Response:
{
  "emails_processed": 10,
  "calendar_events": 3,
  "tasks_created": 5
}
```

---

### STEP 2: Task Extraction (LLM) 🤖

**What:** Extract structured tasks, no reasoning

**Prompt (simplified):**
```
Extract actionable tasks from this email. Output JSON only.

RULES:
• If no clear action → ignore
• If no implied deadline → mark due_datetime = null
• Only concrete tasks (reply, schedule, call, etc.)

OUTPUT (strict JSON):
{
  "tasks": [
    {
      "title": "task description (max 12 words)",
      "action_type": "reply|schedule|call|review|complete|delegate",
      "due_datetime": "YYYY-MM-DDTHH:MM:SS or null"
    }
  ]
}
```

**LLM Settings:**
- Temperature: `0.0` (deterministic)
- Max tokens: `500`
- Model: `gpt-4o-mini`

**Output Example:**
```json
{
  "tasks": [
    {
      "title": "Send board deck to boss",
      "action_type": "reply",
      "due_datetime": "2026-01-28T17:00:00"
    }
  ]
}
```

---

### STEP 3: Priority Scoring (Deterministic) 🎯

**What:** Calculate score using clear weights, assign bucket

#### Scoring Components

| Signal | Weight | Condition |
|--------|--------|-----------|
| **Due soon** | +4 | < 24 hours |
| **Due soon** | +2 | 1-3 days |
| **Sender VIP** | +3 | `importance: "high"` in relationships |
| **Action required** | +2 | action_type = reply/schedule/call |
| **Calendar conflict** | +1 | Task time overlaps ±30min with event |

#### Priority Buckets

```
score ≥ 6  →  NOW     (🔴 Urgent)
score 3-5  →  SOON    (🟡 Important)
score ≤ 2  →  LATER   (⚪ Low priority)
```

#### Reason Generation

```python
reason_parts = []

if hours_until_due < 24:
    reason_parts.append(f"due in {hours}h")
if is_vip:
    reason_parts.append(f"from {sender_name} (VIP)")
if action_type in ["reply", "schedule", "call"]:
    reason_parts.append(f"{action_type} needed")
if calendar_conflict:
    reason_parts.append("calendar conflict")

reason = " + ".join(reason_parts).capitalize()
# Example: "Due in 7h + from Boss (VIP) + reply needed"
```

---

## Complete Example

### Input: Urgent Email from Boss

```
From: boss@company.com
Subject: URGENT: Board deck needed
Body: Can you send the board deck by 5pm today?
Time: 10:00 AM (current time)
```

### Step 1: Event Created

```json
{
  "_id": "gmail_msg_abc123",
  "user_id": "user_123",
  "source": "gmail",
  "timestamp": "2026-01-28T10:00:00",
  "data": {
    "sender": "boss@company.com",
    "subject": "URGENT: Board deck needed",
    "body": "Can you send the board deck by 5pm today?"
  }
}
```

### Step 2: LLM Extracts Task

**LLM Input:**
```
Extract actionable tasks from this email. Output JSON only.

Email:
From: Boss <boss@company.com>
Subject: URGENT: Board deck needed

Can you send the board deck by 5pm today?
```

**LLM Output:**
```json
{
  "tasks": [
    {
      "title": "Send board deck",
      "action_type": "reply",
      "due_datetime": "2026-01-28T17:00:00"
    }
  ]
}
```

**TaskCandidate Stored:**
```json
{
  "_id": "candidate_xyz789",
  "user_id": "user_123",
  "event_id": "gmail_msg_abc123",
  "title": "Send board deck",
  "action_type": "reply",
  "due_datetime": "2026-01-28T17:00:00",
  "extracted_at": "2026-01-28T10:00:05"
}
```

### Step 3: Deterministic Scoring

```python
# Scoring calculation
score = 0
reason_parts = []

# Due date (7 hours until 5pm)
hours_until_due = 7
if hours_until_due < 24:
    score += 4
    reason_parts.append("due in 7h")

# VIP check (boss@company.com is marked as VIP)
is_vip = check_vip("boss@company.com")  # True
if is_vip:
    score += 3
    reason_parts.append("from Boss (VIP)")

# Action type (reply)
if action_type == "reply":
    score += 2
    reason_parts.append("reply needed")

# Calendar conflict (no meeting at 5pm)
has_conflict = check_calendar_conflict("2026-01-28T17:00:00")  # False
if has_conflict:
    score += 1

# Total score: 4 + 3 + 2 = 9

# Bucket assignment
if score >= 6:
    priority = "NOW"  # ← This one

reason = "Due in 7h + from Boss (VIP) + reply needed"
```

**AivisTask Created:**
```json
{
  "_id": "aivis_abc123",
  "user_id": "user_123",
  "priority": "NOW",
  "priority_score": 9,
  "title": "Send board deck",
  "reason": "Due in 7h + from Boss (VIP) + reply needed",
  "due_datetime": "2026-01-28T17:00:00",
  "actions": ["draft_reply", "open_in_gmail"],
  "status": "pending"
}
```

### UI Display

```
┌──────────────────────────────────────────────────┐
│ 🔴 NOW (score: 9)                       [⋮ Menu] │
├──────────────────────────────────────────────────┤
│                                                  │
│ Send board deck                                  │
│                                                  │
│ 💡 Due in 7h + from Boss (VIP) + reply needed   │
│ ⏰ Today at 5:00 PM                              │
│                                                  │
├──────────────────────────────────────────────────┤
│ Actions:                                         │
│                                                  │
│ [📝 Draft Reply]        [📧 Open Email]         │
│                                                  │
│ [ ✓ Mark as Done ]                              │
└──────────────────────────────────────────────────┘
```

---

## Score Examples

### Score 10: Urgent VIP with Conflict

```
Email: "Call tomorrow at 2pm to discuss contract" (from VIP client)
Calendar: Meeting already scheduled at 2pm tomorrow

Score breakdown:
- Due < 24h: +4
- VIP sender: +3
- Call needed: +2
- Calendar conflict: +1
Total: 10 → NOW

Reason: "Due in 18h + from Client (VIP) + call needed + calendar conflict"
```

### Score 6: Urgent Non-VIP

```
Email: "Can you review the doc by EOD today?"

Score breakdown:
- Due < 24h: +4
- VIP sender: 0
- Review needed: 0 (passive action)
- Calendar conflict: 0
Total: 4 → SOON

Reason: "Due in 6h"
```

### Score 5: VIP with Action

```
Email: "Can we schedule a sync?" (from VIP, no deadline)

Score breakdown:
- Due: 0
- VIP sender: +3
- Schedule needed: +2
- Calendar conflict: 0
Total: 5 → SOON

Reason: "From Manager (VIP) + schedule needed"
```

### Score 2: Normal Reply

```
Email: "Let me know your thoughts" (from colleague, no deadline)

Score breakdown:
- Due: 0
- VIP sender: 0
- Reply needed: +2
- Calendar conflict: 0
Total: 2 → LATER

Reason: "Reply needed"
```

### Score 0: Newsletter

```
Email: "Weekly tech roundup"

Score breakdown:
- Due: 0
- VIP sender: 0
- Action: 0 (no task extracted)
- Calendar conflict: 0
Total: 0 → LATER (no task created)
```

---

## API Usage

### 1. Ingest and Process

```bash
# Pull unread emails and process into tasks
curl -X POST http://localhost:10000/api/tasks/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "max_emails": 20
  }'

Response:
{
  "success": true,
  "emails_processed": 10,
  "calendar_events": 3,
  "tasks_created": 5,
  "task_ids": ["aivis_1", "aivis_2", ...]
}
```

### 2. Get Tasks by Priority

```bash
# Get all NOW tasks
curl "http://localhost:10000/api/tasks?user_id=user_123&priority=NOW"

Response:
{
  "success": true,
  "tasks": [
    {
      "_id": "aivis_1",
      "priority": "NOW",
      "priority_score": 9,
      "title": "Send board deck",
      "reason": "Due in 7h + from Boss (VIP) + reply needed",
      "actions": ["draft_reply", "open_in_gmail"]
    }
  ]
}
```

### 3. Complete Task

```bash
curl -X POST http://localhost:10000/api/tasks/aivis_1/complete \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_123"}'
```

---

## Key Changes from Initial Implementation

| Aspect | Before | After |
|--------|--------|-------|
| **Priority levels** | 5 levels (NOW/TODAY/THIS_WEEK/LATER/SOMEDAY) | **3 levels (NOW/SOON/LATER)** |
| **Scoring** | Mixed LLM + logic | **Pure deterministic** |
| **LLM extraction** | With confidence/stake | **Minimal (title/action/due only)** |
| **Score visibility** | Hidden | **Exposed in API response** |
| **Reasoning** | LLM-generated | **Deterministic template** |
| **Weights** | Implicit | **Explicit (+4, +3, +2, +1)** |

---

## Files Updated

1. **`app/memory/task_models.py`**
   - Updated `TaskPriority` enum (3 levels)
   - Removed `stake` and `confidence` from TaskCandidate
   - Added `priority_score` to AivisTask

2. **`app/services/task_pipeline_service.py`**
   - New `ingest_and_process()` method
   - Updated `_calculate_priority()` - deterministic scoring
   - Added `_check_calendar_conflict()` method
   - Simplified LLM extraction prompt

3. **`app/api/tasks_routes.py`**
   - Added `POST /api/tasks/ingest` endpoint

4. **`examples/task_pipeline_demo.py`**
   - Updated to show priority scores

5. **`docs/PRIORITY_SCORING_LOGIC.md`** (new)
   - Complete scoring reference

---

## Benefits of Deterministic Scoring

✅ **Transparent** - Users see exact score and reasoning  
✅ **Predictable** - Same inputs = same priority  
✅ **Fast** - No LLM call for scoring (~10ms vs ~500ms)  
✅ **Tunable** - Easy to adjust weights  
✅ **Debuggable** - Can trace why task got priority  
✅ **Testable** - Unit tests for scoring logic  
✅ **Explainable** - "Due in 7h + from VIP + reply needed"  

---

## Testing

### Run Demo

```bash
python examples/task_pipeline_demo.py
```

### Unit Test Priority Calculation

```python
from app.services.task_pipeline_service import get_task_pipeline_service
from datetime import datetime, timedelta

pipeline = get_task_pipeline_service()

# Test: Urgent VIP email
candidate = {
    "title": "Send deck",
    "action_type": "reply",
    "due_datetime": datetime.now() + timedelta(hours=7)
}

email_data = {
    "sender": "boss@company.com",  # VIP
    "sender_name": "Boss"
}

priority, score, reason = pipeline._calculate_priority(
    user_id="test_user",
    candidate=candidate,
    email_data=email_data
)

assert priority == "NOW"
assert score == 9  # 4 + 3 + 2
assert "due in 7h" in reason.lower()
assert "vip" in reason.lower()
```

---

## Tuning Weights

Edit `task_pipeline_service.py`:

```python
# Current weights
DUE_URGENT = 4      # < 24h
DUE_SOON = 2        # 1-3 days
VIP_SENDER = 3
ACTION_REQUIRED = 2
CALENDAR_CONFLICT = 1

# Make VIP more important
VIP_SENDER = 5

# Adjust buckets
if score >= 8:  # Stricter NOW bucket
    priority = "NOW"
elif score >= 4:
    priority = "SOON"
else:
    priority = "LATER"
```

---

## Summary

The MVP now implements **exactly** the deterministic scoring logic you specified:

1. ✅ **Ingest** - Pull unread emails + calendar events
2. ✅ **Extract** - LLM outputs structured JSON only
3. ✅ **Score** - Deterministic weights (+4, +3, +2, +1)
4. ✅ **Bucket** - score ≥6→NOW, 3-5→SOON, ≤2→LATER
5. ✅ **Reason** - Human sentence from template

**Simple. Transparent. Tunable.** 🎯
