"""
Explain Backfill Results Script - Show what was extracted from each email

This script shows:
1. Each email processed and what was extracted from it
2. Facts extracted from each email
3. Tasks extracted from each email
4. Project-contact relationships created
5. Projects created

Usage:
    python scripts/explain_backfill_results.py --user_id v
    python scripts/explain_backfill_results.py --user_id v --max_emails 50
"""

import os
import sys
import argparse
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.database import DatabaseManager
from app.utils.user_email_utils import get_user_email

load_dotenv()


def format_datetime(dt):
    """Format datetime for display"""
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


def explain_backfill_results(user_id: str, max_emails: int = 100):
    """
    Show what was extracted from each email in an explainable way.
    
    Args:
        user_id: User identifier
        max_emails: Maximum number of emails to show
    """
    print("=" * 80)
    print("Backfill Results Explanation")
    print("=" * 80)
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
    
    # Get collections
    facts_col = db_manager.db["memory_facts"]
    tasks_col = db_manager.db["tasks"]
    projects_col = db_manager.db["projects"]
    relationships_col = db_manager.db["project_contact_relationships"]
    
    # Get user email for thread matching
    try:
        user_email = get_user_email(user_id)
    except:
        user_email = None
    
    # Get all facts grouped by source_ref (email thread)
    print("=" * 80)
    print("SECTION 1: FACTS EXTRACTED FROM EMAILS")
    print("=" * 80)
    print()
    
    facts_by_thread = defaultdict(list)
    all_facts = list(facts_col.find(
        {"user_id": user_id, "is_active": True},
        {"_id": 1, "fact_text": 1, "source_ref": 1, "created_at": 1}
    ).sort("created_at", -1).limit(1000))
    
    for fact in all_facts:
        source_ref = fact.get("source_ref", "")
        if source_ref.startswith("email:"):
            thread_id = source_ref.replace("email:", "")
            facts_by_thread[thread_id].append(fact)
    
    print(f"Total facts found: {len(all_facts)}")
    print(f"Facts grouped by email thread: {len(facts_by_thread)} threads")
    print()
    
    # Get all tasks from emails
    print("=" * 80)
    print("SECTION 2: TASKS EXTRACTED FROM EMAILS")
    print("=" * 80)
    print()
    
    email_tasks = list(tasks_col.find(
        {"user_id": user_id, "source": "email"},
        {"_id": 1, "title": 1, "description": 1, "source_ref": 1, "created_at": 1, "status": 1}
    ).sort("created_at", -1).limit(1000))
    
    tasks_by_thread = defaultdict(list)
    for task in email_tasks:
        source_ref = task.get("source_ref", "")
        if ":" in source_ref:
            thread_id = source_ref.split(":")[-1] if ":" in source_ref else source_ref
            tasks_by_thread[thread_id].append(task)
    
    print(f"Total email tasks found: {len(email_tasks)}")
    print()
    
    # Get all projects
    print("=" * 80)
    print("SECTION 3: PROJECTS CREATED")
    print("=" * 80)
    print()
    
    projects = list(projects_col.find(
        {"user_id": user_id},
        {"_id": 1, "name": 1, "status": 1, "related_threads": 1, "created_at": 1}
    ).sort("created_at", -1))
    
    print(f"Total projects: {len(projects)}")
    for project in projects:
        print(f"\n  📁 Project: {project.get('name', 'N/A')}")
        print(f"     Status: {project.get('status', 'N/A')}")
        print(f"     Created: {format_datetime(project.get('created_at'))}")
        related_threads = project.get("related_threads", [])
        print(f"     Related email threads: {len(related_threads)}")
        if related_threads:
            for thread_id in related_threads[:5]:  # Show first 5
                print(f"       - {thread_id}")
            if len(related_threads) > 5:
                print(f"       ... and {len(related_threads) - 5} more")
    print()
    
    # Get all project-contact relationships
    print("=" * 80)
    print("SECTION 4: PROJECT-CONTACT RELATIONSHIPS")
    print("=" * 80)
    print()
    
    relationships = list(relationships_col.find(
        {"user_id": user_id}
    ).sort("created_at", -1))
    
    print(f"Total project-contact relationships: {len(relationships)}")
    print()
    
    for idx, rel in enumerate(relationships, 1):
        print(f"  🔗 Relationship #{idx}")
        projects_list = rel.get("projects", [])
        contacts_list = rel.get("contacts", [])
        sources = rel.get("sources", [])
        notes = rel.get("notes", [])
        description = rel.get("description")
        source_message_ids = rel.get("source_message_ids", [])
        
        print(f"     Projects: {projects_list if projects_list else '(None)'}")
        print(f"     Contacts: {contacts_list if contacts_list else '(None)'}")
        print(f"     Sources: {sources if sources else '(None)'}")
        if description:
            print(f"     Description: {description}")
        if notes:
            print(f"     Notes: {notes}")
        if source_message_ids:
            print(f"     Source message IDs: {len(source_message_ids)} message(s)")
            for msg_id in source_message_ids[:3]:  # Show first 3
                print(f"       - {msg_id}")
            if len(source_message_ids) > 3:
                print(f"       ... and {len(source_message_ids) - 3} more")
        print(f"     Created: {format_datetime(rel.get('created_at'))}")
        print()
    
    # Group relationships by thread (if we can extract thread from source_message_ids)
    print("=" * 80)
    print("SECTION 5: EMAIL-BY-EMAIL BREAKDOWN")
    print("=" * 80)
    print()
    
    # Get emails from MongoDB cache
    try:
        emails_col = db_manager.db["emails"]
        messages = list(emails_col.find(
            {"user_id": user_id},
            {"thread_id": 1, "subject": 1, "from": 1, "to": 1, "date": 1, "category": 1, "snippet": 1}
        ).sort("classified_at", -1).limit(max_emails))
        
        print(f"Showing details for {len(messages)} most recent emails\n")
        
        for msg_idx, msg in enumerate(messages, 1):
            thread_id = msg.get("thread_id", "")
            subject = msg.get("subject", "(No subject)")
            sender = msg.get("from", "Unknown")
            date = msg.get("date", "")
            category = msg.get("category", "unknown")
            snippet = msg.get("snippet", "")
            
            print(f"{'=' * 80}")
            print(f"Email #{msg_idx}: {subject}")
            print(f"{'=' * 80}")
            print(f"  From: {sender}")
            print(f"  Date: {date}")
            print(f"  Category: {category}")
            print(f"  Thread ID: {thread_id}")
            if snippet:
                snippet_short = snippet[:150]
                print(f"  Snippet: {snippet_short}")
                if len(snippet) > 150:
                    print(f"           ... (truncated)")
            print()
            
            # Show facts extracted from this thread
            thread_facts = facts_by_thread.get(thread_id, [])
            if thread_facts:
                print(f"  📝 Facts extracted ({len(thread_facts)}):")
                for fact_idx, fact in enumerate(thread_facts[:10], 1):  # Show first 10
                    fact_text = fact.get("fact_text", "")[:200]  # Truncate long facts
                    print(f"     {fact_idx}. {fact_text}")
                    if len(fact_text) == 200:
                        print(f"        ... (truncated)")
                if len(thread_facts) > 10:
                    print(f"     ... and {len(thread_facts) - 10} more facts")
                print()
            else:
                print(f"  📝 Facts extracted: None")
                print()
            
            # Show tasks extracted from this thread
            thread_tasks = tasks_by_thread.get(thread_id, [])
            if thread_tasks:
                print(f"  ✅ Tasks extracted ({len(thread_tasks)}):")
                for task_idx, task in enumerate(thread_tasks, 1):
                    title = task.get("title", "Untitled")
                    status = task.get("status", "unknown")
                    desc = task.get("description", "")
                    print(f"     {task_idx}. {title} [{status}]")
                    if desc:
                        desc_short = desc[:100]
                        print(f"        {desc_short}")
                        if len(desc) > 100:
                            print(f"        ... (truncated)")
                print()
            else:
                print(f"  ✅ Tasks extracted: None")
                print()
            
            # Show if this thread is linked to a project
            linked_projects = [p for p in projects if thread_id in p.get("related_threads", [])]
            if linked_projects:
                print(f"  📁 Linked to projects:")
                for proj in linked_projects:
                    print(f"     - {proj.get('name', 'N/A')}")
                print()
            
            # Show relationships created from this thread
            thread_relationships = []
            for rel in relationships:
                source_msg_ids = rel.get("source_message_ids", [])
                # Check if any source_message_id contains this thread_id
                for msg_id in source_msg_ids:
                    if thread_id in msg_id or msg_id.startswith(thread_id):
                        thread_relationships.append(rel)
                        break
            
            if thread_relationships:
                print(f"  🔗 Project-contact relationships created ({len(thread_relationships)}):")
                for rel_idx, rel in enumerate(thread_relationships, 1):
                    projects_list = rel.get("projects", [])
                    contacts_list = rel.get("contacts", [])
                    print(f"     {rel_idx}. Projects: {projects_list if projects_list else '(None)'}")
                    print(f"        Contacts: {contacts_list if contacts_list else '(None)'}")
                print()
            else:
                print(f"  🔗 Project-contact relationships created: None")
                print()
            
            print()
            
    except Exception as e:
        print(f"[WARNING] Could not fetch email details: {e}")
        print("Showing summary only...")
        print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total facts: {len(all_facts)}")
    print(f"Total email tasks: {len(email_tasks)}")
    print(f"Total projects: {len(projects)}")
    print(f"Total project-contact relationships: {len(relationships)}")
    print()
    
    # Final section: List all project-contact relationships
    print("=" * 80)
    print("FINAL: ALL PROJECT-CONTACT RELATIONSHIPS")
    print("=" * 80)
    print()
    
    if not relationships:
        print("No project-contact relationships found.")
    else:
        # Group by project for better readability
        relationships_by_project = defaultdict(list)
        relationships_without_project = []
        
        for rel in relationships:
            projects_list = rel.get("projects", [])
            if projects_list:
                for project in projects_list:
                    relationships_by_project[project].append(rel)
            else:
                relationships_without_project.append(rel)
        
        # Show relationships grouped by project
        for project_name, rels in sorted(relationships_by_project.items()):
            print(f"📁 Project: {project_name}")
            print(f"   Relationships: {len(rels)}")
            print()
            
            for rel_idx, rel in enumerate(rels, 1):
                contacts_list = rel.get("contacts", [])
                sources = rel.get("sources", [])
                notes = rel.get("notes", [])
                description = rel.get("description")
                source_message_ids = rel.get("source_message_ids", [])
                
                print(f"   Relationship #{rel_idx}:")
                if contacts_list:
                    print(f"      Contacts: {', '.join(contacts_list)}")
                else:
                    print(f"      Contacts: (None)")
                
                if sources:
                    print(f"      Sources: {', '.join(sources)}")
                
                if description:
                    desc_short = description[:150]
                    print(f"      Description: {desc_short}")
                    if len(description) > 150:
                        print(f"                   ... (truncated)")
                
                if notes:
                    print(f"      Notes: {len(notes)} note(s)")
                    for note in notes[:3]:  # Show first 3 notes
                        note_short = note[:100]
                        print(f"         - {note_short}")
                        if len(note) > 100:
                            print(f"           ... (truncated)")
                    if len(notes) > 3:
                        print(f"         ... and {len(notes) - 3} more notes")
                
                if source_message_ids:
                    print(f"      Source messages: {len(source_message_ids)}")
                
                print(f"      Created: {format_datetime(rel.get('created_at'))}")
                print()
        
        # Show relationships without projects
        if relationships_without_project:
            print("📁 Relationships without projects:")
            print()
            for rel_idx, rel in enumerate(relationships_without_project, 1):
                contacts_list = rel.get("contacts", [])
                sources = rel.get("sources", [])
                notes = rel.get("notes", [])
                description = rel.get("description")
                
                print(f"   Relationship #{rel_idx}:")
                if contacts_list:
                    print(f"      Contacts: {', '.join(contacts_list)}")
                else:
                    print(f"      Contacts: (None)")
                
                if sources:
                    print(f"      Sources: {', '.join(sources)}")
                
                if description:
                    desc_short = description[:150]
                    print(f"      Description: {desc_short}")
                    if len(description) > 150:
                        print(f"                   ... (truncated)")
                
                if notes:
                    print(f"      Notes: {len(notes)} note(s)")
                    for note in notes[:3]:
                        note_short = note[:100]
                        print(f"         - {note_short}")
                        if len(note) > 100:
                            print(f"           ... (truncated)")
                    if len(notes) > 3:
                        print(f"         ... and {len(notes) - 3} more notes")
                
                print(f"      Created: {format_datetime(rel.get('created_at'))}")
                print()
    
    print("=" * 80)
    print()
    
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Show what was extracted from each email in an explainable way"
    )
    parser.add_argument("--user_id", required=True, help="User ID to explain backfill results for")
    parser.add_argument(
        "--max_emails",
        type=int,
        default=100,
        help="Maximum number of emails to show details for (default: 100)"
    )
    
    args = parser.parse_args()
    
    success = explain_backfill_results(
        user_id=args.user_id,
        max_emails=args.max_emails
    )
    
    sys.exit(0 if success else 1)

