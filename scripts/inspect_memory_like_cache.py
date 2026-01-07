#!/usr/bin/env python3
"""
Inspect Memory-Like Cache Documents

Finds and displays the memory-like documents in cache to determine
where they should be moved.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager

load_dotenv()


def inspect_memory_like_documents():
    """Find and display memory-like documents in cache"""
    
    print("=" * 70)
    print("Memory-Like Cache Documents Inspection")
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
    
    # Find all cache documents
    all_docs = list(cache_col.find({}))
    
    print(f"\n[INFO] Total cache documents: {len(all_docs)}")
    print("[INFO] Searching for memory-like content...\n")
    
    memory_keywords = ["fact", "memory", "user", "preference", "relationship", "project", "task"]
    memory_like_docs = []
    
    for doc in all_docs:
        doc_str = str(doc).lower()
        doc_value = doc.get("value", {})
        value_str = str(doc_value).lower()
        
        # Check if contains memory keywords
        if any(kw in doc_str or kw in value_str for kw in memory_keywords):
            memory_like_docs.append(doc)
    
    print(f"[FOUND] {len(memory_like_docs)} memory-like documents\n")
    
    if not memory_like_docs:
        print("[OK] No memory-like documents found")
        db_manager.disconnect()
        return True
    
    # Analyze each document
    for i, doc in enumerate(memory_like_docs, 1):
        print("=" * 70)
        print(f"Document {i}/{len(memory_like_docs)}")
        print("=" * 70)
        
        print(f"\n_id: {doc.get('_id')}")
        print(f"key: {doc.get('key')}")
        print(f"cached_at: {doc.get('cached_at')}")
        print(f"expires_at: {doc.get('expires_at')}")
        
        value = doc.get("value", {})
        print(f"\nvalue type: {type(value).__name__}")
        print(f"value keys: {list(value.keys()) if isinstance(value, dict) else 'N/A'}")
        
        # Pretty print value
        print("\nvalue content:")
        import json
        try:
            # Try to convert to JSON-serializable format
            if isinstance(value, dict):
                print(json.dumps(value, indent=2, default=str))
            else:
                print(str(value)[:500])
        except:
            print(str(value)[:500])
        
        # Determine where it should go
        print("\n" + "-" * 70)
        print("Analysis:")
        print("-" * 70)
        
        value_lower = str(value).lower()
        doc_key = doc.get("key", "").lower()
        
        recommendations = []
        
        if "fact" in value_lower or "memory_fact" in value_lower:
            recommendations.append("-> memory_facts collection")
        if "preference" in value_lower or "setting" in value_lower:
            recommendations.append("-> preferences collection")
        if "relationship" in value_lower or "contact" in value_lower:
            recommendations.append("-> relationships collection")
        if "project" in value_lower:
            recommendations.append("-> projects collection")
        if "task" in value_lower or "todo" in value_lower:
            recommendations.append("-> tasks collection")
        
        if recommendations:
            print("Recommended destination:")
            for rec in recommendations:
                print(f"  {rec}")
        else:
            print("  [UNKNOWN] Cannot determine destination - manual review needed")
        
        # Check if it's actually cache (expires soon)
        expires_at = doc.get("expires_at")
        if expires_at:
            if expires_at < datetime.utcnow():
                print("\n  [EXPIRED] Document has expired - safe to delete")
            else:
                time_until_expiry = expires_at - datetime.utcnow()
                print(f"\n  [EXPIRES] Document expires in: {time_until_expiry}")
                if time_until_expiry.total_seconds() < 3600:  # Less than 1 hour
                    print("  [NOTE] Expires soon - might be legitimate cache")
        
        print()
    
    # Summary
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"\nFound {len(memory_like_docs)} memory-like documents")
    print("\nNext steps:")
    print("  1. Review each document above")
    print("  2. Determine if it's actually memory or just cached data")
    print("  3. If memory: move to appropriate collection")
    print("  4. If cache: keep in cache (it will expire)")
    print("\n[RULE] Cache should be disposable. If it's not disposable, it's not a cache.")
    
    db_manager.disconnect()
    return True


if __name__ == "__main__":
    try:
        inspect_memory_like_documents()
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Inspection cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Inspection failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

