# Priority Scoring Logic (MVP)

## Overview

The task priority system uses **deterministic scoring** with clear weights and buckets. No LLM reasoning involved in priority calculation.

---

## Scoring Components

### 1. Due Date Urgency

| Timeframe | Points | Example |
|-----------|--------|---------|
| < 24 hours | **+4** | "by EOD today", "tomorrow morning" |
| 1-3 days | **+2** | "by Friday", "early next week" |
| > 3 days | **0** | "next month", "sometime" |
| No deadline | **0** | null |

### 2. Sender VIP Status

| Status | Points | How Determined |
|--------|--------|----------------|
| VIP sender | **+3** | `relationships` collection, `importance: "high"` |
| Normal sender | **0** | Not in VIP list |

**Example VIP contacts:**
- Direct manager
- Key clients
- C-suite executives
- Important partners

### 3. Action Required

| Action Type | Points | Examples |
|-------------|--------|----------|
| reply, schedule, call | **+2** | "Can you confirm?", "Let's schedule", "Call me" |
| review, complete, delegate | **0** | Passive tasks |

### 4. Calendar Conflict

| Condition | Points | Logic |
|-----------|--------|-------|
| Task time conflicts with event | **+1** | Task due_datetime ±30min overlaps with calendar event |
| No conflict | **0** | Clear schedule |

---

## Priority Buckets

```
score ≥ 6  →  NOW     (🔴 Red - Urgent)
score 3-5  →  SOON    (🟡 Yellow - Important)
score ≤ 2  →  LATER   (⚪ White - Low priority)
```

---

## Examples

### Example 1: Urgent Email from Boss

**Email:**
```
From: boss@company.com (VIP)
Subject: URGENT: Board deck needed
Body: Can you send the board deck by 5pm today?
Time: 10:00 AM (7 hours until deadline)
```

**Scoring:**
- Due < 24h: **+4**
- Sender VIP: **+3**
- Action required (send/reply): **+2**
- Calendar conflict: **0**
- **Total: 9 points**

**Priority: NOW** (score ≥ 6)

**Reason:** "Due in 7h + from Boss (VIP) + reply needed"

---

### Example 2: Meeting Request from Colleague

**Email:**
```
From: colleague@company.com (not VIP)
Subject: Coffee next week?
Body: Want to grab coffee sometime next week? Let me know what works.
Time: Monday (no specific deadline)
```

**Scoring:**
- Due: **0** (no specific deadline)
- Sender VIP: **0**
- Action required (reply): **+2**
- Calendar conflict: **0**
- **Total: 2 points**

**Priority: LATER** (score ≤ 2)

**Reason:** "Reply needed"

---

### Example 3: Project Review Due Friday

**Email:**
```
From: manager@company.com (VIP)
Subject: Q1 report review
Body: Can you review the Q1 report by Friday EOD?
Time: Monday (4 days until deadline)
```

**Scoring:**
- Due 1-3 days: **0** (4 days = outside window)
- Sender VIP: **+3**
- Action required (review): **0** (passive)
- Calendar conflict: **0**
- **Total: 3 points**

**Priority: SOON** (score 3-5)

**Reason:** "From Manager (VIP)"

---

### Example 4: Urgent Call Tomorrow at 2pm

**Email:**
```
From: client@bigcorp.com (VIP)
Subject: Can we sync tomorrow?
Body: Can we have a quick call tomorrow at 2pm to discuss the proposal?
Time: Today at 5pm (21 hours until call)
Calendar: Meeting at 2pm tomorrow already exists
```

**Scoring:**
- Due < 24h: **+4**
- Sender VIP: **+3**
- Action required (call): **+2**
- Calendar conflict: **+1** (overlaps with existing 2pm meeting)
- **Total: 10 points**

**Priority: NOW** (score ≥ 6)

**Reason:** "Due in 21h + from Client (VIP) + call needed + calendar conflict"

---

### Example 5: Newsletter with No Action

**Email:**
```
From: newsletter@tech.com (not VIP)
Subject: Weekly tech roundup
Body: Here's what happened in tech this week...
Time: Any
```

**Scoring:**
- Due: **0** (no action)
- Sender VIP: **0**
- Action required: **0** (no action extracted)
- Calendar conflict: **0**
- **Total: 0 points**

**Priority: LATER** (score ≤ 2)

**No task created** (LLM should return empty tasks array)

---

## Implementation

### Step 1: LLM Extraction (No Scoring)

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

### Step 2: Deterministic Scoring (Python)

