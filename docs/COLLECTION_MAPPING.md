# Collection Mapping to Memory Architecture

## Overview

This document maps existing MongoDB collections to the memory architecture layers and defines the migration path.

## Architecture Layers

### 1. Raw / Evidence Store (Keep As-Is)

**Purpose:** Store raw source data for evidence and reconstruction

| Current Collection | Future Name (Optional) | Purpose | Status |
|-------------------|------------------------|---------|--------|
| `emails` | `emails_raw` (optional rename) | Raw email data from Gmail | ✅ Keep |
| `calendar_events` | `calendar_raw` (optional rename) | Calendar entries | ✅ Keep |
| `messages` | `chats_raw` (optional rename) | Individual messages | ✅ Keep |
| `conversations` | `chats_raw` (optional rename) | Chat conversations | ✅ Keep |

**Action:** Keep as-is. Optional rename later if needed for clarity.

### 2. Structured Memory (Build On Top)

**Purpose:** Distilled, structured memory derived from raw evidence

| Current Collection | Changes Needed | Status |
|-------------------|----------------|--------|
| `email_todos` | → Merge into `tasks` | ⏳ Migrate |
| `contacts` | Keep as base, add `relationships` overlay | ✅ Keep + Enhance |
| `memory_facts` | Add: `confidence`, `evidenceRef`, `validFrom/To` | ✅ Keep + Enhance |
| `thread_summaries` | Evolve into `projects` capsules (many docs, not 1) | ⏳ Evolve |

**Action Items:**
- ✅ `tasks` collection created
- ⏳ Migrate `email_todos` → `tasks`
- ⏳ Enhance `contacts` with `relationships` data
- ⏳ Add fields to `memory_facts` schema
- ⏳ Start using `projects` instead of single `thread_summaries`

### 3. New Collections (Added)

| Collection | Purpose | Status |
|-----------|---------|--------|
| `preferences` | User settings, canonical namespace | ✅ Created |
| `projects` | Project capsules (multi-thread context) | ✅ Created |
| `tasks` | Unified tasks (all sources) | ✅ Created |
| `truth_ledger` | Fact versioning & contradictions | ✅ Created |
| `relationships` | Enhanced contact metadata | ✅ Created |

## Detailed Mapping

### Raw Evidence Store

#### `emails` → Keep
- **Current:** 1,953 documents
- **Purpose:** Raw email data from Gmail
- **Action:** Keep as-is. This is source of truth.
- **Future:** Optional rename to `emails_raw` for clarity

#### `calendar_events` → Keep
- **Current:** 41 documents
- **Purpose:** Calendar entries
- **Action:** Keep as-is
- **Future:** Optional rename to `calendar_raw`

#### `messages` + `conversations` → Keep
- **Current:** 15 messages, 236 conversations
- **Purpose:** Chat history
- **Action:** Keep as-is
- **Future:** Optional rename to `chats_raw`

### Structured Memory

#### `email_todos` → Migrate to `tasks`
- **Current:** 6 documents
- **Problem:** Tasks trapped in "email land"
- **Solution:** 
  - ✅ `tasks` collection created
  - ⏳ Migrate existing `email_todos` → `tasks`
  - ⏳ Start writing new tasks to `tasks` collection
  - Mark `email_todos` as "legacy"

**Migration Fields:**
```python
email_todos → tasks:
  user_id → user_id
  thread_id → source_ref
  todos[] → individual task documents
  extracted_at → created_at
  Add: status="pending", source="email", priority="medium"
```

#### `contacts` → Keep + Enhance with `relationships`
- **Current:** 1,294 documents
- **Base:** Keep `contacts` as-is (name, email, basic info)
- **Enhancement:** Add `relationships` overlay:
  - `importance` (high/medium/low)
  - `last_contact` (datetime)
  - `contact_frequency` (messages per month)
  - `notes` (important notes)
  - `projects` (shared projects)
  - `relationship_type` (colleague/friend/family/client)

**Action:** 
- Keep `contacts` for basic info
- Use `relationships` for enhanced metadata
- Link via `contact_email`

#### `memory_facts` → Keep + Add Fields
- **Current:** 216 documents
- **Current Fields:** `_id`, `user_id`, `text`, `type`, `confidence`, `source_ref`, `created_at`, `updated_at`, `is_active`
- **Add Fields:**
  - `evidenceRef` (already have `source_ref` - verify usage)
  - `validFrom` (datetime - when fact became true)
  - `validTo` (datetime - when fact became false, null if still valid)
  - `confidence` (already exists - verify it's being used)

**Action:**
- ✅ Keep collection
- ⏳ Add `validFrom`/`validTo` fields to schema
- ⏳ Verify `confidence` is being used properly
- ⏳ Use `source_ref` as `evidenceRef`

#### `thread_summaries` → Evolve into `projects`
- **Current:** 1 document (single summary)
- **Problem:** Only 1 doc, not scalable
- **Solution:** Use `projects` collection instead
  - Multiple project docs
  - Each project can have multiple threads
  - Better organization

**Action:**
- ✅ `projects` collection created
- ⏳ Start creating projects instead of thread summaries
- ⏳ Migrate existing thread_summaries → projects (optional)

### New Collections

#### `preferences`
- **Purpose:** User settings, canonical namespace
- **Status:** ✅ Created (0 documents)
- **Use:** Store user preferences, canonical Pinecone namespace

#### `projects`
- **Purpose:** Project capsules (multi-thread context)
- **Status:** ✅ Created (0 documents)
- **Use:** Group related threads/emails into projects

#### `tasks`
- **Purpose:** Unified task management
- **Status:** ✅ Created (0 documents)
- **Use:** All tasks from email, chat, calendar, manual

#### `truth_ledger`
- **Purpose:** Fact versioning & contradictions
- **Status:** ✅ Created (0 documents)
- **Use:** Track when facts change

#### `relationships`
- **Purpose:** Enhanced contact metadata
- **Status:** ✅ Created (0 documents)
- **Use:** Track relationship importance, frequency, notes

## Migration Priority

### High Priority (Do Now)

1. ✅ **Create new collections** - DONE
2. ⏳ **Start writing tasks to `tasks` collection** - DO THIS
3. ⏳ **Migrate `email_todos` → `tasks`** - DO THIS

### Medium Priority (Do Soon)

4. ⏳ **Enhance `contacts` with `relationships` data**
5. ⏳ **Add fields to `memory_facts` schema**
6. ⏳ **Start using `projects` instead of `thread_summaries`**

### Low Priority (Optional)

7. ⏳ **Rename collections** (emails → emails_raw, etc.)
8. ⏳ **Migrate existing `thread_summaries` → `projects`**

## Cache Collection

**Current:** 157 documents

**Action Required:**
- ⚠️ **Inspect cache contents** - What keys? What TTL behavior?
- ⚠️ **Determine if disposable:**
  - If result cache (can be rebuilt) → Add TTL indexes, keep it
  - If storing memory-ish things → Move those out
  - **Rule:** Cache should be disposable. If not disposable, it's not a cache.

**Status:** ⏳ Needs inspection

