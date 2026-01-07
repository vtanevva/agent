"""
Test script for memory layer integration.

Tests:
1. Email todos → tasks collection
2. Task extraction from chat
3. Relationship tracking
"""

import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager
from app.memory.models import get_tasks_collection, get_relationships_collection

# Load environment variables
load_dotenv()

# Initialize database connection
db_manager = DatabaseManager()
if not db_manager.connect():
    print("[ERROR] Failed to connect to MongoDB. Check MONGO_URI in .env")
    sys.exit(1)


def test_tasks_collection():
    """Test that tasks are being stored correctly"""
    print("\n" + "="*60)
    print("TEST 1: Tasks Collection")
    print("="*60)
    
    if not db_manager.is_connected or db_manager.db is None:
        print("[ERROR] Database not connected")
        return False
    
    # Try to get tasks collection - if helper fails, access directly
    tasks_col = get_tasks_collection()
    if tasks_col is None:
        # Try direct access
        tasks_col = db_manager.db.get_collection("tasks")
        if tasks_col is None:
            print("[ERROR] Tasks collection not available")
            return False
    
    # Get all tasks for user "v"
    user_id = "v"
    all_tasks = list(tasks_col.find({"user_id": user_id}))
    
    print(f"\n[INFO] Total tasks for user '{user_id}': {len(all_tasks)}")
    
    # Group by source
    by_source = {}
    for task in all_tasks:
        source = task.get("source", "unknown")
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(task)
    
    print("\n[INFO] Tasks by source:")
    for source, tasks in by_source.items():
        print(f"  - {source}: {len(tasks)} tasks")
        for task in tasks[:3]:  # Show first 3
            status = task.get("status", "unknown")
            priority = task.get("priority", "unknown")
            title = task.get("title", "")[:50]
            print(f"    * [{status}] {priority}: {title}")
        if len(tasks) > 3:
            print(f"    ... and {len(tasks) - 3} more")
    
    # Check email tasks specifically
    email_tasks = [t for t in all_tasks if t.get("source") == "email"]
    print(f"\n[INFO] Email tasks: {len(email_tasks)}")
    
    # Check chat tasks specifically
    chat_tasks = [t for t in all_tasks if t.get("source") == "chat"]
    print(f"[INFO] Chat tasks: {len(chat_tasks)}")
    
    return True


def test_relationships_collection():
    """Test that relationships are being tracked"""
    print("\n" + "="*60)
    print("TEST 2: Relationships Collection")
    print("="*60)
    
    if not db_manager.is_connected or db_manager.db is None:
        print("[ERROR] Database not connected")
        return False
    
    # Try to get relationships collection - if helper fails, access directly
    relationships_col = get_relationships_collection()
    if relationships_col is None:
        # Try direct access
        relationships_col = db_manager.db.get_collection("relationships")
        if relationships_col is None:
            print("[ERROR] Relationships collection not available")
            return False
    
    # Get all relationships for user "v"
    user_id = "v"
    all_relationships = list(relationships_col.find({"user_id": user_id}))
    
    print(f"\n[INFO] Total relationships for user '{user_id}': {len(all_relationships)}")
    
    if all_relationships:
        # Sort by last contact (most recent first)
        sorted_rels = sorted(
            all_relationships,
            key=lambda x: x.get("last_contact") or datetime.min,
            reverse=True
        )
        
        print("\n[INFO] All relationships (sorted by last contact):")
        print(f"\n{'Email':<40} {'Contacts':<10} {'Importance':<12} {'Type':<15} {'Last Contact':<20} {'Projects':<10}")
        print("-" * 120)
        
        for rel in sorted_rels:
            email = rel.get("contact_email", "unknown")
            count = rel.get("contact_count", 0)
            last_contact = rel.get("last_contact")
            importance = rel.get("importance", "unknown")
            rel_type = rel.get("relationship_type", "contact")
            projects = rel.get("projects", [])
            projects_str = str(len(projects)) if projects else "0"
            
            if last_contact:
                if isinstance(last_contact, datetime):
                    last_str = last_contact.strftime("%Y-%m-%d %H:%M")
                else:
                    last_str = str(last_contact)[:19]  # Truncate if too long
            else:
                last_str = "never"
            
            # Truncate email if too long
            email_display = email[:38] + ".." if len(email) > 40 else email
            
            print(f"{email_display:<40} {count:<10} {importance:<12} {rel_type:<15} {last_str:<20} {projects_str:<10}")
        
        # Summary statistics
        print("\n" + "-" * 120)
        print("\n[INFO] Summary Statistics:")
        
        # Count by importance
        by_importance = {}
        for rel in all_relationships:
            imp = rel.get("importance", "unknown")
            by_importance[imp] = by_importance.get(imp, 0) + 1
        
        print(f"  By Importance:")
        for imp, count in sorted(by_importance.items(), key=lambda x: x[1], reverse=True):
            print(f"    {imp}: {count}")
        
        # Count by relationship type
        by_type = {}
        for rel in all_relationships:
            rtype = rel.get("relationship_type", "contact")
            by_type[rtype] = by_type.get(rtype, 0) + 1
        
        print(f"  By Type:")
        for rtype, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
            print(f"    {rtype}: {count}")
        
        # Total contact count
        total_contacts = sum(rel.get("contact_count", 0) for rel in all_relationships)
        print(f"  Total Interactions: {total_contacts}")
        
        # Relationships with projects
        with_projects = sum(1 for rel in all_relationships if rel.get("projects"))
        print(f"  Relationships with Projects: {with_projects}")
        
        # Most contacted
        most_contacted = sorted(all_relationships, key=lambda x: x.get("contact_count", 0), reverse=True)[:5]
        print(f"\n  Top 5 Most Contacted:")
        for rel in most_contacted:
            email = rel.get("contact_email", "unknown")
            count = rel.get("contact_count", 0)
            print(f"    {email}: {count} contacts")
    else:
        print("\n[INFO] No relationships found yet. Process some emails to create relationships.")
    
    return True