```python
score = 0
reason_parts = []

# Due date scoring
hours_until_due = (due - now).total_seconds() / 3600
if hours_until_due < 24:
    score += 4
    reason_parts.append(f"due in {int(hours_until_due)}h")
elif hours_until_due < 72:
    score += 2
    reason_parts.append(f"due in {int(hours_until_due/24)}d")

# VIP scoring
if is_vip(sender):
    score += 3
    reason_parts.append(f"from {sender_name} (VIP)")

# Action scoring
if action_type in ["reply", "schedule", "call"]:
    score += 2
    reason_parts.append(f"{action_type} needed")

# Calendar conflict
if check_calendar_conflict(due):
    score += 1
    reason_parts.append("calendar conflict")

# Bucket assignment
if score >= 6:
    priority = "NOW"
elif score >= 3:
    priority = "SOON"
else:
    priority = "LATER"

reason = " + ".join(reason_parts).capitalize()
```

### Step 3: Result

```json
{
  "_id": "aivis_abc123",
  "priority": "NOW",
  "priority_score": 9,
  "title": "Send board deck",
  "reason": "Due in 7h + from Boss (VIP) + reply needed",
  "due_datetime": "2026-01-28T17:00:00",
  "actions": ["draft_reply", "open_in_gmail"],
  "status": "pending"
}
```

---

## Score Distribution Examples

### Common Score Ranges

| Score | Priority | Typical Scenarios |
|-------|----------|-------------------|
| 10 | NOW | Urgent VIP email due today with calendar conflict |
| 9 | NOW | Urgent VIP email due today requiring action |
| 7 | NOW | VIP email due today (no action required) |
| 6 | NOW | Non-VIP urgent email requiring action |
| 5 | SOON | VIP email with action (no deadline) |
| 4 | SOON | Non-VIP email due within 24h |
| 3 | SOON | VIP email (no action or deadline) |
| 2 | LATER | Non-VIP email requiring action |
| 1 | LATER | Calendar conflict only |
| 0 | LATER | No signals |

---

## VIP Management

### How to Mark Contacts as VIP

```python
# Via relationships collection
{
  "user_id": "user_123",
  "contact_email": "boss@company.com",
  "importance": "high",  # <- This marks as VIP
  "relationship_type": "colleague"
}
```

### VIP List Management API (Future)

```
POST /api/contacts/:email/mark-vip
DELETE /api/contacts/:email/unmark-vip
GET /api/contacts/vips
```

---

## Tuning the System

### Adjusting Weights

If you want to make sender importance more/less impactful:

```python
# Current weights
DUE_URGENT = 4      # < 24h
DUE_SOON = 2        # 1-3 days
VIP_SENDER = 3
ACTION_REQUIRED = 2
CALENDAR_CONFLICT = 1

# Example: Make VIP more important
VIP_SENDER = 4  # Now equal to urgent deadline
```

### Adjusting Buckets

```python
# Current buckets
score >= 6: NOW
score 3-5: SOON
score <= 2: LATER

# Example: Stricter NOW bucket
score >= 8: NOW     # Only truly urgent tasks
score 4-7: SOON
score <= 3: LATER
```

---

## Benefits of Deterministic Scoring

✅ **Transparent** - Users understand why tasks are prioritized  
✅ **Predictable** - Same inputs always produce same priority  
✅ **Tunable** - Easy to adjust weights based on feedback  
✅ **Fast** - No LLM call needed for scoring  
✅ **Debuggable** - Can see exact score breakdown  
✅ **Testable** - Can write unit tests for priority logic  

---

## Future Enhancements

### Additional Signals (Potential)

| Signal | Points | How to Detect |
|--------|--------|---------------|
| Contains "URGENT" in subject | +1 | Keyword match |
| Multiple recipients | -1 | CC count > 3 |
| First email in thread | +1 | No in_reply_to |
| Long thread (>5 messages) | +1 | Thread length |
| Mentioned by name | +1 | User name in body |
| Has deadline keyword | +1 | "by", "before", "deadline" |

### Machine Learning (Phase 2)

Learn weights from user behavior:
- Which tasks do they complete first?
- Which tasks do they mark as done vs. snooze?
- Which senders are they quick to respond to?

Adjust weights automatically over time.

---

## Testing Priority Scoring

```python
from app.services.task_pipeline_service import get_task_pipeline_service

pipeline = get_task_pipeline_service()

# Test case 1: Urgent VIP email
candidate = {
    "title": "Send board deck",
    "action_type": "reply",
    "due_datetime": datetime.now() + timedelta(hours=6)
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

print(f"Priority: {priority}")  # NOW
print(f"Score: {score}")        # 9
print(f"Reason: {reason}")      # "Due in 6h + from Boss (VIP) + reply needed"
```

---

**Summary:** Simple, transparent, deterministic scoring that anyone can understand and tune. Perfect for MVP. 🎯
