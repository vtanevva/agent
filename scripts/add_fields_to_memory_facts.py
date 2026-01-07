#!/usr/bin/env python3
"""
Add Fields to Memory Facts Collection

Adds new fields to existing memory_facts documents:
- valid_from: When fact became true
- valid_to: When fact became false (null if still valid)
- vector_id: Pinecone vector ID (for future tracking)
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager

load_dotenv()


def add_fields_to_memory_facts():
    """Add new fields to memory_facts collection"""
    
    print("=" * 70)
    print("Add Fields to Memory Facts Collection")
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
    
    facts_col = db["memory_facts"]
    total_facts = facts_col.count_documents({})
    
    print(f"\n[INFO] Total facts in collection: {total_facts}")
    
    if total_facts == 0:
        print("[OK] No facts to update")
        db_manager.disconnect()
        return True
    
    # Check which facts need updates
    facts_without_fields = facts_col.count_documents({
        "$or": [
            {"valid_from": {"$exists": False}},
            {"valid_to": {"$exists": False}},
            {"vector_id": {"$exists": False}}
        ]
    })
    
    print(f"[INFO] Facts needing updates: {facts_without_fields}")
    
    if facts_without_fields == 0:
        print("[OK] All facts already have new fields")
        db_manager.disconnect()
        return True
    
    # Update facts
    print("\n[INFO] Adding fields to facts...")
    
    # Set valid_from to created_at for existing facts
    # Set valid_to to null (still valid)
    # vector_id stays null (we don't have it for old facts)
    
    result = facts_col.update_many(
        {
            "$or": [
                {"valid_from": {"$exists": False}},
                {"valid_to": {"$exists": False}}
            ]
        },
        [
            {
                "$set": {
                    "valid_from": {"$ifNull": ["$valid_from", "$created_at"]},
                    "valid_to": {"$ifNull": ["$valid_to", None]},
                    "vector_id": {"$ifNull": ["$vector_id", None]}
                }
            }
        ]
    )
    
    updated_count = result.modified_count
    
    print(f"\n[SUCCESS] Updated {updated_count} facts")
    print(f"  - valid_from: Set to created_at for existing facts")
    print(f"  - valid_to: Set to null (facts are still valid)")
    print(f"  - vector_id: Set to null (not available for old facts)")
    
    # Verify
    facts_with_fields = facts_col.count_documents({
        "valid_from": {"$exists": True},
        "valid_to": {"$exists": True}
    })
    
    print(f"\n[VERIFY] Facts with new fields: {facts_with_fields}/{total_facts}")
    
    db_manager.disconnect()
    
    print("\n[OK] Schema update complete!")
    print("\n[NOTE] Going forward, set these fields when creating new facts:")
    print("  - valid_from: datetime when fact became true")
    print("  - valid_to: null (or datetime when fact becomes false)")
    print("  - vector_id: Pinecone vector ID (for tracking)")
    
    return True


if __name__ == "__main__":
    try:
        add_fields_to_memory_facts()
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

