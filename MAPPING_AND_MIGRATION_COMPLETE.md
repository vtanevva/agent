# Collection Mapping & Migration - Complete ✅

## What Was Done

### ✅ 1. Created Collection Mapping Document

**`docs/COLLECTION_MAPPING.md`** - Complete mapping of all collections to memory architecture:

- **Raw Evidence Store:** emails, calendar_events, messages, conversations → Keep as-is
- **Structured Memory:** email_todos, contacts, memory_facts, thread_summaries → Enhance/migrate
- **New Collections:** preferences, projects, tasks, truth_ledger, relationships → Created

### ✅ 2. Created Migration Scripts

**`scripts/migrate_email_todos_to_tasks.py`**
- Migrates email_todos → tasks collection
- Dry-run mode (safe testing)
- Prevents duplicates
- Marks email_todos as legacy

**Status:** Ready to use. Found 7 tasks to migrate from 6 email_todos documents.

### ✅ 3. Inspected Cache Collection

**`scripts/inspect_cache.py`**
- Analyzed 157 cache documents
- Found proper cache structure: `key`, `value`, `cached_at`, `expires_at`
- **Issue:** Has TTL fields but NO TTL index
- **Issue:** Found 2 memory-like documents that should be moved

**Cache Structure:**
```
{
  "_id": ObjectId,
  "key": "thread_detail:thread_detail|v|19ad100980bf53ea",
  "cached_at": datetime,
  "expires_at": datetime,
  "value": dict
}
```

**Recommendations:**
1. ✅ Cache is mostly disposable (result cache)
2. ⚠️ Add TTL index: `cache_col.create_index('expires_at', expireAfterSeconds=0)`
3. ⚠️ Move 2 memory-like documents to appropriate collections

## Current Status

### Collections Mapping

| Layer | Collection | Status | Action |
|-------|-----------|--------|--------|
| **Raw Evidence** | `emails` | ✅ Keep | Optional rename to `emails_raw` |
| | `calendar_events` | ✅ Keep | Optional rename to `calendar_raw` |
| | `messages` | ✅ Keep | Optional rename to `chats_raw` |
| | `conversations` | ✅ Keep | Optional rename to `chats_raw` |
| **Structured Memory** | `email_todos` | ⏳ Legacy | Migrate to `tasks` |
| | `contacts` | ✅ Keep | Enhance with `relationships` |
| | `memory_facts` | ✅ Keep | Add `validFrom`/`validTo` fields |
| | `thread_summaries` | ⏳ Evolve | Use `projects` instead |
| **New Collections** | `preferences` | ✅ Created | Ready to use |
| | `projects` | ✅ Created | Ready to use |
| | `tasks` | ✅ Created | Ready to use |
| | `truth_ledger` | ✅ Created | Ready to use |
| | `relationships` | ✅ Created | Ready to use |
| **System** | `cache` | ⚠️ Review | Add TTL index, move memory |

## Immediate Actions

### High Priority (Do Now)

1. ✅ **Collection mapping documented** - DONE
2. ⏳ **Migrate email_todos → tasks**
   ```bash
   python scripts/migrate_email_todos_to_tasks.py --execute
   ```
   - Found 7 tasks ready to migrate
   - After migration, start writing new tasks to `tasks` collection

3. ⏳ **Add TTL index to cache**
   ```python
   from app.database import get_db
   db = get_db().db
   db["cache"].create_index("expires_at", expireAfterSeconds=0)
   ```

### Medium Priority (Do Soon)

4. ⏳ **Move memory-like content from cache**
   - Inspect the 2 memory-like documents
   - Move to appropriate collections (memory_facts, preferences, etc.)

5. ⏳ **Start using `tasks` collection for new tasks**
   - Update code to write tasks to `tasks` instead of `email_todos`
   - Mark `email_todos` as legacy in code comments

6. ⏳ **Enhance `contacts` with `relationships` data**
   - Calculate importance from email frequency
   - Track last contact dates
   - Add relationship metadata

### Low Priority (Optional)

7. ⏳ **Add fields to `memory_facts`**
   - Add `validFrom`/`validTo` fields
   - Verify `confidence` is being used

8. ⏳ **Start using `projects` instead of `thread_summaries`**
   - Create projects for multi-thread contexts
   - Migrate existing thread_summaries (optional)

9. ⏳ **Rename collections** (optional)
   - emails → emails_raw
   - calendar_events → calendar_raw
   - messages/conversations → chats_raw

## Cache Analysis Results

### ✅ Good News
- Cache structure is proper (has `expires_at`)
- Most content is disposable result cache
- Keys follow pattern: `thread_detail:thread_detail|user_id|thread_id`

### ⚠️ Issues Found
1. **No TTL index** - Documents won't auto-expire
2. **2 memory-like documents** - Should be moved to proper collections

### 🔧 Fix Required

**Add TTL Index:**
```python
from app.database import get_db
db = get_db().db
cache_col = db["cache"]

# Create TTL index on expires_at
cache_col.create_index("expires_at", expireAfterSeconds=0)
```

This will auto-delete documents when `expires_at` is reached.

## Email Todos Migration

**Found:** 6 email_todos documents with 7 tasks total

**Tasks to migrate:**
1. "Apply for Data Scientist position at Belmond..."
2. "Set a digital curfew before bed..."
3. "Sneak in extra steps throughout the day..."
4. "Cook a Home Chef meal..."
5. "Pick meals from Home Chef..."
6. "Respond to Damyan Damyanov's invitation..."
7. "Schedule meeting..."

**To execute migration:**
```bash
python scripts/migrate_email_todos_to_tasks.py --execute
```

**After migration:**
- ✅ 7 tasks in `tasks` collection
- ✅ `email_todos` marked as legacy
- ⏳ Update code to write new tasks to `tasks` collection

## Summary

✅ **Collection mapping complete** - All collections documented and mapped
✅ **Migration scripts ready** - email_todos → tasks ready to execute
✅ **Cache inspected** - Structure analyzed, issues identified
⏳ **Next:** Execute migrations and start using new collections

**The foundation is ready. Time to migrate and build!** 🚀

