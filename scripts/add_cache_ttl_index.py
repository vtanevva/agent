#!/usr/bin/env python3
"""
Add TTL Index to Cache Collection

Creates a TTL index on expires_at field so cache documents auto-expire.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager

load_dotenv()


def add_cache_ttl_index():
    """Add TTL index to cache collection"""
    
    print("=" * 70)
    print("Add TTL Index to Cache Collection")
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
    
    # Check if index already exists
    indexes = list(cache_col.list_indexes())
    has_ttl = any("expires_at" in str(idx) and "expireAfterSeconds" in str(idx) for idx in indexes)
    
    if has_ttl:
        print("\n[INFO] TTL index already exists on cache collection")
        for idx in indexes:
            if "expires_at" in str(idx):
                print(f"  Existing index: {idx}")
        db_manager.disconnect()
        return True
    
    # Create TTL index
    print("\n[INFO] Creating TTL index on 'expires_at' field...")
    print("       Documents will auto-delete when expires_at is reached")
    
    try:
        cache_col.create_index("expires_at", expireAfterSeconds=0)
        print("[OK] TTL index created successfully!")
        
        # Verify
        indexes = list(cache_col.list_indexes())
        print("\n[VERIFY] Current indexes on cache collection:")
        for idx in indexes:
            print(f"  - {idx}")
        
    except Exception as e:
        print(f"[ERROR] Failed to create TTL index: {e}")
        db_manager.disconnect()
        return False
    
    db_manager.disconnect()
    
    print("\n[SUCCESS] Cache collection now has TTL index")
    print("          Expired documents will be automatically deleted")
    
    return True


if __name__ == "__main__":
    try:
        add_cache_ttl_index()
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

