#!/usr/bin/env python3
"""
Migrate email_todos to tasks collection

Moves tasks from email_todos (email-only) to unified tasks collection.
Keeps email_todos as legacy but marks it.
"""

import os
import sys
from datetime import datetime
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager
from app.memory.models import get_tasks_collection

load_dotenv()


def migrate_email_todos_to_tasks(dry_run=True):
    """Migrate email_todos to tasks collection"""
    
    print("=" * 70)
    print("Migrate email_todos -> tasks")
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
    
    email_todos_col = db["email_todos"]
    tasks_col = db["tasks"]  # Use db directly instead of helper
    
    # Get all email todos
    email_todos = list(email_todos_col.find({}))
    
    print(f"[INFO] Found {len(email_todos)} email todos to migrate\n")
    
    if not email_todos:
        print("[OK] No email todos to migrate")
        db_manager.disconnect()
        return True
    
    migrated_count = 0
    skipped_count = 0
    
    for todo_doc in email_todos:
        user_id = todo_doc.get("user_id")
        thread_id = todo_doc.get("thread_id")
        todos = todo_doc.get("todos", [])
        extracted_at = todo_doc.get("extracted_at", datetime.utcnow())
        
        if not todos:
            print(f"  [SKIP] No todos in document for user {user_id}, thread {thread_id}")
            skipped_count += 1
            continue
        
        print(f"\n[PROCESS] User: {user_id}, Thread: {thread_id}, Todos: {len(todos)}")
        
        for i, todo_item in enumerate(todos):
            # Extract task info from todo
            todo_text = todo_item
            if isinstance(todo_item, dict):
                todo_text = todo_item.get("text", str(todo_item))
            
            task = {
                "_id": str(uuid4()),
                "user_id": user_id,
                "title": todo_text[:200],  # Limit title length
                "description": todo_text if len(todo_text) > 200 else None,
                "status": "pending",
                "priority": "medium",
                "source": "email",
                "source_ref": thread_id,
                "created_at": extracted_at,
                "updated_at": datetime.utcnow()
            }
            
            if dry_run:
                print(f"  [DRY-RUN] Would create task: {task['title'][:50]}...")
            else:
                # Check if task already exists (avoid duplicates)
                existing = tasks_col.find_one({
                    "user_id": user_id,
                    "source": "email",
                    "source_ref": thread_id,
                    "title": task["title"]
                })
                
                if existing:
                    print(f"  [SKIP] Task already exists: {task['title'][:50]}...")
                    skipped_count += 1
                    continue
                
                tasks_col.insert_one(task)
                print(f"  [OK] Created task: {task['title'][:50]}...")
                migrated_count += 1
    
    # Mark email_todos as legacy (optional - add a field)
    if not dry_run and migrated_count > 0:
        # Add legacy marker to email_todos collection
        # We'll just leave it as-is, but document it as legacy
        print(f"\n[INFO] email_todos collection is now legacy")
        print(f"       New tasks should be written to 'tasks' collection")
    
    db_manager.disconnect()
    
    # Summary
    print("\n" + "=" * 70)
    print("Migration Summary")
    print("=" * 70)
    
    if dry_run:
        print(f"[DRY-RUN] Would migrate: {migrated_count} tasks")
        print(f"[DRY-RUN] Would skip: {skipped_count} tasks")
        print("\n[INFO] Run with --execute to perform migration")
    else:
        print(f"[SUCCESS] Migrated: {migrated_count} tasks")
        print(f"[INFO] Skipped: {skipped_count} tasks")
        print(f"\n[OK] Migration complete!")
        print(f"\n[IMPORTANT] Going forward, write new tasks to 'tasks' collection")
        print(f"            email_todos is now legacy (kept for reference)")
    
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate email_todos to tasks")
    parser.add_argument("--execute", action="store_true",
                        help="Actually perform migration (default is dry-run)")
    
    args = parser.parse_args()
    
    try:
        migrate_email_todos_to_tasks(dry_run=not args.execute)
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

