#!/usr/bin/env python3
"""
Create Missing Memory Collections

Creates the missing MongoDB collections for complete memory architecture:
- preferences
- projects
- tasks
- truth_ledger
- relationships
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager

load_dotenv()


def create_collections():
    """Create missing collections with proper indexes"""
    
    print("=" * 70)
    print("Creating Missing Memory Collections")
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
    
    print(f"\n[INFO] Connected to database: {db.name}")
    
    collections_created = []
    collections_existing = []
    
    # 1. Preferences Collection
    print("\n[1/5] Creating 'preferences' collection...")
    if "preferences" not in db.list_collection_names():
        db.create_collection("preferences")
        db["preferences"].create_index([("user_id", 1)], unique=True)
        db["preferences"].create_index([("updated_at", -1)])
        collections_created.append("preferences")
        print("  [OK] Created 'preferences' collection with indexes")
    else:
        collections_existing.append("preferences")
        print("  [INFO] 'preferences' collection already exists")
    
    # 2. Projects Collection
    print("\n[2/5] Creating 'projects' collection...")
    if "projects" not in db.list_collection_names():
        db.create_collection("projects")
        db["projects"].create_index([("user_id", 1), ("status", 1)])
        db["projects"].create_index([("user_id", 1), ("updated_at", -1)])
        db["projects"].create_index([("user_id", 1), ("name", 1)])
        collections_created.append("projects")
        print("  [OK] Created 'projects' collection with indexes")
    else:
        collections_existing.append("projects")
        print("  [INFO] 'projects' collection already exists")
    
    # 3. Tasks Collection (unified, not just email)
    print("\n[3/5] Creating 'tasks' collection...")
    if "tasks" not in db.list_collection_names():
        db.create_collection("tasks")
        db["tasks"].create_index([("user_id", 1), ("status", 1)])
        db["tasks"].create_index([("user_id", 1), ("due_date", 1)])
        db["tasks"].create_index([("user_id", 1), ("priority", 1)])
        db["tasks"].create_index([("user_id", 1), ("created_at", -1)])
        db["tasks"].create_index([("source", 1), ("source_ref", 1)])
        collections_created.append("tasks")
        print("  [OK] Created 'tasks' collection with indexes")
    else:
        collections_existing.append("tasks")
        print("  [INFO] 'tasks' collection already exists")
    
    # 4. Truth Ledger Collection
    print("\n[4/5] Creating 'truth_ledger' collection...")
    if "truth_ledger" not in db.list_collection_names():
        db.create_collection("truth_ledger")
        db["truth_ledger"].create_index([("user_id", 1), ("fact_id", 1)])
        db["truth_ledger"].create_index([("user_id", 1), ("changed_at", -1)])
        db["truth_ledger"].create_index([("reason", 1)])
        collections_created.append("truth_ledger")
        print("  [OK] Created 'truth_ledger' collection with indexes")
    else:
        collections_existing.append("truth_ledger")
        print("  [INFO] 'truth_ledger' collection already exists")
    
    # 5. Relationships Collection
    print("\n[5/5] Creating 'relationships' collection...")
    if "relationships" not in db.list_collection_names():
        db.create_collection("relationships")
        db["relationships"].create_index([("user_id", 1), ("contact_email", 1)], unique=True)
        db["relationships"].create_index([("user_id", 1), ("importance", 1)])
        db["relationships"].create_index([("user_id", 1), ("last_contact", -1)])
        db["relationships"].create_index([("relationship_type", 1)])
        collections_created.append("relationships")
        print("  [OK] Created 'relationships' collection with indexes")
    else:
        collections_existing.append("relationships")
        print("  [INFO] 'relationships' collection already exists")
    
    db_manager.disconnect()
    
    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    
    if collections_created:
        print(f"[SUCCESS] Created {len(collections_created)} new collections:")
        for col in collections_created:
            print(f"  - {col}")
    
    if collections_existing:
        print(f"\n[INFO] {len(collections_existing)} collections already existed:")
        for col in collections_existing:
            print(f"  - {col}")
    
    print("\n[OK] Collection setup complete!")
    print("\nNext steps:")
    print("  1. Start using these collections in your code")
    print("  2. Migrate email_todos -> tasks (optional)")
    print("  3. Enhance contacts -> relationships (optional)")
    print("  4. Start tracking projects and preferences")
    
    return True


if __name__ == "__main__":
    try:
        create_collections()
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

