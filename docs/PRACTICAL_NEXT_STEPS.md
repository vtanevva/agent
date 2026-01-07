# Practical Next Steps: Using Your Memory Layer

## Current State ✅

Your memory layer foundation is complete:
- ✅ All collections created (`tasks`, `projects`, `relationships`, `preferences`, `truth_ledger`)
- ✅ Data migrated (email todos → tasks, email styles → preferences)
- ✅ Code updated to use canonical namespaces
- ✅ Facts extraction working (emails, chat)

## What's Missing: Integration Points

### 1. Email Todos Still Writing to Old Collection ⚠️

**Current:** `app/tools/email/extract_todos.py` writes to `email_todos`  
**Should:** Write to `tasks` collection instead

### 2. No Relationship Tracking ⚠️

**Current:** Contacts exist but no relationship metadata  
**Should:** Track importance, frequency, last contact when processing emails

### 3. No Project Linking ⚠️

**Current:** Threads exist in isolation  
**Should:** Group related threads into projects

### 4. No Task Extraction from Chat ⚠️

**Current:** Chat extracts facts but not tasks  
**Should:** Extract actionable tasks from conversations

## Implementation Guide

### Step 1: Update Email Todos to Write to Tasks Collection

**File:** `app/tools/email/extract_todos.py`

**Change:** After extracting todos, write them to `tasks` collection instead of (or in addition to) `email_todos`.

```python
# After line 236 (after todos are extracted)
from app.memory.models import get_tasks_collection
from datetime import datetime
from uuid import uuid4

# ... existing code ...

# Store in tasks collection
tasks_col = get_tasks_collection()
if tasks_col:
    for todo_item in todos:
        todo_text = todo_item
        if isinstance(todo_item, dict):
            todo_text = todo_item.get("text", str(todo_item))
        
        task = {
            "_id": str(uuid4()),
            "user_id": user_id,
            "title": todo_text[:200],
            "description": todo_text if len(todo_text) > 200 else None,
            "status": "pending",
            "priority": "medium",
            "source": "email",
            "source_ref": thread_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        # Check if task already exists (deduplicate)
        existing = tasks_col.find_one({
            "user_id": user_id,
            "title": task["title"],
            "source_ref": thread_id,
            "status": {"$ne": "completed"}
        })
        
        if not existing:
            tasks_col.insert_one(task)
            logger.info(f"Created task from email: {task['title'][:50]}...")
```

### Step 2: Update Email Todos API to Read from Tasks

**File:** `app/services/gmail_service.py` (function `list_email_todos`)

**Change:** Query `tasks` collection with `source="email"` instead of `email_todos`.

```python
def list_email_todos(user_id: str, limit: int = 100) -> Dict[str, Any]:
    """
    List tasks extracted from emails.
    Now reads from unified tasks collection.
    """
    from app.memory.models import get_tasks_collection
    
    try:
        tasks_col = get_tasks_collection()
        if not tasks_col:
            return {"success": False, "error": "Tasks collection not available"}
        
        # Query tasks from email source
        cursor = (
            tasks_col.find({
                "user_id": user_id,
                "source": "email"
            })
            .sort("created_at", -1)
            .limit(max(1, min(int(limit or 100), 500)))
        )
        
        items = []
        for task in cursor:
            items.append({
                "id": task.get("_id"),
                "text": task.get("title"),
                "thread_id": task.get("source_ref"),
                "status": task.get("status", "pending"),
                "priority": task.get("priority", "medium"),
                "created_at": task.get("created_at"),
                "extracted_at": task.get("created_at"),  # For backward compatibility
            })
        
        return {
            "success": True,
            "items": items,
            "count": len(items)
        }
    except Exception as e:
        logger.error(f"Failed to list email tasks: {e}")
        return {"success": False, "error": str(e)}
```

### Step 3: Extract Relationships from Emails

**File:** `app/services/gmail_service.py` (function `extract_facts_from_email`)

**Add:** After fact extraction, update relationship metadata.

