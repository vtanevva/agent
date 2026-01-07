# Pinecone Namespace Change: Username → Email

## Summary

Changed Pinecone namespaces from using `user_id` (username) to using email addresses for better stability and uniqueness.

## Changes Made

### 1. Created `app/utils/user_email_utils.py`
- New utility function `get_user_email(user_id)` that:
  - Returns email if `user_id` is already an email (contains `@`)
  - Attempts to get email from Gmail profile using stored credentials
  - Falls back to `user_id` if email cannot be retrieved

### 2. Updated `app/memory/vector_store.py`
- Modified all methods to use email as namespace:
  - `upsert_vectors()` - Now uses email for namespace
  - `search()` - Now uses email for namespace
  - `delete_vectors()` - Now uses email for namespace
  - `get_stats()` - Now uses email for namespace
- Metadata still contains `user_id` for filtering purposes
- Updated docstrings to reflect email-based namespaces

### 3. Updated `app/services/memory_service.py`
- Updated `save_fact()` to use email for namespace
- Updated `retrieve_facts()` to use email for namespace

## How It Works

1. When storing/retrieving vectors, the system:
   - Takes `user_id` (which may be a username like "v" or "vanesa")
   - Calls `get_user_email(user_id)` to get the email address
   - Uses the email as the Pinecone namespace
   - Still stores `user_id` in metadata for filtering

2. Email retrieval strategy:
   - If `user_id` already contains `@`, use it directly
   - Otherwise, load Google credentials and get Gmail profile
   - If that fails, fall back to `user_id` (backward compatibility)

## Benefits

1. **Stability**: Email addresses are more stable than usernames
2. **Uniqueness**: Email addresses are globally unique
3. **Consistency**: All namespaces will be email-based going forward
4. **Backward Compatibility**: Falls back to `user_id` if email can't be retrieved

## Migration Note

- **Existing vectors**: Vectors stored with username namespaces will remain in those namespaces
- **New vectors**: All new vectors will be stored using email namespaces
- **Search**: The system will look in the email namespace, so old vectors won't be found until migrated
- **Recommendation**: Create a migration script to move existing vectors from username namespaces to email namespaces

## Testing

To test the changes:
1. Store a new fact for a user
2. Check Pinecone to verify the namespace is now the email address
3. Verify search still works correctly

