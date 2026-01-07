# New Memory Collections - Quick Reference

## Overview

Five new collections have been created to complete the memory architecture:

1. **`preferences`** - User settings and preferences
2. **`projects`** - Project capsules (multi-message context)
3. **`tasks`** - Unified task management (all sources)
4. **`truth_ledger`** - Fact versioning and contradictions
5. **`relationships`** - Enhanced contact relationship metadata

## Usage Examples

### 1. Preferences Collection

**Purpose:** Store user preferences and canonical namespace

```python
from app.memory.models import get_preferences_collection
from datetime import datetime
from uuid import uuid4

prefs_col = get_preferences_collection()

# Create/update preferences
prefs_col.update_one(
    {"user_id": "v"},
    {
        "$set": {
            "memory_namespace": "u:695d8f9c2cc24510999d4dc3",
            "primary_email": "vanesa.taneva@gmail.com",
            "timezone": "UTC",
            "language": "en",
            "updated_at": datetime.utcnow()
        },
        "$setOnInsert": {
            "_id": str(uuid4()),
            "user_id": "v",
            "created_at": datetime.utcnow()
        }
    },
    upsert=True
)

# Get preferences
prefs = prefs_col.find_one({"user_id": "v"})
canonical_namespace = prefs.get("memory_namespace")
```

### 2. Projects Collection

**Purpose:** Track projects with related context

```python
from app.memory.models import get_projects_collection
from datetime import datetime
from uuid import uuid4

projects_col = get_projects_collection()

# Create a project
project = {
    "_id": str(uuid4()),
    "user_id": "v",
    "name": "Q1 Product Launch",
    "description": "Launch new product features",
    "status": "active",
    "related_contacts": ["john@example.com"],
    "related_threads": ["thread_123"],
    "summary": "Working on product launch...",
    "key_facts": ["Launch date: March 1", "Team: 5 people"],
    "created_at": datetime.utcnow(),
    "updated_at": datetime.utcnow(),
    "last_activity": datetime.utcnow()
}
projects_col.insert_one(project)

# Get active projects
active_projects = list(projects_col.find({
    "user_id": "v",
    "status": "active"
}).sort("updated_at", -1))
```

### 3. Tasks Collection

**Purpose:** Unified task management from all sources

```python
from app.memory.models import get_tasks_collection
from datetime import datetime, timedelta
from uuid import uuid4

tasks_col = get_tasks_collection()

# Create a task
task = {
    "_id": str(uuid4()),
    "user_id": "v",
    "title": "Review PR #123",
    "description": "Review the new feature PR",
    "status": "pending",
    "priority": "high",
    "source": "email",  # or "chat", "calendar", "manual"
    "source_ref": "thread_456",
    "due_date": datetime.utcnow() + timedelta(days=2),
    "created_at": datetime.utcnow(),
    "updated_at": datetime.utcnow()
}
tasks_col.insert_one(task)

# Get pending tasks
pending_tasks = list(tasks_col.find({
    "user_id": "v",
    "status": "pending"
}).sort("due_date", 1))

# Complete a task
tasks_col.update_one(
    {"_id": task_id},
    {
        "$set": {
            "status": "completed",
            "completed_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
    }
)
```

### 4. Truth Ledger Collection

**Purpose:** Track fact changes and handle contradictions

```python
from app.memory.models import get_truth_ledger_collection
from datetime import datetime
from uuid import uuid4

truth_col = get_truth_ledger_collection()

# Log a fact change
ledger_entry = {
    "_id": str(uuid4()),
    "user_id": "v",
    "fact_id": "fact_123",
    "version": 2,
    "previous_value": "User works at Company A",
    "new_value": "User works at Company B",
    "reason": "contradiction",  # or "update", "refinement"
    "confidence_change": -0.2,  # Confidence decreased
    "evidence_ref": "email_thread_789",
    "changed_at": datetime.utcnow()
}
truth_col.insert_one(ledger_entry)

# Get fact history
fact_history = list(truth_col.find({
    "user_id": "v",
    "fact_id": "fact_123"
}).sort("version", 1))
```