```python
# After fact extraction (around line 123)
from app.memory.models import get_relationships_collection
from datetime import datetime

# Update relationship metadata
relationships_col = get_relationships_collection()
if relationships_col and sender:
    # Extract email from sender string
    sender_email = sender
    if "<" in sender and ">" in sender:
        sender_email = sender.split("<")[1].split(">")[0]
    elif "@" in sender:
        sender_email = sender.strip()
    
    if "@" in sender_email:
        # Update or create relationship
        relationships_col.update_one(
            {
                "user_id": user_id,
                "contact_email": sender_email
            },
            {
                "$set": {
                    "last_contact": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                },
                "$inc": {
                    "contact_count": 1  # Track interaction frequency
                },
                "$setOnInsert": {
                    "_id": str(uuid4()),
                    "user_id": user_id,
                    "contact_email": sender_email,
                    "importance": "medium",  # Default
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )
```

### Step 4: Extract Tasks from Chat

**File:** `app/api/chat_routes.py` (after line 242, after fact ingestion)

**Add:** Extract tasks from user messages.

```python
# After fact ingestion
try:
    from app.memory.models import get_tasks_collection
    from app.services.llm_service import get_llm_service
    import json
    
    # Check if message contains task-like language
    task_keywords = ["todo", "task", "remind me", "need to", "should", "must", "have to"]
    if any(keyword in user_message.lower() for keyword in task_keywords):
        # Extract task using LLM
        llm_service = get_llm_service()
        task_prompt = f"""Extract any actionable tasks from this message. Return JSON:
{{
    "tasks": [
        {{"title": "Task description", "priority": "high|medium|low"}}
    ]
}}

Message: {user_message}

If no clear task, return {{"tasks": []}}"""

        try:
            task_response = llm_service.chat_completion_text(
                messages=[
                    {"role": "system", "content": "Extract tasks from messages. Return only JSON."},
                    {"role": "user", "content": task_prompt}
                ],
                temperature=0.1
            )
            
            task_data = json.loads(task_response)
            tasks_col = get_tasks_collection()
            
            if tasks_col and task_data.get("tasks"):
                for task_item in task_data["tasks"]:
                    task = {
                        "_id": str(uuid4()),
                        "user_id": user_id,
                        "title": task_item.get("title", "")[:200],
                        "status": "pending",
                        "priority": task_item.get("priority", "medium"),
                        "source": "chat",
                        "source_ref": session_id,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                    
                    # Deduplicate
                    existing = tasks_col.find_one({
                        "user_id": user_id,
                        "title": task["title"],
                        "status": {"$ne": "completed"}
                    })
                    
                    if not existing:
                        tasks_col.insert_one(task)
                        logger.info(f"Created task from chat: {task['title'][:50]}...")
        except Exception as e:
            logger.warning(f"Task extraction from chat failed: {e}")
except Exception as e:
    logger.warning(f"Task extraction setup failed: {e}")
```

### Step 5: Link Threads to Projects

**File:** `app/services/gmail_service.py` (function `extract_facts_from_email`)

**Add:** Check if thread relates to existing project, or create new one.

```python
# After relationship update (around line 150)
from app.memory.models import get_projects_collection

# Check if thread relates to a project
projects_col = get_projects_collection()
if projects_col:
    thread_id = email_data.get('thread_id')
    subject = email_data.get('subject', '')
    
    # Check if thread already linked to project
    existing_project = projects_col.find_one({
        "user_id": user_id,
        "related_threads": thread_id
    })
    
    if not existing_project:
        # Check if subject suggests a project (contains keywords)
        project_keywords = ["project", "launch", "initiative", "campaign", "feature"]
        if any(keyword in subject.lower() for keyword in project_keywords):
            # Create or update project
            project_name = subject[:100]  # Use subject as project name
            
            projects_col.update_one(
                {
                    "user_id": user_id,
                    "name": project_name
                },
                {
                    "$addToSet": {"related_threads": thread_id},
                    "$set": {
                        "last_activity": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    },
                    "$setOnInsert": {
                        "_id": str(uuid4()),
                        "user_id": user_id,
                        "name": project_name,
                        "status": "active",
                        "created_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
```

### Step 6: Use Tasks in Chat Context

**File:** `app/agents/aivis_core_agent.py` (function `handle_chat`)

**Add:** Include pending tasks in context for better responses.

