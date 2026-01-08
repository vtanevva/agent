"""
Memory Cleanup Script - Delete facts and cache to start fresh

This script will:
1. Delete all facts for a user
2. Delete all cache entries
3. Optionally delete relationships, projects, and tasks

Usage:
    python scripts/cleanup_memory.py --user_id v
    python scripts/cleanup_memory.py --user_id v --all  # Delete everything
    python scripts/cleanup_memory.py --user_id v --facts-only  # Only facts
    python scripts/cleanup_memory.py --user_id v --cache-only  # Only cache
"""

import os
import sys
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager
# Collections accessed directly from database manager

load_dotenv()


def cleanup_memory(user_id: str, facts_only: bool = False, cache_only: bool = False, all_data: bool = False):
    """Clean up memory data for a user"""
    
    print("=" * 70)
    print("Memory Cleanup Script")
    print("=" * 70)
    print(f"User ID: {user_id}")
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    print()
    
    # Connect to database
    db_manager = DatabaseManager()
    if not db_manager.connect():
        print("[ERROR] Failed to connect to MongoDB")
        return
    
    print("[OK] Database connected\n")
    
    if db_manager.db is None:
        print("[ERROR] Database not initialized")
        return
    
    stats = {
        "facts_deleted": 0,
        "cache_deleted": 0,
        "relationships_deleted": 0,
        "projects_deleted": 0,
        "tasks_deleted": 0,
    }
    
    # 1. Clean Facts
    if not cache_only:
        print("[1] Cleaning memory_facts collection...")
        try:
            facts_col = db_manager.db["memory_facts"]
            # Count before deletion
            count_before = facts_col.count_documents({"user_id": user_id})
            
            if count_before > 0:
                # Delete facts
                result = facts_col.delete_many({"user_id": user_id})
                stats["facts_deleted"] = result.deleted_count
                print(f"    [OK] Deleted {result.deleted_count} facts")
            else:
                print(f"    [INFO] No facts found for user '{user_id}'")
        except Exception as e:
            print(f"    [ERROR] Could not access memory_facts collection: {e}")
        print()
    
    # 2. Clean Cache
    if not facts_only:
        print("[2] Cleaning cache collection...")
        if db_manager.db is not None:
            cache_col = db_manager.db["cache"]
            # Count before deletion
            count_before = cache_col.count_documents({})
            
            if count_before > 0:
                # Delete all cache (cache is not user-specific in this schema)
                result = cache_col.delete_many({})
                stats["cache_deleted"] = result.deleted_count
                print(f"    [OK] Deleted {result.deleted_count} cache entries")
            else:
                print("    [INFO] Cache collection is already empty")
        else:
            print("    [ERROR] Database not initialized")
        print()
    
    # 3. Clean Other Collections (if --all flag)
    if all_data:
        print("[3] Cleaning other memory collections (--all flag)...")
        
        # Relationships
        try:
            relationships_col = db_manager.db["relationships"]
            count_before = relationships_col.count_documents({"user_id": user_id})
            if count_before > 0:
                result = relationships_col.delete_many({"user_id": user_id})
                stats["relationships_deleted"] = result.deleted_count
                print(f"    [OK] Deleted {result.deleted_count} relationships")
            else:
                print(f"    [INFO] No relationships found for user '{user_id}'")
        except Exception as e:
            print(f"    [ERROR] Could not access relationships collection: {e}")
        
        # Projects
        try:
            projects_col = db_manager.db["projects"]
            count_before = projects_col.count_documents({"user_id": user_id})
            if count_before > 0:
                result = projects_col.delete_many({"user_id": user_id})
                stats["projects_deleted"] = result.deleted_count
                print(f"    [OK] Deleted {result.deleted_count} projects")
            else:
                print(f"    [INFO] No projects found for user '{user_id}'")
        except Exception as e:
            print(f"    [ERROR] Could not access projects collection: {e}")
        
        # Tasks
        try:
            tasks_col = db_manager.db["tasks"]
            count_before = tasks_col.count_documents({"user_id": user_id})
            if count_before > 0:
                result = tasks_col.delete_many({"user_id": user_id})
                stats["tasks_deleted"] = result.deleted_count
                print(f"    [OK] Deleted {result.deleted_count} tasks")
            else:
                print(f"    [INFO] No tasks found for user '{user_id}'")
        except Exception as e:
            print(f"    [ERROR] Could not access tasks collection: {e}")
        
        print()
    
    # Summary
    print("=" * 70)
    print("Cleanup Summary")
    print("=" * 70)
    print(f"Facts deleted: {stats['facts_deleted']}")
    print(f"Cache deleted: {stats['cache_deleted']}")
    
    if all_data:
        print(f"Relationships deleted: {stats['relationships_deleted']}")
        print(f"Projects deleted: {stats['projects_deleted']}")
        print(f"Tasks deleted: {stats['tasks_deleted']}")
    
    total_deleted = sum(stats.values())
    print(f"\nTotal items deleted: {total_deleted}")
    
    if total_deleted > 0:
        print("\n[SUCCESS] Cleanup completed!")
        print("\nNext steps:")
        print("1. Re-login via Google OAuth to trigger fresh backfill")
        print("2. Or manually trigger backfill:")
        print(f'   curl -X POST http://localhost:10000/memory/admin/backfill-comprehensive \\')
        print(f'     -H "Content-Type: application/json" \\')
        print(f'     -d \'{{"user_id": "{user_id}", "max_emails": 100}}\'')
        print("\n[INFO] Backfill will now skip newsletters/marketing emails")
        print("       and only process important emails (action_items, urgent, clients, etc.)")
    else:
        print("\n[INFO] No data found to delete (already clean)")
    
    print("=" * 70)