### 5. Relationships Collection

**Purpose:** Enhanced contact relationship tracking

```python
from app.memory.models import get_relationships_collection
from datetime import datetime
from uuid import uuid4

relationships_col = get_relationships_collection()

# Create/update relationship
relationships_col.update_one(
    {
        "user_id": "v",
        "contact_email": "john@example.com"
    },
    {
        "$set": {
            "importance": "high",
            "relationship_type": "colleague",
            "last_contact": datetime.utcnow(),
            "contact_frequency": 15,  # messages per month
            "notes": ["Works on same project", "Key stakeholder"],
            "projects": ["project_123"],
            "updated_at": datetime.utcnow()
        },
        "$setOnInsert": {
            "_id": str(uuid4()),
            "user_id": "v",
            "contact_email": "john@example.com",
            "created_at": datetime.utcnow()
        }
    },
    upsert=True
)

# Get important relationships
important_contacts = list(relationships_col.find({
    "user_id": "v",
    "importance": "high"
}).sort("last_contact", -1))
```

## Migration from Existing Collections

### Email Todos → Tasks

```python
from app.database import get_db
from app.memory.models import get_tasks_collection
from datetime import datetime

db = get_db()
email_todos_col = db.db["email_todos"]
tasks_col = get_tasks_collection()

# Migrate email todos to tasks
for todo_doc in email_todos_col.find({}):
    task = {
        "_id": todo_doc["_id"],
        "user_id": todo_doc["user_id"],
        "title": todo_doc.get("title", "Email task"),
        "description": todo_doc.get("description"),
        "status": "pending",
        "priority": "medium",
        "source": "email",
        "source_ref": todo_doc.get("thread_id"),
        "created_at": todo_doc.get("extracted_at", datetime.utcnow()),
        "updated_at": datetime.utcnow()
    }
    tasks_col.insert_one(task)
```

### Contacts → Relationships

```python
from app.database import get_db
from app.memory.models import get_relationships_collection
from app.db.collections import get_contacts_collection

contacts_col = get_contacts_collection()
relationships_col = get_relationships_collection()

# Enhance contacts with relationship data
for contact in contacts_col.find({}):
    # Calculate importance based on interaction frequency
    # (you'd need to query emails/messages for this)
    
    relationships_col.update_one(
        {
            "user_id": contact["user_id"],
            "contact_email": contact["email"]
        },
        {
            "$set": {
                "relationship_type": "colleague",  # or infer from data
                "importance": "medium",  # calculate from frequency
                "updated_at": datetime.utcnow()
            },
            "$setOnInsert": {
                "_id": str(uuid4()),
                "user_id": contact["user_id"],
                "contact_email": contact["email"],
                "created_at": datetime.utcnow()
            }
        },
        upsert=True
    )
```

## Integration Points

### When to Use Each Collection

- **preferences**: User settings, canonical namespace lookup
- **projects**: Multi-thread/multi-message context grouping
- **tasks**: Any actionable item (from email, chat, calendar, manual)
- **truth_ledger**: When a fact changes or contradicts
- **relationships**: When you need relationship metadata beyond basic contact info

### Common Patterns

1. **Creating a task from email:**
   ```python
   # Extract todo from email → create in tasks collection
   ```

2. **Tracking fact changes:**
   ```python
   # When memory_fact is updated → log to truth_ledger
   ```

3. **Grouping threads into projects:**
   ```python
   # Multiple email threads → one project capsule
   ```

4. **Enhancing contacts:**
   ```python
   # When contact interacts → update relationships.last_contact
   ```

## Next Steps

1. ✅ Collections created
2. ✅ Helper functions added to `app/memory/models.py`
3. ⏳ Start using in your code
4. ⏳ Migrate existing data (optional)
5. ⏳ Build UI/APIs for these collections

