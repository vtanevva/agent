# Building on the Memory Layer

## Current Foundation ✅

You now have:
- ✅ All collections created and ready
- ✅ Canonical namespaces in place
- ✅ Data migrated and organized
- ✅ Helper functions available
- ✅ Schemas defined

## How to Use the Memory Layer

### 1. Storing Facts (Memory Facts Collection)

**When to use:** Extract and store user facts from conversations, emails, etc.

```python
from app.memory.models import get_memory_facts_collection
from app.memory.memory_gate import get_memory_gate
from datetime import datetime
from uuid import uuid4

# Extract facts from text
memory_gate = get_memory_gate()
candidates = memory_gate.extract_candidate_facts(
    text="I work as a Data Scientist at Belmond",
    user_id="v",
    source_ref="message_123"
)

# Store validated facts
stored_count = memory_gate.store_facts("v", candidates)

# Facts are automatically:
# - Stored in MongoDB (memory_facts collection)
# - Embedded and stored in Pinecone (canonical namespace)
# - Ready for retrieval
```

### 2. Creating Tasks (Tasks Collection)

**When to use:** Any actionable item from any source (email, chat, calendar, manual)

```python
from app.memory.models import get_tasks_collection
from datetime import datetime, timedelta
from uuid import uuid4

tasks_col = get_tasks_collection()

# Create task from email
task = {
    "_id": str(uuid4()),
    "user_id": "v",
    "title": "Review PR #123",
    "description": "Review the new feature implementation",
    "status": "pending",
    "priority": "high",
    "source": "email",
    "source_ref": "thread_456",
    "due_date": datetime.utcnow() + timedelta(days=2),
    "created_at": datetime.utcnow(),
    "updated_at": datetime.utcnow()
}
tasks_col.insert_one(task)

# Query pending tasks
pending = list(tasks_col.find({
    "user_id": "v",
    "status": "pending"
}).sort("due_date", 1))
```

### 3. Managing Projects (Projects Collection)

**When to use:** Group related threads/emails/conversations into projects

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
    "related_threads": ["thread_123", "thread_456"],
    "summary": "Working on product launch with team...",
    "key_facts": ["Launch date: March 1", "Team: 5 people"],
    "created_at": datetime.utcnow(),
    "updated_at": datetime.utcnow(),
    "last_activity": datetime.utcnow()
}
projects_col.insert_one(project)

# Link new thread to project
projects_col.update_one(
    {"_id": project_id},
    {
        "$addToSet": {"related_threads": "thread_789"},
        "$set": {
            "last_activity": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
    }
)
```

### 4. Tracking Relationships (Relationships Collection)

**When to use:** Enhance contact information with relationship metadata

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
important = list(relationships_col.find({
    "user_id": "v",
    "importance": "high"
}).sort("last_contact", -1))
```

### 5. Versioning Facts (Truth Ledger)

**When to use:** Track when facts change or contradict

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
    "confidence_change": -0.2,
    "evidence_ref": "email_thread_789",
    "changed_at": datetime.utcnow()
}
truth_col.insert_one(ledger_entry)

# Get fact history
history = list(truth_col.find({
    "user_id": "v",
    "fact_id": "fact_123"
}).sort("version", 1))
```

### 6. Retrieving Memory (Vector Search)

**When to use:** Find relevant memories for context

```python
from app.memory.vector_store import get_vector_store
from app.memory.retrieval_service import RetrievalService

# Search for relevant facts
vector_store = get_vector_store()
matches = vector_store.search(
    user_id="v",
    query_text="What does the user work on?",
    top_k=10,
    vector_type="fact"
)

# Or use retrieval service
retrieval = RetrievalService()
relevant_facts = retrieval.get_relevant_facts(
    user_id="v",
    query="work projects",
    limit=5
)
```

## Integration Points

### 1. Email Processing

**Enhance email processing to extract and store:**

```python
# In your email processing code
from app.memory.memory_gate import get_memory_gate
from app.memory.models import get_tasks_collection

# Extract facts from email
memory_gate = get_memory_gate()
facts = memory_gate.extract_candidate_facts(
    text=email_body,
    user_id=user_id,
    source_ref=f"email_{email_id}"
)
memory_gate.store_facts(user_id, facts)

# Extract tasks from email
# (your existing email_todos logic, but save to tasks collection)
tasks_col = get_tasks_collection()
# ... create task documents
```

### 2. Chat Conversations

**Enhance chat to use memory:**

```python
# In your chat endpoint
from app.memory.retrieval_service import RetrievalService

# Get relevant context before responding
retrieval = RetrievalService()
context = retrieval.get_relevant_facts(
    user_id=user_id,
    query=user_message,
    limit=5
)

# Use context in LLM prompt
prompt = f"""
User context:
{chr(10).join([f"- {fact}" for fact in context])}

User message: {user_message}
"""

