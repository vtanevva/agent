# Migration Quick Start Guide

## 🎯 Goal

Fix Pinecone namespace inconsistencies and establish a clean memory architecture.

## 📊 Current State

Run audit to see current state:
```bash
python scripts/audit_storage.py --format text
```

**Key Issues:**
- ❌ Users have vectors split across multiple namespaces (e.g., "v", "vane", "vanesa", "vanesa.taneva@gmail.com")
- ❌ Inconsistent namespace formats (usernames, emails, test users)
- ❌ Missing collections (preferences, projects, tasks, truth_ledger, relationships)

## 🚀 Migration Steps

### Step 1: Audit Current State (5 minutes)

```bash
# Generate audit report
python scripts/audit_storage.py --format text --output audit_before.txt

# Review the report
cat audit_before.txt
```

**What to look for:**
- How many namespaces exist?
- Which namespaces have the most vectors?
- Are there potential duplicates?

### Step 2: Dry Run Migration (10 minutes)

```bash
# Dry run - see what would happen (safe, no changes)
python scripts/migrate_pinecone_namespaces.py --dry-run --all
```

**What this does:**
- Shows which namespaces would be migrated
- Shows target canonical namespaces
- **Makes NO changes** (safe to run)

**Review the output:**
- Does the mapping look correct?
- Are all users accounted for?
- Any unexpected mappings?

### Step 3: Create Missing Collections (15 minutes)

Create the MongoDB collections that don't exist yet:

```python
# Run this in Python shell or create a script
from app.database import DatabaseManager
from datetime import datetime

db_manager = DatabaseManager()
db_manager.connect()
db = db_manager.db

# Create preferences collection
db.create_collection("preferences")
db["preferences"].create_index([("user_id", 1)], unique=True)

# Create tasks collection
db.create_collection("tasks")
db["tasks"].create_index([("user_id", 1), ("status", 1)])
db["tasks"].create_index([("user_id", 1), ("due_date", 1)])

# Create projects collection
db.create_collection("projects")
db["projects"].create_index([("user_id", 1), ("status", 1)])

# Create truth_ledger collection
db.create_collection("truth_ledger")
db["truth_ledger"].create_index([("user_id", 1), ("fact_id", 1)])

# Create relationships collection
db.create_collection("relationships")
db["relationships"].create_index([("user_id", 1), ("contact_email", 1)])

print("✅ Collections created!")
```

### Step 4: Backfill User Profiles (10 minutes)

Add canonical namespaces to existing users:

```python
from app.database import DatabaseManager
from app.utils.oauth_utils import load_google_credentials, get_gmail_profile

db_manager = DatabaseManager()
db_manager.connect()
db = db_manager.db

users_col = db["users"]
users = list(users_col.find({}))

for user in users:
    user_id = user.get("user_id")
    canonical_namespace = f"u:{user['_id']}"
    
    # Try to get email
    try:
        creds = load_google_credentials(user_id)
        email = get_gmail_profile(creds) if creds else None
    except:
        email = None
    
    # Update user
    update = {
        "memory_namespace": canonical_namespace,
        "primary_email": email
    }
    
    users_col.update_one(
        {"_id": user["_id"]},
        {"$set": update}
    )
    
    print(f"✅ Updated {user_id}: namespace={canonical_namespace}, email={email}")

print("✅ User profiles backfilled!")
```

### Step 5: Execute Migration (30 minutes)

**⚠️ IMPORTANT: This makes real changes!**

```bash
# Execute migration for all users
python scripts/migrate_pinecone_namespaces.py --all --yes-i-am-sure
```

**What happens:**
1. Copies vectors from old namespaces to new canonical namespaces
2. Verifies vector counts match
3. Logs all operations to `migration_log_TIMESTAMP.json`
4. **Does NOT delete old namespaces** (kept for safety)

**Monitor the output:**
- Watch for errors
- Verify counts match
- Check that migration completes successfully

### Step 6: Verify Migration (10 minutes)

```bash
# Run audit again to verify
python scripts/audit_storage.py --format text --output audit_after.txt

# Compare before and after
diff audit_before.txt audit_after.txt
```

**What to check:**
- New canonical namespaces exist (u:...)
- Vector counts are correct
- Old namespaces still exist (for now)

### Step 7: Test Application (20 minutes)

Test key functionality:

1. **Store a new fact:**
   - Send a chat message with a fact
   - Check Pinecone to see it's in the canonical namespace

2. **Retrieve facts:**
   - Ask a question that requires memory
   - Verify relevant facts are retrieved

3. **Email processing:**
   - Process an email
   - Verify facts are extracted to canonical namespace

### Step 8: Cleanup (After 30 Days)

**⚠️ Only do this after 30 days of successful operation!**

```bash
# Delete old namespaces
python scripts/migrate_pinecone_namespaces.py --cleanup-old --days-after 30
```

## 📋 Rollback Plan

If something goes wrong:

1. **Vectors are copied, not moved** - old namespaces still have the original data
2. **Code changes to use canonical namespaces** - revert the code changes in:
   - `app/memory/vector_store.py`
   - `app/services/memory_service.py`
3. **MongoDB changes** - users still have `user_id` field, just added `memory_namespace`

To rollback:
```bash
# Revert code changes
git checkout HEAD -- app/memory/vector_store.py app/services/memory_service.py

# Restart application
# Old namespaces will be used again
```

## 🎯 Success Criteria

Migration is successful when:

- ✅ All users have `memory_namespace` in users collection
- ✅ New vectors are stored in canonical namespaces (u:...)
- ✅ Retrieval works correctly from canonical namespaces
- ✅ No errors in application logs
- ✅ Vector counts match between old and new namespaces

## 📞 Troubleshooting

### Issue: Migration script can't find email for user

**Solution:** Manual mapping
```python
# In the migration script, add manual mapping
namespace_map = {
    "v": "u:695d8f9c2cc24510999d4dc3",
    # Add other mappings as needed
}
```

### Issue: Vector counts don't match

**Cause:** Pinecone query API limitations

**Solution:** 
- Run migration again (it will upsert, not duplicate)
- Verify manually using Pinecone console

### Issue: Application can't find old facts after migration

**Cause:** Code is using new namespaces, but migration didn't complete

**Solution:**
1. Check migration logs
2. Verify canonical namespace in users collection
3. Re-run migration for specific user
4. Check Pinecone console directly

## 📚 Next Steps

After migration:

1. **Monitor for 1 week:**
   - Check error logs daily
   - Verify facts are being stored/retrieved
   - Test with different users

2. **Enhance memory system:**
   - Start using new collections (projects, tasks, relationships)
   - Implement truth versioning
   - Add preference-based customization

3. **Cleanup (after 30 days):**
   - Delete old namespaces
   - Archive migration logs
   - Update documentation

## 🔧 Useful Commands

```bash
# Quick status check
python scripts/audit_storage.py --format json | jq '.pinecone.namespace_analysis'

# Export audit as JSON for analysis
python scripts/audit_storage.py --format json --output audit.json

# Check specific namespace
# (Manual Pinecone query using console or API)

# Test email retrieval for user
python -c "from app.utils.user_email_utils import get_user_email; print(get_user_email('v'))"
```

