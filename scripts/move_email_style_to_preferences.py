#!/usr/bin/env python3
"""
Move Email Style Preferences from Cache to Preferences Collection

Email style preferences are being cached but should be stored permanently
in the preferences collection.
"""

import os
import sys
from datetime import datetime
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager
from app.memory.models import get_preferences_collection

load_dotenv()


def move_email_style_preferences(dry_run=True):
    """Move email style preferences from cache to preferences collection"""
    
    print("=" * 70)
    print("Move Email Style Preferences: Cache -> Preferences")
    print("=" * 70)
    
    if dry_run:
        print("\n[DRY-RUN] Mode: No changes will be made\n")
    
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
    prefs_col = db["preferences"]  # Use db directly instead of helper
    
    # Find email_style cache entries
    email_style_docs = list(cache_col.find({
        "key": {"$regex": "^email_style:"}
    }))
    
    print(f"[INFO] Found {len(email_style_docs)} email style cache entries\n")
    
    if not email_style_docs:
        print("[OK] No email style preferences in cache")
        db_manager.disconnect()
        return True
    
    moved_count = 0
    skipped_count = 0
    
    for cache_doc in email_style_docs:
        key = cache_doc.get("key", "")
        # Extract user_id from key: "email_style:email_style|user_id"
        parts = key.split("|")
        if len(parts) < 2:
            print(f"  [SKIP] Invalid key format: {key}")
            skipped_count += 1
            continue
        
        user_id = parts[-1]
        email_style = cache_doc.get("value", {})
        
        if not email_style or not isinstance(email_style, dict):
            print(f"  [SKIP] Invalid email style data for user {user_id}")
            skipped_count += 1
            continue
        
        print(f"\n[PROCESS] User: {user_id}")
        print(f"  Cache key: {key}")
        print(f"  Email style keys: {list(email_style.keys())}")
        
        if dry_run:
            print(f"  [DRY-RUN] Would move to preferences collection")
            print(f"  [DRY-RUN] Would store as: preferences.email_style")
        else:
            # Get or create preferences document
            prefs_doc = prefs_col.find_one({"user_id": user_id})
            
            if prefs_doc:
                # Update existing preferences
                update_data = {
                    "email_style": email_style,
                    "updated_at": datetime.utcnow()
                }
                prefs_col.update_one(
                    {"user_id": user_id},
                    {"$set": update_data}
                )
                print(f"  [OK] Updated preferences with email_style")
            else:
                # Create new preferences document
                prefs_doc = {
                    "_id": str(uuid4()),
                    "user_id": user_id,
                    "email_style": email_style,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                prefs_col.insert_one(prefs_doc)
                print(f"  [OK] Created preferences document with email_style")
            
            # Delete from cache (optional - you might want to keep it until TTL expires)
            # cache_col.delete_one({"_id": cache_doc["_id"]})
            # print(f"  [OK] Deleted from cache")
            
            moved_count += 1
    
    db_manager.disconnect()
    
    # Summary
    print("\n" + "=" * 70)
    print("Migration Summary")
    print("=" * 70)
    
    if dry_run:
        print(f"[DRY-RUN] Would move: {moved_count} email style preferences")
        print(f"[DRY-RUN] Would skip: {skipped_count} entries")
        print("\n[INFO] Run with --execute to perform migration")
    else:
        print(f"[SUCCESS] Moved: {moved_count} email style preferences")
        print(f"[INFO] Skipped: {skipped_count} entries")
        print(f"\n[OK] Migration complete!")
        print(f"\n[NOTE] Cache entries will expire naturally via TTL")
        print(f"       Or delete them manually if desired")
    
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Move email style preferences from cache to preferences")
    parser.add_argument("--execute", action="store_true",
                        help="Actually perform migration (default is dry-run)")
    
    args = parser.parse_args()
    
    try:
        move_email_style_preferences(dry_run=not args.execute)
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

