# How to Integrate the Task Pipeline into Your System

## Quick Start (3 Steps)

### 1. Server Already Has It ✅

The task pipeline is **already integrated** into your server. When you run:

```bash
python server.py
```

These endpoints are now available:
- `POST /api/tasks/ingest` - Process unread emails into tasks
- `GET /api/tasks` - Get tasks (filterable by priority)
- `POST /api/tasks/:id/complete` - Mark task done
- `POST /api/tasks/process-email` - Process single email

---

### 2. Process Your Unread Emails

#### Option A: Process All Unread Emails (Recommended)

```bash
# This will:
# - Pull your last 20 unread Gmail threads
# - Extract tasks from each
# - Score and prioritize them
# - Return all created tasks

curl -X POST http://localhost:10000/api/tasks/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "YOUR_USER_ID",
    "max_emails": 20
  }'
```

**Response:**
```json
{
  "success": true,
  "emails_processed": 10,
  "calendar_events": 3,
  "tasks_created": 5,
  "task_ids": ["aivis_1", "aivis_2", ...]
}
```

#### Option B: Process Single Email

```bash
curl -X POST http://localhost:10000/api/tasks/process-email \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "YOUR_USER_ID",
    "email": {
      "message_id": "msg_123",
      "thread_id": "thread_123",
      "sender": "boss@company.com",
      "sender_name": "Boss",
      "subject": "URGENT: Board deck needed",
      "body": "Can you send the board deck by 5pm today?",
      "timestamp": "2026-01-28T09:00:00"
    }
  }'
```

---

### 3. Get Your Prioritized Tasks

```bash
# Get all tasks (sorted by priority)
curl "http://localhost:10000/api/tasks?user_id=YOUR_USER_ID"

# Get only urgent tasks (NOW)
curl "http://localhost:10000/api/tasks?user_id=YOUR_USER_ID&priority=NOW"

# Get important tasks (SOON)
curl "http://localhost:10000/api/tasks?user_id=YOUR_USER_ID&priority=SOON"
```

**Response:**
```json
{
  "success": true,
  "tasks": [
    {
      "_id": "aivis_abc123",
      "priority": "NOW",
      "priority_score": 9,
      "title": "Send board deck",
      "reason": "Due in 7h + from Boss (VIP) + reply needed",
      "due_datetime": "2026-01-28T17:00:00",
      "actions": ["draft_reply", "open_in_gmail", "mark_done"],
      "action_metadata": {
        "draft_reply": {
          "to": "boss@company.com",
          "thread_id": "thread_123"
        },
        "open_in_gmail": {
          "url": "https://mail.google.com/mail/u/0/#inbox/thread_123"
        }
      },
      "status": "pending"
    }
  ],
  "count": 1
}
```

---

## Integration with Existing System

### A. Auto-Process New Emails

Hook into your Gmail webhook/polling system:

```python
# In your existing Gmail processing code
from app.services.task_pipeline_service import get_task_pipeline_service

def on_new_email_received(user_id, email_data):
    """Called when new email arrives"""
    
    # Your existing email processing...
    # store_email(email_data)
    # classify_email(email_data)
    
    # NEW: Extract tasks from email
    pipeline = get_task_pipeline_service()
    task_id = pipeline.process_gmail_event(user_id, {
        "message_id": email_data["id"],
        "thread_id": email_data["threadId"],
        "sender": email_data["from"],
        "sender_name": extract_name(email_data["from"]),
        "subject": email_data["subject"],
        "snippet": email_data["snippet"],
        "body": email_data["body"],
        "timestamp": email_data["internalDate"]
    })
    
    if task_id:
        # Notify user about new task
        send_notification(user_id, f"New task: {task_id}")
```

### B. Add to Your Gmail Agent

Update `app/agents/gmail_agent.py`:

