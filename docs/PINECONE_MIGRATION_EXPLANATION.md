# Pinecone Migration Problem & Solutions

## The Problem

**Pinecone doesn't have a "list all vectors" API.**

You cannot do:
```python
# This doesn't exist!
all_vectors = index.list_all_vectors(namespace="v")
```

**What Pinecone DOES have:**
1. `query()` - Returns top_k most similar vectors to a query vector (not all vectors)
2. `fetch()` - Fetches specific vectors by ID (but you need the IDs first!)
3. `describe_index_stats()` - Returns counts per namespace (but not the actual vectors)

## Why Current Migration Fails

The current migration script tries:
```python
# Query with dummy vector
query_result = index.query(
    namespace=old_namespace,
    vector=dummy_vector,  # Random vector
    top_k=100
)
```

**Problem:** This only returns the 100 vectors most similar to the dummy vector, not ALL vectors in the namespace. If you have 332 vectors, you'll only get 100 of them.

## Solutions

### Option 1: Store Vector IDs in MongoDB (Best for Future)

**How it works:**
- When creating vectors, store the vector ID in MongoDB
- Link vectors to facts/messages in MongoDB
- Use stored IDs to fetch and migrate

**Implementation:**
```python
# When creating a fact
fact_doc = {
    "_id": fact_id,
    "user_id": user_id,
    "text": fact_text,
    "vector_id": vector_id,  # NEW: Store Pinecone vector ID
    "namespace": namespace,  # NEW: Store namespace used
    ...
}

# During migration
facts = memory_facts_col.find({"user_id": user_id})
vector_ids = [fact["vector_id"] for fact in facts if "vector_id" in fact]

# Fetch vectors by ID
vectors = index.fetch(ids=vector_ids, namespace=old_namespace)

# Migrate to new namespace
index.upsert(vectors=vectors, namespace=new_namespace)
```

**Pros:**
- Clean, reliable
- Can track which vectors belong to which facts
- Works for future migrations

**Cons:**
- Doesn't help with existing vectors (no IDs stored)
- Need to update code to store IDs going forward

### Option 2: Query with Multiple Random Vectors (Workaround)

**How it works:**
- Generate many random query vectors
- Query each one to get different subsets
- Combine results (deduplicate)
- Hope to get all vectors

**Implementation:**
```python
import numpy as np

all_vector_ids = set()
all_vectors = []

# Try many random queries
for i in range(100):  # Query 100 times
    random_vector = np.random.rand(1536).tolist()
    result = index.query(
        namespace=old_namespace,
        vector=random_vector,
        top_k=100
    )
    
    for match in result.matches:
        if match.id not in all_vector_ids:
            all_vector_ids.add(match.id)
            all_vectors.append({
                "id": match.id,
                "values": match.values,
                "metadata": match.metadata
            })

# Now migrate
index.upsert(vectors=all_vectors, namespace=new_namespace)
```

**Pros:**
- Works with existing vectors
- No code changes needed

**Cons:**
- Not guaranteed to get all vectors (might miss some)
- Slow (many queries)
- Inefficient

### Option 3: Link via Metadata (Current Facts)

**How it works:**
- Facts in MongoDB have `source_ref` (message_id, thread_id, etc.)
- Query Pinecone with metadata filters
- Get vectors that match

**Implementation:**
```python
# Get all facts for user
facts = memory_facts_col.find({"user_id": user_id})

# For each fact, try to find vector by metadata
for fact in facts:
    # Query with fact text as query
    query_vector = generate_embedding(fact["text"])
    
    result = index.query(
        namespace=old_namespace,
        vector=query_vector,
        top_k=1,
        filter={"user_id": user_id, "text": fact["text"][:100]}
    )
    
    if result.matches:
        # Found the vector, migrate it
        ...
```

**Pros:**
- Uses existing data structure
- Can link facts to vectors

**Cons:**
- Only works for facts (not all vector types)
- Might miss vectors without matching facts
- Slow (one query per fact)

### Option 4: Accept Loss & Move Forward (Pragmatic)

**How it works:**
- Don't migrate old vectors
- New vectors use canonical namespace
- Old vectors stay in old namespaces (will be ignored)

**Pros:**
- Fast, simple
- No risk of data loss
- New system works correctly

**Cons:**
- Lose access to old vectors
- Memory might feel incomplete initially

## Recommended Approach

**For now:** Use Option 2 (multiple random queries) as a best-effort migration
**Going forward:** Implement Option 1 (store vector IDs in MongoDB)

### Hybrid Solution

1. **Update code to store vector IDs:**
   ```python
   # In memory_facts, add vector_id field
   fact_doc["vector_id"] = vector_id
   ```

2. **For existing vectors:** Use Option 2 (multiple random queries)
   - Best effort to migrate what we can
   - Accept that some might be missed

3. **For new vectors:** Store IDs in MongoDB
   - Future migrations will be easy
   - Can track and manage vectors properly

## Implementation Plan

1. Update `memory_facts` schema to include `vector_id`
2. Update vector creation code to store IDs
3. Fix migration script to use multiple random queries
4. Execute migration (best effort)
5. Verify counts (expect some loss)