def test_projects_collection():
    """Test that projects are being created and threads linked"""
    print("\n" + "="*60)
    print("TEST 3: Projects Collection")
    print("="*60)
    
    if not db_manager.is_connected or db_manager.db is None:
        print("[ERROR] Database not connected")
        return False
    
    # Try to get projects collection - if helper fails, access directly
    from app.memory.models import get_projects_collection
    projects_col = get_projects_collection()
    if projects_col is None:
        # Try direct access
        projects_col = db_manager.db.get_collection("projects")
        if projects_col is None:
            print("[ERROR] Projects collection not available")
            return False
    
    # Get all projects for user "v"
    user_id = "v"
    all_projects = list(projects_col.find({"user_id": user_id}))
    
    print(f"\n[INFO] Total projects for user '{user_id}': {len(all_projects)}")
    
    if all_projects:
        print("\n[INFO] Projects:")
        for project in all_projects:
            name = project.get("name", "unnamed")
            status = project.get("status", "unknown")
            threads = project.get("related_threads", [])
            last_activity = project.get("last_activity")
            
            print(f"  - {name}")
            print(f"    Status: {status}")
            print(f"    Threads: {len(threads)}")
            if last_activity:
                if isinstance(last_activity, datetime):
                    last_str = last_activity.strftime("%Y-%m-%d %H:%M")
                else:
                    last_str = str(last_activity)
                print(f"    Last activity: {last_str}")
    else:
        print("\n[INFO] No projects found yet. Process emails with project keywords to create projects.")
        print("      Keywords: project, launch, initiative, campaign, feature, release, sprint, milestone")
    
    return True


def test_email_todos_backward_compat():
    """Test that email_todos collection still works"""
    print("\n" + "="*60)
    print("TEST 3: Email Todos Backward Compatibility")
    print("="*60)
    
    if not db_manager.is_connected or db_manager.db is None:
        print("[ERROR] Database not connected")
        return False
    
    email_todos_col = db_manager.db.get_collection("email_todos")
    if email_todos_col is None:
        print("[ERROR] email_todos collection not available")
        return False
    
    user_id = "v"
    todos = list(email_todos_col.find({"user_id": user_id}).limit(5))
    
    print(f"\n[INFO] Email todos documents: {len(todos)}")
    
    for todo_doc in todos[:3]:
        thread_id = todo_doc.get("thread_id", "unknown")
        todos_list = todo_doc.get("todos", [])
        print(f"  - Thread {thread_id}: {len(todos_list)} todos")
    
    return True


def main():
    """Run all tests"""
    global db_manager
    
    print("\n" + "="*60)
    print("MEMORY LAYER INTEGRATION TESTS")
    print("="*60)
    
    # Initialize database
    db_manager = DatabaseManager()
    if not db_manager.connect():
        print("[ERROR] Failed to connect to MongoDB")
        return 1
    
    results = []
    
    # Test 1: Tasks collection
    try:
        results.append(("Tasks Collection", test_tasks_collection()))
    except Exception as e:
        print(f"[ERROR] Tasks test failed: {e}")
        results.append(("Tasks Collection", False))
    
    # Test 2: Relationships collection
    try:
        results.append(("Relationships Collection", test_relationships_collection()))
    except Exception as e:
        print(f"[ERROR] Relationships test failed: {e}")
        results.append(("Relationships Collection", False))
    
    # Test 3: Projects collection
    try:
        results.append(("Projects Collection", test_projects_collection()))
    except Exception as e:
        print(f"[ERROR] Projects test failed: {e}")
        results.append(("Projects Collection", False))
    
    # Test 4: Backward compatibility
    try:
        results.append(("Email Todos Backward Compat", test_email_todos_backward_compat()))
    except Exception as e:
        print(f"[ERROR] Backward compat test failed: {e}")
        results.append(("Email Todos Backward Compat", False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, passed in results:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {test_name}")
    
    all_passed = all(passed for _, passed in results)
    print(f"\n{'All tests passed!' if all_passed else 'Some tests failed.'}")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())