```python
from app.services.task_pipeline_service import get_task_pipeline_service

class GmailAgent:
    def __init__(self):
        # ... existing code ...
        self.task_pipeline = get_task_pipeline_service()
    
    def handle_inbox_check(self, user_id):
        """When user asks 'check my inbox'"""
        
        # Existing: Get emails
        emails = self.gmail_service.list_threads(user_id, max_results=20, query="is:unread")
        
        # NEW: Process into tasks
        result = self.task_pipeline.ingest_and_process(user_id, max_emails=20)
        
        # Get prioritized tasks
        now_tasks = self.task_pipeline.get_tasks_by_priority(user_id, priority="NOW")
        soon_tasks = self.task_pipeline.get_tasks_by_priority(user_id, priority="SOON")
        
        # Return to user
        response = f"You have {len(now_tasks)} urgent tasks:\n"
        for task in now_tasks:
            response += f"- {task['title']} ({task['reason']})\n"
        
        return response
```

### C. Mark VIP Contacts

For the scoring to work well, mark your important contacts as VIP:

```python
from app.memory.models import get_relationships_collection

def mark_contact_as_vip(user_id, email):
    """Mark a contact as VIP for priority scoring"""
    relationships_col = get_relationships_collection()
    
    relationships_col.update_one(
        {"user_id": user_id, "contact_email": email},
        {
            "$set": {
                "user_id": user_id,
                "contact_email": email,
                "importance": "high",  # <-- This makes them VIP
                "relationship_type": "colleague",
                "updated_at": datetime.utcnow()
            }
        },
        upsert=True
    )

# Mark your boss as VIP
mark_contact_as_vip("your_user_id", "boss@company.com")

# Mark key clients as VIP
mark_contact_as_vip("your_user_id", "bigclient@corp.com")
```

---

## Frontend Integration

### Display Tasks in Your UI

```javascript
// Fetch tasks from API
async function getTasks(userId, priority = null) {
  const url = priority 
    ? `/api/tasks?user_id=${userId}&priority=${priority}`
    : `/api/tasks?user_id=${userId}`;
  
  const response = await fetch(url);
  const data = await response.json();
  return data.tasks;
}

// Display tasks grouped by priority
async function displayTasks(userId) {
  const nowTasks = await getTasks(userId, 'NOW');
  const soonTasks = await getTasks(userId, 'SOON');
  const laterTasks = await getTasks(userId, 'LATER');
  
  // Render NOW tasks (red, urgent)
  renderTaskGroup('NOW', nowTasks, '🔴');
  
  // Render SOON tasks (yellow, important)
  renderTaskGroup('SOON', soonTasks, '🟡');
  
  // Render LATER tasks (white, low priority)
  renderTaskGroup('LATER', laterTasks, '⚪');
}

function renderTaskGroup(priority, tasks, emoji) {
  const container = document.getElementById(`${priority}-tasks`);
  
  tasks.forEach(task => {
    const taskCard = `
      <div class="task-card">
        <div class="task-header">
          <span class="priority-badge">${emoji} ${priority}</span>
          <span class="score">Score: ${task.priority_score}</span>
        </div>
        
        <h3>${task.title}</h3>
        <p class="reason">${task.reason}</p>
        
        ${task.due_datetime ? `<p class="due">⏰ ${formatDate(task.due_datetime)}</p>` : ''}
        
        <div class="actions">
          ${task.actions.map(action => `
            <button onclick="handleAction('${task._id}', '${action}')">
              ${getActionLabel(action)}
            </button>
          `).join('')}
        </div>
      </div>
    `;
    
    container.innerHTML += taskCard;
  });
}

// Handle task actions
async function handleAction(taskId, action) {
  if (action === 'mark_done') {
    await fetch(`/api/tasks/${taskId}/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUserId })
    });
    // Refresh tasks
    displayTasks(currentUserId);
  } else if (action === 'open_in_gmail') {
    // Open Gmail thread
    const task = await getTask(taskId);
    window.open(task.action_metadata.open_in_gmail.url, '_blank');
  } else if (action === 'draft_reply') {
    // Show reply composer
    showReplyComposer(taskId);
  }
}
```

### Example UI Layout

```html
<div class="tasks-dashboard">
  <h1>Your Tasks</h1>
  
  <section class="priority-section">
    <h2>🔴 NOW (Urgent)</h2>
    <div id="NOW-tasks"></div>
  </section>
  
  <section class="priority-section">
    <h2>🟡 SOON (Important)</h2>
    <div id="SOON-tasks"></div>
  </section>
  
  <section class="priority-section">
    <h2>⚪ LATER (Low Priority)</h2>
    <div id="LATER-tasks"></div>
  </section>
