#!/usr/bin/env python3
"""
Inspect Cache Collection

Analyzes what's in the cache collection to determine:
- What keys are being used
- What TTL behavior exists
- Whether it's disposable (result cache) or contains memory
"""

import os
import sys
from collections import defaultdict, Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager

load_dotenv()


def inspect_cache():
    """Inspect cache collection contents"""
    
    print("=" * 70)
    print("Cache Collection Inspection")
    print("=" * 70)
    
    if not Config.MONGO_URI:
        print("[ERROR] MONGO_URI not configured")
        return False
    
    db_manager = DatabaseManager()
    if not db_manager.connect():
        print("[ERROR] Failed to connect to MongoDB")
        return False
    
    db = db_manager.db
    if db is None:
        print("[ERROR] Database not initialized")
        return False
    
    cache_col = db["cache"]
    total_docs = cache_col.count_documents({})
    
    print(f"\n[INFO] Total cache documents: {total_docs}")
    
    if total_docs == 0:
        print("[OK] Cache is empty")
        db_manager.disconnect()
        return True
    
    # Sample documents
    print("\n[INFO] Sampling cache documents...")
    sample_size = min(20, total_docs)
    sample_docs = list(cache_col.find({}).limit(sample_size))
    
    # Analyze structure
    key_patterns = Counter()
    field_analysis = defaultdict(set)
    has_ttl = False
    has_timestamp = False
    memory_like = []
    
    print(f"\n[ANALYSIS] Analyzing {sample_size} sample documents...\n")
    
    for doc in sample_docs:
        # Check for _id patterns
        doc_id = str(doc.get("_id", ""))
        
        # Analyze key patterns
        if ":" in doc_id:
            key_patterns[doc_id.split(":")[0]] += 1
        
        # Check fields
        for key in doc.keys():
            field_analysis[key].add(type(doc[key]).__name__)
            
            # Check for TTL indicators
            if "ttl" in key.lower() or "expire" in key.lower():
                has_ttl = True
            if "timestamp" in key.lower() or "created" in key.lower() or "updated" in key.lower():
                has_timestamp = True
        
        # Check if looks like memory (not disposable cache)
        doc_str = str(doc).lower()
        memory_keywords = ["fact", "memory", "user", "preference", "relationship", "project"]
        if any(kw in doc_str for kw in memory_keywords):
            memory_like.append(doc_id[:50])
    
    # Report findings
    print("=" * 70)
    print("Key Patterns")
    print("=" * 70)
    if key_patterns:
        for pattern, count in key_patterns.most_common(10):
            print(f"  {pattern}: {count} documents")
    else:
        print("  No clear key patterns found")
    
    print("\n" + "=" * 70)
    print("Field Analysis")
    print("=" * 70)
    for field, types in sorted(field_analysis.items()):
        print(f"  {field}: {', '.join(types)}")
    
    print("\n" + "=" * 70)
    print("TTL & Timestamp Analysis")
    print("=" * 70)
    print(f"  Has TTL fields: {has_ttl}")
    print(f"  Has timestamp fields: {has_timestamp}")
    
    # Check for TTL index
    indexes = list(cache_col.list_indexes())
    has_ttl_index = any("expireAfterSeconds" in str(idx) for idx in indexes)
    print(f"  Has TTL index: {has_ttl_index}")
    
    if has_ttl_index:
        for idx in indexes:
            if "expireAfterSeconds" in str(idx):
                print(f"    TTL index: {idx}")
    
    print("\n" + "=" * 70)
    print("Memory-Like Content Check")
    print("=" * 70)
    if memory_like:
        print(f"  [WARNING] Found {len(memory_like)} documents that look like memory:")
        for doc_id in memory_like[:5]:
            print(f"    - {doc_id}...")
        if len(memory_like) > 5:
            print(f"    ... and {len(memory_like) - 5} more")
        print("\n  [RECOMMENDATION] These should be moved to appropriate collections:")
        print("    - facts -> memory_facts")
        print("    - preferences -> preferences")
        print("    - relationships -> relationships")
        print("    - projects -> projects")
    else:
        print("  [OK] No memory-like content detected")
        print("  [OK] Cache appears to be disposable result cache")
    
    # Sample document structure
    print("\n" + "=" * 70)
    print("Sample Document Structure")
    print("=" * 70)
    if sample_docs:
        sample = sample_docs[0]
        print(f"  Sample _id: {sample.get('_id')}")
        print(f"  Keys: {list(sample.keys())}")
        print(f"  Sample content (first 200 chars):")
        print(f"    {str(sample)[:200]}...")
    
    # Recommendations
    print("\n" + "=" * 70)
    print("Recommendations")
    print("=" * 70)
    
    if memory_like:
        print("\n[ACTION REQUIRED]")
        print("  1. Move memory-like content to appropriate collections")
        print("  2. Keep only disposable result cache in cache collection")
        print("  3. Add TTL index if not present")
    else:
        print("\n[OK] Cache appears to be disposable")
        if not has_ttl_index:
            print("  [RECOMMENDATION] Add TTL index to auto-expire old cache:")
            print("    cache_col.create_index('created_at', expireAfterSeconds=86400)  # 24 hours")
        else:
            print("  [OK] TTL index already exists")
    
    print("\n[RULE] Cache should be disposable. If it's not disposable, it's not a cache.")
    
    db_manager.disconnect()
    return True


if __name__ == "__main__":
    try:
        inspect_cache()
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Inspection cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Inspection failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

