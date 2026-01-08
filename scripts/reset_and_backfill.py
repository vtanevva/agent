"""
Reset and Backfill Script - Delete existing data and re-process everything

This script will:
1. Delete all facts, relationships, projects, and email tasks for a user
2. Trigger comprehensive backfill to re-extract everything from emails

Usage:
    python scripts/reset_and_backfill.py --user_id v
    python scripts/reset_and_backfill.py --user_id v --max_emails 200
"""

import os
import sys
import argparse
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager

load_dotenv()


def reset_and_backfill(user_id: str, max_emails: int = 100):
    """
    Delete existing data and trigger comprehensive backfill.
    
    Args:
        user_id: User identifier
        max_emails: Maximum number of emails to process in backfill
    """
    print("=" * 70)
    print("Reset and Backfill Script")
    print("=" * 70)
    print(f"User ID: {user_id}")
    print(f"Max Emails: {max_emails}")
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    print()
    
    # Connect to database
    db_manager = DatabaseManager()
    if not db_manager.connect():
        print("[ERROR] Failed to connect to MongoDB")
        return False
    
    print("[OK] Database connected\n")
    
    if db_manager.db is None:
        print("[ERROR] Database not initialized")
        return False
    
    stats = {
        "facts_deleted": 0,
        "relationships_deleted": 0,
        "projects_deleted": 0,
        "email_tasks_deleted": 0,
    }
    
    # 1. Delete Facts
    print("[1] Deleting facts...")
    try:
        facts_col = db_manager.db["memory_facts"]
        count_before = facts_col.count_documents({"user_id": user_id})
        if count_before > 0:
            result = facts_col.delete_many({"user_id": user_id})
            stats["facts_deleted"] = result.deleted_count
            print(f"    [OK] Deleted {result.deleted_count} facts")
        else:
            print(f"    [INFO] No facts found for user '{user_id}'")
    except Exception as e:
        print(f"    [ERROR] Could not delete facts: {e}")
    print()
    
    # 2. Delete Relationships
    print("[2] Deleting relationships...")
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
        print(f"    [ERROR] Could not delete relationships: {e}")
    print()
    
    # 3. Delete Projects
    print("[3] Deleting projects...")
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
        print(f"    [ERROR] Could not delete projects: {e}")
    print()
    
    # 4. Delete Email Tasks
    print("[4] Deleting email tasks...")
    try:
        tasks_col = db_manager.db["tasks"]
        count_before = tasks_col.count_documents({"user_id": user_id, "source": "email"})
        if count_before > 0:
            result = tasks_col.delete_many({"user_id": user_id, "source": "email"})
            stats["email_tasks_deleted"] = result.deleted_count
            print(f"    [OK] Deleted {result.deleted_count} email tasks")
        else:
            print(f"    [INFO] No email tasks found for user '{user_id}'")
    except Exception as e:
        print(f"    [ERROR] Could not delete email tasks: {e}")
    print()
    
    # 5. Note about vector store
    print("[5] Vector store note...")
    try:
        from app.memory.vector_store import get_vector_store
        from app.utils.user_email_utils import get_user_email
        
        vector_store = get_vector_store()
        if vector_store.initialize():
            try:
                user_email = get_user_email(user_id)
                namespace = user_email
            except:
                namespace = user_id.lower().strip()
            
            if vector_store._index:
                try:
                    stats_data = vector_store._index.describe_index_stats()
                    if stats_data.namespaces and namespace in stats_data.namespaces:
                        namespace_stats = stats_data.namespaces[namespace]
                        vector_count = namespace_stats.get("vector_count", 0)
                        if vector_count > 0:
                            print(f"    [INFO] {vector_count} vectors exist in namespace '{namespace}'")
                            print(f"    [INFO] Vectors will be overwritten as new facts are extracted")
                except Exception as e:
                    print(f"    [WARNING] Could not check vector store: {e}")
    except Exception as e:
        print(f"    [WARNING] Could not check vector store: {e}")
    print()
    
    # Summary of deletions
    print("=" * 70)
    print("Deletion Summary")
    print("=" * 70)
    print(f"Facts deleted: {stats['facts_deleted']}")
    print(f"Relationships deleted: {stats['relationships_deleted']}")
    print(f"Projects deleted: {stats['projects_deleted']}")
    print(f"Email tasks deleted: {stats['email_tasks_deleted']}")
    print()
    
    # 6. Trigger comprehensive backfill
    print("=" * 70)
    print("[6] Triggering comprehensive backfill...")
    print("=" * 70)
    
    try:
        base_url = os.getenv("BASE_URL", "http://localhost:10000")
        backfill_url = f"{base_url}/memory/admin/backfill-comprehensive"
        
        print(f"    URL: {backfill_url}")
        print(f"    User ID: {user_id}")
        print(f"    Max Emails: {max_emails}")
        print()
        
        response = requests.post(
            backfill_url,
            json={"user_id": user_id, "max_emails": max_emails},
            timeout=1800  # 30 minutes timeout
        )
        
        if response.status_code == 200:
            print(f"    [OK] Backfill triggered successfully!")
            print(f"    [INFO] Backfill is running in background")
            print(f"    [INFO] Check server logs for progress")
            print()
            print("=" * 70)
            print("✅ Reset and backfill completed!")
            print("=" * 70)
            print()
            print("Next steps:")
            print("  - Monitor server logs for backfill progress")
            print("  - Check facts: GET /memory/facts?user_id={user_id}")
            print("  - Check relationships: GET /api/relationships?user_id={user_id}")
            print("  - Check projects: GET /api/projects?user_id={user_id}")
            return True
        else:
            print(f"    [ERROR] Backfill request failed: HTTP {response.status_code}")
            print(f"    Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"    [ERROR] Could not connect to server at {base_url}")
        print(f"    [INFO] Make sure the server is running")
        return False
    except Exception as e:
        print(f"    [ERROR] Failed to trigger backfill: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Delete existing data and trigger comprehensive backfill"
    )
    parser.add_argument("--user_id", required=True, help="User ID to reset and backfill")
    parser.add_argument(
        "--max_emails",
        type=int,
        default=100,
        help="Maximum number of emails to process (default: 100)"
    )
    
    args = parser.parse_args()
    
    # Ask for confirmation
    print("\n[WARNING] This will:")
    print(f"  - Delete ALL facts for user '{args.user_id}'")
    print(f"  - Delete ALL relationships for user '{args.user_id}'")
    print(f"  - Delete ALL projects for user '{args.user_id}'")
    print(f"  - Delete ALL email tasks for user '{args.user_id}'")
    print(f"  - Trigger comprehensive backfill to re-extract everything")
    print()
    
    response = input("Are you sure you want to continue? (yes/no): ").strip().lower()
    
    if response in ["yes", "y"]:
        success = reset_and_backfill(
            user_id=args.user_id,
            max_emails=args.max_emails
        )
        sys.exit(0 if success else 1)
    else:
        print("\n[CANCELLED] Reset and backfill aborted")
        sys.exit(1)

