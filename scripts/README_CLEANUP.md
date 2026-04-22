# Memory Cleanup Script

## Quick Start

**Preview what will be deleted:**
```bash
python scripts/cleanup_memory.py --user_id v --preview
```

**Delete facts and cache (default):**
```bash
python scripts/cleanup_memory.py --user_id v
```

**Delete everything (facts, cache, relationships, projects, tasks):**
```bash
python scripts/cleanup_memory.py --user_id v --all
```

**Only delete facts:**
```bash
python scripts/cleanup_memory.py --user_id v --facts-only
```

**Only delete cache:**
```bash
python scripts/cleanup_memory.py --user_id v --cache-only
```

## What Gets Deleted

### Default (facts + cache):
- ✅ All facts for the user
- ✅ All cache entries (affects all users)

### With `--all` flag:
- ✅ All facts for the user
- ✅ All cache entries
- ✅ All relationships for the user
- ✅ All projects for the user
- ✅ All tasks for the user

## After Cleanup

1. **Re-login via Google OAuth** - Backfill will trigger automatically with new filtering
2. **Or manually trigger backfill:**
   ```bash
   curl -X POST http://localhost:5000/memory/admin/backfill-comprehensive \
     -H "Content-Type: application/json" \
     -d '{"user_id": "v", "max_emails": 100}'
   ```

## What Happens Next

After cleanup and re-login:
- ✅ Backfill will automatically trigger
- ✅ Only **important emails** will be processed (not newsletters/marketing)
- ✅ Facts, relationships, tasks, and projects will be extracted fresh
- ✅ Newsletter/marketing emails will be skipped

## Example Output

```
======================================================================
Memory Cleanup Script
======================================================================
User ID: v
Timestamp: 2026-01-07T23:30:00

[OK] Database connected

[1] Cleaning memory_facts collection...
    [OK] Deleted 294 facts

[2] Cleaning cache collection...
    [OK] Deleted 1 cache entries

======================================================================
Cleanup Summary
======================================================================
Facts deleted: 294
Cache deleted: 1

Total items deleted: 295

[SUCCESS] Cleanup completed!

Next steps:
1. Re-login via Google OAuth to trigger fresh backfill
2. Or manually trigger backfill:
   curl -X POST http://localhost:5000/memory/admin/backfill-comprehensive \
     -H "Content-Type: application/json" \
     -d '{"user_id": "v", "max_emails": 100}'

[INFO] Backfill will now skip newsletters/marketing emails
       and only process important emails (action_items, urgent, clients, etc.)
======================================================================
```

