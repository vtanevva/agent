# Memory Architecture

## Current State Analysis

### MongoDB Collections

#### ✅ Existing Collections (Good Foundation)

1. **`emails`** - Raw email data from Gmail
   - Purpose: Source of truth for email content
   - Has: `user_id`, email content, metadata
   - Usage: Email triage, fact extraction

2. **`contacts`** - User's contact relationships
   - Purpose: Contact information and relationships
   - Has: `user_id`, name, email, notes, metadata
   - Usage: Email addressing, relationship tracking

3. **`calendar_events`** - Calendar entries
   - Purpose: Schedule and time-based context
   - Has: `user_id`, event details, timestamps
   - Usage: Scheduling, context awareness

4. **`email_todos`** - Tasks extracted from emails
   - Purpose: Action items from email threads
   - Has: `user_id`, `thread_id`, todos
   - Usage: Task management (email-only)

5. **`memory_facts`** - Distilled user facts
   - Purpose: Long-term facts about the user
   - Has: `user_id`, text, type, confidence, source_ref
   - Usage: User awareness, personalization

6. **`thread_summaries`** - Email thread capsules
   - Purpose: Condensed thread context
   - Has: `user_id`, `thread_id`, summary
   - Usage: Quick thread context (only 1 doc currently)

7. **`conversations`** - Chat conversations
   - Purpose: Chat history with bot
   - Has: `user_id`, `session_id`, messages array
   - Usage: Conversation continuity

8. **`messages`** - Individual messages
   - Purpose: Granular message storage
   - Has: `user_id`, `thread_id`, text, timestamp
   - Usage: Fine-grained memory access

9. **`tokens`** - OAuth tokens
   - Purpose: API access credentials
   - Has: `user_id`, google/microsoft tokens
   - Usage: Third-party API access

10. **`users`** - User accounts
    - Purpose: User identity and metadata
    - Has: `_id`, `user_id`, classification flags
    - Usage: User management

11. **`cache`** - Temporary data cache
    - Purpose: Performance optimization
    - Has: Various cached data
    - Usage: Reducing API calls

12. **`documents`** - Uploaded documents
    - Purpose: User-uploaded files
    - Has: `user_id`, metadata
    - Usage: File-based memory (empty currently)

13. **`document_chunks`** - Document text chunks
    - Purpose: Chunked document content for RAG
    - Has: `user_id`, `doc_id`, chunks
    - Usage: Document search (empty currently)

14. **`waitlist`** - User waitlist
    - Purpose: Feature access control
    - Has: User email, status
    - Usage: Beta access management

#### ❌ Missing Collections (Should Add)

1. **`preferences`** - User preferences and settings
   - Purpose: Stable user defaults
   - Schema:
     ```python
     {
       "_id": str,
       "user_id": str,
       "memory_namespace": str,  # Canonical namespace for Pinecone
       "primary_email": str,
       "timezone": str,
       "language": str,
       "notification_settings": dict,
       "ai_personality": dict,
       "created_at": datetime,
       "updated_at": datetime
     }
     ```

2. **`projects`** - Project capsules
   - Purpose: Multi-message context per project
   - Schema:
     ```python
     {
       "_id": str,  # project_id
       "user_id": str,
       "name": str,
       "description": str,
       "status": str,  # active, archived, completed
       "related_contacts": list,
       "related_threads": list,
       "summary": str,
       "key_facts": list,
       "created_at": datetime,
       "updated_at": datetime,
       "last_activity": datetime
     }
     ```

3. **`tasks`** - Unified task management
   - Purpose: Consolidate tasks from all sources
   - Schema:
     ```python
     {
       "_id": str,  # task_id
       "user_id": str,
       "title": str,
       "description": str,
       "status": str,  # pending, in_progress, completed, cancelled
       "priority": str,  # low, medium, high, urgent
       "source": str,  # email, chat, calendar, manual
       "source_ref": str,  # thread_id, message_id, etc.
       "due_date": datetime,
       "completed_at": datetime,
       "created_at": datetime,
       "updated_at": datetime
     }
     ```

4. **`truth_ledger`** - Fact versioning and contradictions
   - Purpose: Track fact evolution and handle contradictions
   - Schema:
     ```python
     {
       "_id": str,
       "user_id": str,
       "fact_id": str,  # Links to memory_facts
       "version": int,
       "previous_value": str,
       "new_value": str,
       "reason": str,  # "contradiction", "update", "refinement"
       "confidence_change": float,
       "evidence_ref": str,
       "changed_at": datetime
     }
     ```