```python
# After context retrieval (around line 104)
from app.memory.models import get_tasks_collection

# Get pending tasks for context
tasks_col = get_tasks_collection()
if tasks_col:
    pending_tasks = list(tasks_col.find({
        "user_id": user_id,
        "status": "pending"
    }).sort("priority", -1).limit(5))
    
    if pending_tasks:
        tasks_context = "\n".join([
            f"- {task.get('title')} ({task.get('priority', 'medium')} priority)"
            for task in pending_tasks
        ])
        
        # Add to system prompt
        system_prompt += f"\n\nUser's pending tasks:\n{tasks_context}"
```

## Quick Wins (Start Here)

### 1. Update Email Todos → Tasks (30 min)

**Priority:** High  
**Impact:** Unifies task management

1. Update `app/tools/email/extract_todos.py` to write to `tasks`
2. Update `app/services/gmail_service.py` `list_email_todos` to read from `tasks`
3. Test by extracting todos from an email

### 2. Extract Tasks from Chat (1 hour)

**Priority:** Medium  
**Impact:** Captures tasks from conversations

1. Add task extraction to `app/api/chat_routes.py`
2. Test by sending a message like "Remind me to review the PR tomorrow"

### 3. Track Relationships (1 hour)

**Priority:** Medium  
**Impact:** Better contact management

1. Add relationship updates to `extract_facts_from_email`
2. Test by processing an email from a contact

## Testing Your Changes

### Test Email Todos → Tasks

```bash
# Extract todos from an email thread
curl -X POST http://localhost:10000/api/gmail/extract-todos \
  -H "Content-Type: application/json" \
  -d '{"user_id": "v", "thread_id": "YOUR_THREAD_ID"}'

# List tasks
curl -X POST http://localhost:10000/api/gmail/email-todos \
  -H "Content-Type: application/json" \
  -d '{"user_id": "v", "limit": 10}'
```

### Test Task Extraction from Chat

```bash
# Send a message with a task
curl -X POST http://localhost:10000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "v",
    "session_id": "test",
    "message": "Remind me to call John tomorrow about the project"
  }'

# Check tasks collection
python -c "
from app.memory.models import get_tasks_collection
col = get_tasks_collection()
tasks = list(col.find({'user_id': 'v', 'source': 'chat'}))
print(f'Found {len(tasks)} tasks from chat')
for t in tasks:
    print(f\"  - {t.get('title')}\")
"
```

### Test Relationship Tracking

```bash
# Process an email (this happens automatically when emails are fetched)
# Then check relationships
python -c "
from app.memory.models import get_relationships_collection
col = get_relationships_collection()
rels = list(col.find({'user_id': 'v'}).sort('last_contact', -1).limit(5))
print(f'Found {len(rels)} relationships')
for r in rels:
    print(f\"  - {r.get('contact_email')}: last contact {r.get('last_contact')}\")
"
```

## Monitoring

### Check What's Being Stored

```python
# Count tasks by source
from app.memory.models import get_tasks_collection
col = get_tasks_collection()
pipeline = [
    {"$match": {"user_id": "v"}},
    {"$group": {"_id": "$source", "count": {"$sum": 1}}}
]
sources = list(col.aggregate(pipeline))
print("Tasks by source:", sources)

# Count relationships
from app.memory.models import get_relationships_collection
rel_col = get_relationships_collection()
print(f"Total relationships: {rel_col.count_documents({'user_id': 'v'})}")

# Count projects
from app.memory.models import get_projects_collection
proj_col = get_projects_collection()
print(f"Total projects: {proj_col.count_documents({'user_id': 'v'})}")
```

## Next Features to Build

1. **Task Dashboard API**
   - List all tasks (all sources)
   - Filter by status, priority, source
   - Update task status
   - Set due dates

2. **Project Management API**
   - Create projects manually
   - Link threads to projects
   - Get project summaries
   - List projects with activity

3. **Relationship Insights API**
   - Get important contacts
   - Suggest follow-ups
   - Track interaction frequency
   - Link contacts to projects

4. **Memory Search API**
   - Search across facts, tasks, projects
   - Get unified context
   - Find related items

## Resources

- **Collection helpers:** `app/memory/models.py`
- **Fact extraction:** `app/memory/memory_gate.py`
- **Vector operations:** `app/memory/vector_store.py`
- **Usage guide:** `docs/BUILDING_ON_MEMORY_LAYER.md`

**Start with Step 1 (Email Todos → Tasks) - it's the quickest win!** 🚀