# After response, extract new facts
memory_gate = get_memory_gate()
new_facts = memory_gate.extract_candidate_facts(
    text=f"{user_message} {bot_response}",
    user_id=user_id,
    source_ref=f"chat_{session_id}"
)
memory_gate.store_facts(user_id, new_facts)
```

### 3. Calendar Events

**Link calendar to projects and tasks:**

```python
# When creating calendar event
from app.memory.models import get_projects_collection

# Check if event relates to a project
projects_col = get_projects_collection()
related_project = projects_col.find_one({
    "user_id": user_id,
    "related_contacts": {"$in": [attendee_email]},
    "status": "active"
})

if related_project:
    # Link event to project
    # Update project last_activity
    pass
```

## Building Features

### Feature 1: Smart Task Management

**Use tasks collection to build:**
- Task dashboard
- Priority-based sorting
- Source tracking (email vs chat vs manual)
- Due date reminders
- Project-linked tasks

### Feature 2: Project Context

**Use projects collection to:**
- Group related conversations
- Track project progress
- Link contacts to projects
- Generate project summaries
- Cross-reference related threads

### Feature 3: Relationship Intelligence

**Use relationships collection to:**
- Prioritize important contacts
- Track interaction frequency
- Suggest follow-ups
- Link contacts to projects
- Personalize communication style

### Feature 4: Fact Versioning

**Use truth_ledger to:**
- Handle contradictions
- Track fact evolution
- Maintain confidence scores
- Provide fact history
- Resolve conflicts

## Best Practices

### 1. Always Use Helper Functions

```python
# ✅ Good
from app.memory.models import get_tasks_collection
tasks_col = get_tasks_collection()

# ❌ Bad
from app.database import get_db
tasks_col = get_db().db["tasks"]  # Direct access
```

### 2. Store Vector IDs for Future Migrations

```python
# When creating facts, store vector_id
fact_doc = {
    "_id": fact_id,
    "vector_id": vector_id,  # Store this!
    "user_id": user_id,
    "text": fact_text,
    ...
}
```

### 3. Use Canonical Namespaces

```python
# ✅ Good - uses canonical namespace
vector_store.upsert_vectors(user_id="v", ...)

# The code automatically:
# 1. Gets canonical namespace from users.memory_namespace
# 2. Falls back to email if needed
# 3. Falls back to user_id as last resort
```

### 4. Track Fact Validity

```python
# When fact changes
fact_doc["valid_to"] = datetime.utcnow()  # Mark old fact as invalid
fact_doc["is_active"] = False

# Create new fact
new_fact = {
    "valid_from": datetime.utcnow(),
    "valid_to": None,  # Still valid
    "is_active": True,
    ...
}

# Log to truth_ledger
truth_col.insert_one({
    "fact_id": old_fact_id,
    "previous_value": old_text,
    "new_value": new_text,
    "reason": "contradiction",
    ...
})
```

## Example: Complete Memory Flow

```python
# 1. User sends message
user_message = "I'm starting a new project at work"

# 2. Retrieve relevant context
retrieval = RetrievalService()
context = retrieval.get_relevant_facts(user_id, user_message, limit=5)

# 3. Generate response with context
response = llm.generate_response(user_message, context=context)

# 4. Extract new facts
memory_gate = get_memory_gate()
facts = memory_gate.extract_candidate_facts(
    text=f"{user_message} {response}",
    user_id=user_id,
    source_ref=f"chat_{session_id}"
)

# 5. Store facts
memory_gate.store_facts(user_id, facts)

# 6. Check if this relates to a project
projects_col = get_projects_collection()
if "project" in user_message.lower():
    # Create or update project
    pass

# 7. Extract tasks if any
if "todo" in user_message.lower() or "task" in user_message.lower():
    tasks_col = get_tasks_collection()
    # Create task
    pass
```

## Next Steps

1. **Start using in your code:**
   - Update email processing to use `tasks` collection
   - Update chat to retrieve and store facts
   - Link calendar events to projects

2. **Build UI/APIs:**
   - Task management interface
   - Project dashboard
   - Relationship insights

3. **Enhance existing features:**
   - Add memory context to responses
   - Track relationship importance
   - Version facts when they change

4. **Monitor and iterate:**
   - Check what's being stored
   - Verify retrieval quality
   - Adjust extraction logic

## Resources

- **Helper functions:** `app/memory/models.py`
- **Fact extraction:** `app/memory/memory_gate.py`
- **Vector operations:** `app/memory/vector_store.py`
- **Retrieval:** `app/memory/retrieval_service.py`
- **Usage examples:** `docs/NEW_COLLECTIONS_GUIDE.md`

**You're ready to build! The foundation is solid.** 🚀