5. **`relationships`** - Enhanced contact relationships
   - Purpose: Track relationship metadata
   - Schema:
     ```python
     {
       "_id": str,
       "user_id": str,
       "contact_email": str,
       "importance": str,  # high, medium, low
       "relationship_type": str,  # colleague, friend, family, client
       "last_contact": datetime,
       "contact_frequency": int,  # messages per month
       "notes": list,  # Important notes about this person
       "projects": list,  # Shared projects
       "created_at": datetime,
       "updated_at": datetime
     }
     ```

### Pinecone Namespaces

#### 🔴 Current Issues

1. **Inconsistent namespace formats:**
   - Usernames: `v`, `vane`, `vanesa`, `mitko`
   - Emails: `vanesa.taneva@gmail.com`, `vanesa.taneva12@gmail.com`
   - Test users: `test-user-20260106201700`
   - Anonymous: `(empty)`, `default`

2. **Split user memories:**
   - Same user has vectors across multiple namespaces
   - Example: User "vanesa" has vectors in:
     - `v` (332 vectors)
     - `vane` (84 vectors)
     - `vanesa` (5 vectors)
     - `vanesa.taneva@gmail.com` (54 vectors)
   - Total: 475 vectors fragmented across 4 namespaces

3. **Retrieval problems:**
   - Queries only search one namespace at a time
   - Missing relevant memories from other namespaces
   - Inconsistent user experience

#### ✅ Recommended Solution

**Use canonical namespace format: `u:<userId>`**

Benefits:
- Stable: Doesn't change if email/username changes
- Unique: One namespace per user
- Scalable: Can add sub-types in metadata

**Namespace structure:**
```
namespace: u:695d8f9c2cc24510999d4dc3
metadata: {
  "user_id": "v",  # Original username
  "source_type": "email" | "chat" | "file" | "memory",
  "vector_type": "fact" | "summary" | "doc_chunk",
  "created_at": "2026-01-07T10:00:00Z"
}
```

Alternative if sub-namespaces are needed:
```
u:695d8f9c2cc24510999d4dc3:emails
u:695d8f9c2cc24510999d4dc3:files
u:695d8f9c2cc24510999d4dc3:memories
```

## Migration Plan

### Phase 1: Add Memory Profile to Users (Week 1)

1. **Update `users` collection schema:**
   ```python
   {
     "_id": ObjectId,  # MongoDB internal ID
     "user_id": str,  # Login username (keep for backward compat)
     "memory_namespace": str,  # NEW: Canonical Pinecone namespace
     "primary_email": str,  # NEW: User's primary email
     "workspace_id": str,  # NEW: For future multi-tenant support
     # ... existing fields ...
   }
   ```

2. **Backfill existing users:**
   - Script: `scripts/backfill_user_profiles.py`
   - For each user in `users`:
     - Set `memory_namespace = f"u:{_id}"`
     - Get email from tokens/credentials
     - Set `primary_email`

### Phase 2: Create Missing Collections (Week 1-2)

1. **Create `preferences` collection**
   - Migration: Extract preferences from existing data
   - Default values for existing users

2. **Create `tasks` collection**
   - Migration: Copy from `email_todos`
   - Add `source="email"`

3. **Create `projects` collection**
   - Start empty, build organically

4. **Create `truth_ledger` collection**
   - Start empty, track future changes

5. **Create `relationships` collection**
   - Migration: Enhance from `contacts`
   - Calculate importance/frequency from `emails`

### Phase 3: Migrate Pinecone Namespaces (Week 2-3)

**CRITICAL: Copy first, verify, then delete**

1. **Create migration script: `scripts/migrate_pinecone_namespaces.py`**

2. **Steps:**
   ```
   For each old namespace:
     1. Identify which user it belongs to
     2. Get canonical namespace from users.memory_namespace
     3. Query all vectors from old namespace
     4. Upsert to new namespace
     5. Verify vector counts match
     6. Log migration
     7. (Optional) Delete old namespace after verification
   ```

3. **User mapping:**
   ```python
   # Map old namespaces to users
   namespace_map = {
     "v": "u:695d8f9c2cc24510999d4dc3",
     "vane": "u:695d8f9c2cc24510999d4dc3",
     "vanesa": "u:695d8f9c2cc24510999d4dc3",
     "vanesa.taneva@gmail.com": "u:695d8f9c2cc24510999d4dc3",
     # ... etc
   }
   ```