def show_preview(user_id: str):
    """Show what will be deleted before actually deleting"""
    
    print("=" * 70)
    print("Memory Cleanup Preview")
    print("=" * 70)
    print(f"User ID: {user_id}")
    print()
    
    # Connect to database
    db_manager = DatabaseManager()
    if not db_manager.connect():
        print("[ERROR] Failed to connect to MongoDB")
        return
    
    print("[OK] Database connected\n")
    
    if db_manager.db is None:
        print("[ERROR] Database not initialized")
        return
    
    # Count facts
    try:
        facts_col = db_manager.db["memory_facts"]
        facts_count = facts_col.count_documents({"user_id": user_id})
        print(f"Facts: {facts_count} will be deleted")
    except Exception as e:
        print(f"Facts: Collection not accessible - {e}")
    
    # Count cache
    try:
        cache_col = db_manager.db["cache"]
        cache_count = cache_col.count_documents({})
        print(f"Cache: {cache_count} entries will be deleted")
    except Exception as e:
        print(f"Cache: Collection not accessible - {e}")
    
    # Count relationships
    try:
        relationships_col = db_manager.db["relationships"]
        relationships_count = relationships_col.count_documents({"user_id": user_id})
        print(f"Relationships: {relationships_count} (use --all to delete)")
    except Exception as e:
        print(f"Relationships: Collection not accessible - {e}")
    
    # Count projects
    try:
        projects_col = db_manager.db["projects"]
        projects_count = projects_col.count_documents({"user_id": user_id})
        print(f"Projects: {projects_count} (use --all to delete)")
    except Exception as e:
        print(f"Projects: Collection not accessible - {e}")
    
    # Count tasks
    try:
        tasks_col = db_manager.db["tasks"]
        tasks_count = tasks_col.count_documents({"user_id": user_id})
        print(f"Tasks: {tasks_count} (use --all to delete)")
    except Exception as e:
        print(f"Tasks: Collection not accessible - {e}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean up memory data to start fresh")
    parser.add_argument("--user_id", required=True, help="User ID to clean up")
    parser.add_argument("--facts-only", action="store_true", help="Only delete facts")
    parser.add_argument("--cache-only", action="store_true", help="Only delete cache")
    parser.add_argument("--all", action="store_true", help="Delete everything (facts, cache, relationships, projects, tasks)")
    parser.add_argument("--preview", action="store_true", help="Preview what will be deleted without actually deleting")
    
    args = parser.parse_args()
    
    if args.facts_only and args.cache_only:
        print("[ERROR] Cannot use --facts-only and --cache-only together")
        sys.exit(1)
    
    if args.preview:
        show_preview(args.user_id)
    else:
        # Ask for confirmation
        print("\n[WARNING] This will delete memory data!")
        if args.all:
            print("[WARNING] --all flag: Will delete facts, cache, relationships, projects, and tasks!")
        else:
            if not args.cache_only:
                print(f"[WARNING] Will delete ALL facts for user '{args.user_id}'")
            if not args.facts_only:
                print("[WARNING] Will delete ALL cache entries (affects all users)")
        
        response = input("\nAre you sure you want to continue? (yes/no): ").strip().lower()
        
        if response in ["yes", "y"]:
            cleanup_memory(
                user_id=args.user_id,
                facts_only=args.facts_only,
                cache_only=args.cache_only,
                all_data=args.all
            )
        else:
            print("\n[CANCELLED] Cleanup aborted")