</div>
```

---

## Scheduled Processing

Set up a cron job or background task to process emails periodically:

```python
# Add to your background jobs
from app.services.task_pipeline_service import get_task_pipeline_service

def process_emails_for_all_users():
    """Run every 15 minutes"""
    users = get_all_users()
    pipeline = get_task_pipeline_service()
    
    for user in users:
        try:
            # Process unread emails
            result = pipeline.ingest_and_process(user['_id'], max_emails=20)
            
            # Get urgent tasks
            now_tasks = pipeline.get_tasks_by_priority(user['_id'], priority='NOW')
            
            # Send notification if there are urgent tasks
            if now_tasks:
                send_push_notification(user['_id'], 
                    f"You have {len(now_tasks)} urgent tasks!")
        except Exception as e:
            logger.error(f"Failed to process tasks for user {user['_id']}: {e}")

# Add to scheduler
scheduler.add_job(process_emails_for_all_users, 'interval', minutes=15)
```

---

## Chat Integration

Add task commands to your chat agent:

```python
# In app/agents/aivis_core_agent.py

def handle_task_queries(self, user_id, message):
    """Handle task-related questions"""
    pipeline = get_task_pipeline_service()
    
    # "What's urgent?"
    if "urgent" in message.lower() or "important" in message.lower():
        now_tasks = pipeline.get_tasks_by_priority(user_id, priority="NOW")
        
        if not now_tasks:
            return "You have no urgent tasks right now! 🎉"
        
        response = f"You have {len(now_tasks)} urgent tasks:\n\n"
        for task in now_tasks:
            response += f"🔴 {task['title']}\n"
            response += f"   {task['reason']}\n\n"
        
        return response
    
    # "What should I do next?"
    elif "what should i do" in message.lower() or "next" in message.lower():
        all_tasks = pipeline.get_tasks_by_priority(user_id, limit=5)
        
        if not all_tasks:
            return "You're all caught up! No pending tasks."
        
        top_task = all_tasks[0]
        
        return f"I'd recommend: {top_task['title']}\n\n" + \
               f"Why: {top_task['reason']}\n" + \
               f"Priority: {top_task['priority']} (score: {top_task['priority_score']})"
    
    # "Process my emails"
    elif "process" in message.lower() and "email" in message.lower():
        result = pipeline.ingest_and_process(user_id, max_emails=20)
        
        return f"Processed {result['emails_processed']} emails and created " + \
               f"{result['tasks_created']} tasks."
```

---

## Testing Your Integration

### 1. Test with Demo Script

```bash
python examples/task_pipeline_demo.py
```

### 2. Test API Endpoints

```bash
# Start server
python server.py

# In another terminal:

# Process your unread emails
curl -X POST http://localhost:10000/api/tasks/ingest \
  -H "Content-Type: application/json" \
  -d '{"user_id": "YOUR_USER_ID", "max_emails": 10}'

# Get your tasks
curl "http://localhost:10000/api/tasks?user_id=YOUR_USER_ID"
```

### 3. Test VIP Scoring

```python
# Mark someone as VIP
from app.memory.models import get_relationships_collection
from datetime import datetime

relationships_col = get_relationships_collection()
relationships_col.update_one(
    {"user_id": "YOUR_USER_ID", "contact_email": "boss@company.com"},
    {
        "$set": {
            "user_id": "YOUR_USER_ID",
            "contact_email": "boss@company.com",
            "importance": "high",
            "relationship_type": "colleague",
            "updated_at": datetime.utcnow()
        }
    },
    upsert=True
)

# Now process an email from that person - it should get +3 score
```

---

## Summary

**Your task pipeline is ready to use!**

### Quick Integration Checklist:

- ✅ **Already integrated** - Server has the endpoints
- ✅ **Mark VIP contacts** - Add +3 score boost
- ✅ **Call `/api/tasks/ingest`** - Process unread emails
- ✅ **Call `/api/tasks`** - Get prioritized tasks
- ✅ **Display in UI** - Show NOW/SOON/LATER tasks
- ✅ **Add to chat** - "What's urgent?"
- ✅ **Scheduled job** - Process emails every 15 min

**Start now:** Run `python server.py` and hit the `/api/tasks/ingest` endpoint!