4. **Safety measures:**
   - Dry-run mode first
   - Copy, don't move
   - Verify counts before deleting
   - Keep old namespaces for 30 days

### Phase 4: Update Code to Use Canonical Namespaces (Week 3)

1. **Update vector store to use `users.memory_namespace`:**
   ```python
   def get_canonical_namespace(user_id: str) -> str:
       """Get canonical Pinecone namespace for user"""
       users_col = get_users_collection()
       user = users_col.find_one({"user_id": user_id})
       
       if user and "memory_namespace" in user:
           return user["memory_namespace"]
       
       # Fallback: create namespace if missing
       namespace = f"u:{user['_id']}"
       users_col.update_one(
           {"user_id": user_id},
           {"$set": {"memory_namespace": namespace}}
       )
       return namespace
   ```

2. **Update all vector operations:**
   - `vector_store.upsert_vectors()`
   - `vector_store.search()`
   - `vector_store.delete_vectors()`
   - `memory_service.save_fact()`
   - `memory_service.retrieve_facts()`

### Phase 5: Cleanup and Verification (Week 4)

1. **Verify migration:**
   - Run `scripts/audit_storage.py`
   - Check namespace consistency
   - Verify vector counts

2. **Delete old namespaces (after 30-day safety period)**

3. **Update documentation**

4. **Monitor for issues**

## Memory Layers (Conceptual Model)

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
│              (Chat, Email, Calendar APIs)                    │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                  Memory Access Layer                         │
│           (RetrievalService, IngestionService)               │
└─────────────────────────────────────────────────────────────┘
                             │
          ┌──────────────────┴──────────────────┐
          ▼                                      ▼
┌──────────────────────┐              ┌──────────────────────┐
│  Structured Memory   │              │   Vector Memory      │
│     (MongoDB)        │              │    (Pinecone)        │
├──────────────────────┤              ├──────────────────────┤
│ Raw Evidence:        │              │ Semantic Search:     │
│ - emails             │              │ - Embeddings         │
│ - messages           │              │ - Facts              │
│ - calendar_events    │              │ - Summaries          │
│                      │              │ - Doc chunks         │
│ Distilled:           │              │                      │
│ - memory_facts       │              │ Namespace:           │
│ - projects           │              │ u:<userId>           │
│ - tasks              │              │                      │
│ - relationships      │              │                      │
│                      │              │                      │
│ Meta:                │              │                      │
│ - preferences        │              │                      │
│ - truth_ledger       │              │                      │
└──────────────────────┘              └──────────────────────┘
```

## Next Steps

1. ✅ **Week 1:**
   - [x] Run `scripts/audit_storage.py` to get baseline ✅
   - [x] Create `preferences` collection ✅ (7 documents - email styles migrated)
   - [ ] Backfill user profiles with canonical namespaces ⏳

2. ✅ **Week 2:**
   - [x] Create missing collections ✅ (all 5 created)
   - [x] Write namespace migration script ✅
   - [x] Run migration in dry-run mode ✅

3. ⏳ **Week 3:**
   - [ ] Execute namespace migration ⏳ (script ready, not executed)
   - [x] Update code to use email namespaces ✅ (using email, not canonical yet)
   - [ ] Test thoroughly ⏳

4. ⏳ **Week 4:**
   - [ ] Verify migration success ⏳
   - [ ] Clean up old namespaces ⏳
   - [x] Document changes ✅

## ✅ Completed Items

- ✅ All 5 missing collections created (`preferences`, `projects`, `tasks`, `truth_ledger`, `relationships`)
- ✅ Helper functions added to `app/memory/models.py`
- ✅ Schemas defined for all new collections
- ✅ Email style preferences migrated from cache (7 documents)
- ✅ Code updated to use email for Pinecone namespaces
- ✅ Migration scripts created and tested (dry-run)
- ✅ Audit script created and working
- ✅ Collection mapping documented

## ⏳ Pending Items

- ⏳ Execute `email_todos → tasks` migration (script ready)
- ⏳ Execute Pinecone namespace migration (script ready with manual mappings)
- ⏳ Add `memory_namespace` field to users collection
- ⏳ Update code to use canonical `u:<userId>` format (currently using email)
- ⏳ Add TTL index to cache collection
- ⏳ Add `validFrom`/`validTo` fields to `memory_facts`
- ⏳ Enhance `contacts` with `relationships` data
- ⏳ Start using `projects` instead of `thread_summaries`

See `docs/STATUS_CHECK.md` for detailed status.

