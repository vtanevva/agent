"""
Test script to check if a specific email would create a project and extract facts.

Usage:
    python scripts/test_email_processing.py --user_id v --thread_id THREAD_ID
    python scripts/test_email_processing.py --user_id v --subject "Campaign planning"
"""

import os
import sys
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager
from app.memory.models import (
    get_memory_facts_collection,
    get_projects_collection,
    get_relationships_collection
)
from app.services.gmail_service import extract_facts_from_email
from app.utils.oauth_utils import load_google_credentials

load_dotenv()


def test_email_processing(user_id: str, thread_id: str = None, subject: str = None):
    """Test if an email would create a project and extract facts"""
    
    print("=" * 70)
    print("Email Processing Test")
    print("=" * 70)
    
    db_manager = DatabaseManager()
    if not db_manager.connect():
        print("[ERROR] Failed to connect to MongoDB")
        return
    
    # Check if thread already has facts
    facts_col = get_memory_facts_collection()
    projects_col = get_projects_collection()
    
    if thread_id:
        source_ref = f"email:{thread_id}"
        
        print(f"\n[1] Checking if thread {thread_id} was already processed...")
        
        # Check facts
        existing_facts = list(facts_col.find({
            "user_id": user_id,
            "source_ref": source_ref,
            "is_active": True
        }))
        
        print(f"    Facts found: {len(existing_facts)}")
        for fact in existing_facts[:5]:
            print(f"      - {fact.get('text', '')[:80]}")
        
        # Check projects
        existing_projects = list(projects_col.find({
            "user_id": user_id,
            "related_threads": thread_id
        }))
        
        print(f"    Projects linked: {len(existing_projects)}")
        for proj in existing_projects:
            print(f"      - {proj.get('name', 'unnamed')}")
        
        if existing_facts:
            print(f"\n[INFO] Thread already processed - fact extraction would be SKIPPED")
            print(f"       (This is expected behavior with optimization)")
        else:
            print(f"\n[INFO] Thread not yet processed - fact extraction would RUN")
        
        if existing_projects:
            print(f"\n[OK] Thread is linked to {len(existing_projects)} project(s)")
        else:
            print(f"\n[INFO] Thread is NOT linked to any project")
            if subject:
                # Check if subject should create project
                project_keywords = ["project", "launch", "initiative", "campaign", "feature", "release", "sprint", "milestone"]
                subject_lower = (subject or "").lower()
                matches = [kw for kw in project_keywords if kw in subject_lower]
                if matches:
                    print(f"    Subject '{subject}' contains keywords: {matches}")
                    print(f"    [EXPECTED] Project should be created when email is processed")
                else:
                    print(f"    Subject '{subject}' does NOT contain project keywords")
                    print(f"    [INFO] Project would NOT be created automatically")
    
    print("\n" + "=" * 70)
    print("Recommendations")
    print("=" * 70)
    
    if thread_id:
        if not existing_facts:
            print("\n[ACTION] To process this email:")
            print(f"    curl -X POST http://localhost:10000/memory/admin/backfill-comprehensive \\")
            print(f"      -H 'Content-Type: application/json' \\")
            print(f"      -d '{{\"user_id\": \"{user_id}\", \"max_emails\": 10}}'")
            print(f"\n    Or manually trigger fact extraction for this thread")
        
        if not existing_projects and subject:
            project_keywords = ["project", "launch", "initiative", "campaign", "feature", "release", "sprint", "milestone"]
            if any(kw in (subject or "").lower() for kw in project_keywords):
                print(f"\n[EXPECTED] When processed, email with subject '{subject}' should create a project")
            else:
                print(f"\n[INFO] Subject '{subject}' doesn't match project keywords")
                print(f"       Project keywords: {project_keywords}")
    else:
        print("\n[INFO] Provide --thread_id or --subject to test specific email")


def check_recent_emails(user_id: str):
    """Check recent emails from Gmail to see what would be processed"""
    print("\n" + "=" * 70)
    print("Checking Recent Emails from Gmail")
    print("=" * 70)
    
    try:
        from googleapiclient.discovery import build
        from app.tools.email.extract_todos import _extract_plain_text
        
        creds = load_google_credentials(user_id)
        if not creds:
            print("[ERROR] No Google credentials found")
            return
        
        service = build("gmail", "v1", credentials=creds)
        
        # Fetch recent emails (same query as backfill)
        print("\n[INFO] Fetching recent emails (same as backfill query)...")
        resp = service.users().messages().list(
            userId="me",
            q="in:inbox -from:me",  # Same query as backfill
            maxResults=20,
        ).execute()
        
        messages = resp.get("messages", []) or []
        print(f"    Found {len(messages)} emails\n")
        
        facts_col = get_memory_facts_collection()
        projects_col = get_projects_collection()
        project_keywords = ["project", "launch", "initiative", "campaign", "feature", "release", "sprint", "milestone"]
        
        for i, msg_info in enumerate(messages[:10], 1):
            try:
                msg_id = msg_info["id"]
                full_msg = service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="full",
                ).execute()
                
                thread_id = full_msg.get("threadId")
                headers = {h["name"]: h["value"] for h in full_msg.get("payload", {}).get("headers", [])}
                subject = headers.get("Subject", "(No subject)")
                sender = headers.get("From", "")
                
                # Check if processed
                source_ref = f"email:{thread_id}"
                processed = facts_col.find_one({
                    "user_id": user_id,
                    "source_ref": source_ref,
                    "is_active": True
                })
                
                # Check project keywords
                subject_lower = subject.lower()
                matches = [kw for kw in project_keywords if kw in subject_lower]
                
                # Check if linked to project
                linked_project = projects_col.find_one({
                    "user_id": user_id,
                    "related_threads": thread_id
                })
                
                status = "[PROCESSED]" if processed else "[NOT PROCESSED]"
                project_status = f"[PROJECT: {linked_project.get('name')}]" if linked_project else "[NO PROJECT]"
                keyword_status = f"[KEYWORDS: {', '.join(matches)}]" if matches else ""
                
                print(f"{i}. {status} {project_status} {keyword_status}")
                print(f"   Subject: {subject[:60]}")
                print(f"   From: {sender[:50]}")
                print(f"   Thread: {thread_id}")
                print()
                
            except Exception as e:
                print(f"[ERROR] Failed to process message {msg_id}: {e}")
                continue
        
    except Exception as e:
        print(f"[ERROR] Failed to check Gmail: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test email processing")
    parser.add_argument("--user_id", required=True, help="User ID")
    parser.add_argument("--thread_id", help="Thread ID to test")
    parser.add_argument("--subject", help="Email subject to test")
    parser.add_argument("--check_recent", action="store_true", help="Check recent emails from Gmail")
    
    args = parser.parse_args()
    
    if args.check_recent:
        check_recent_emails(args.user_id)
    else:
        test_email_processing(args.user_id, args.thread_id, args.subject)

