# Pinecone Namespace Issue Analysis

## Problem

Facts are being stored in Pinecone using **login usernames** as namespaces instead of proper user IDs. This is evident from the namespace list showing values like:
- `v` (332 vectors)
- `vane` (84 vectors)  
- `vanesa` (5 vectors)
- `vanesa.taneva@gmail.com` (54 vectors)
- etc.

## Root Cause

In `server.py` line 1585, during OAuth callback:
```python
user_id = state  # Use state as userId (this is the username)
```

The `state` parameter from OAuth contains the **login username**, which is then used directly as:
1. The `user_id` throughout the application
2. The **Pinecone namespace** (in `vector_store.py` line 156)

## How Facts Are Stored

1. **MongoDB** (`memory_facts` collection): Facts are stored with `user_id` field = username
2. **Pinecone**: Facts are embedded and stored with `namespace=user_id` (which is the username)

From `app/memory/vector_store.py`:
```python
self._index.upsert(
    vectors=records,
    namespace=user_id  # <-- This is the username!
)
```

## Issues with Current Approach

1. **Not Unique**: Multiple users could have similar usernames
2. **Not Stable**: Usernames can change, breaking the namespace mapping
3. **Privacy**: Usernames/emails are visible in Pinecone namespaces
4. **Inconsistent**: Some namespaces are emails (`vanesa.taneva@gmail.com`), some are usernames (`v`, `vane`)

## Current Storage Locations

- **MongoDB `memory_facts` collection**: 216 documents (facts stored with username as user_id)
- **Pinecone index `psy`**: 568 total vectors across 34 namespaces (mostly usernames)

## Recommended Solution

1. **Use a stable user ID**: Generate or use a UUID-based user ID from MongoDB `users` collection
2. **Map username → user_id**: Create a mapping table or use MongoDB `users._id` as the canonical user ID
3. **Migration**: Create a script to migrate existing Pinecone vectors from username namespaces to user_id namespaces
4. **Update code**: Change all places where `user_id` is set from OAuth state to use the proper user ID

## Files That Need Changes

1. `server.py` - OAuth callback (line 1585)
2. `app/memory/vector_store.py` - Already uses `user_id` as namespace (just need to ensure it's proper ID)
3. `app/api/chat_routes.py` - Normalizes user_id (line 233)
4. All API routes that accept `user_id` from request

