"""
Manually process a specific email thread to extract facts and create projects.

Usage:
    python scripts/manually_process_email.py --user_id v --thread_id THREAD_ID
    python scripts/manually_process_email.py --user_id v --subject "campaign"
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
)
from app.services.gmail_service import extract_facts_from_email
from app.utils.oauth_utils import load_google_credentials
from googleapiclient.discovery import build

load_dotenv()


def _extract_plain_text(payload):
    """Extract plain text from Gmail message payload"""
    from app.tools.email import _extract_plain_text as email_extract
    return email_extract(payload)


def find_email_by_subject(user_id: str, subject_keyword: str):
    """Find email by subject keyword"""
    print(f"\n[INFO] Searching for emails with subject containing '{subject_keyword}'...")
    
    try:
        creds = load_google_credentials(user_id)
        if not creds:
            print("[ERROR] No Google credentials found")
            return None
        
        service = build("gmail", "v1", credentials=creds)
        
        # Search for emails with keyword in subject
        query = f'subject:"{subject_keyword}" in:inbox'
        resp = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=10,
        ).execute()
        
        messages = resp.get("messages", []) or []
        print(f"[INFO] Found {len(messages)} emails matching '{subject_keyword}'")
        
        if not messages:
            return None
        
        # Get first matching email
        msg_id = messages[0]["id"]
        full_msg = service.users().messages().get(
            userId="me",
            id=msg_id,
            format="full",
        ).execute()
        
        thread_id = full_msg.get("threadId")
        headers = {h["name"]: h["value"] for h in full_msg.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "(No subject)")
        sender = headers.get("From", "")
        payload = full_msg.get("payload", {})
        body = _extract_plain_text(payload)
        
        print(f"[INFO] Found email:")
        print(f"  Thread ID: {thread_id}")
        print(f"  Subject: {subject}")
        print(f"  From: {sender}")
        print(f"  Body length: {len(body)} chars")
        
        return {
            "thread_id": thread_id,
            "subject": subject,
            "from": sender,
            "body": body[:2000],  # Limit body length
        }
        
    except Exception as e:
        print(f"[ERROR] Failed to find email: {e}")
        import traceback
        traceback.print_exc()
        return None


def manually_process_email(user_id: str, thread_id: str = None, subject_keyword: str = None):
    """Manually process a specific email to extract facts and create projects"""
    
    print("=" * 70)
    print("Manual Email Processing")
    print("=" * 70)
    
    db_manager = DatabaseManager()
    if not db_manager.connect():
        print("[ERROR] Failed to connect to MongoDB")
        return
    
    # Get email data
    email_data = None
    
    if thread_id:
        # Fetch email by thread ID
        print(f"\n[INFO] Fetching email with thread_id: {thread_id}")
        try:
            creds = load_google_credentials(user_id)
            if not creds:
                print("[ERROR] No Google credentials found")
                return
            
            service = build("gmail", "v1", credentials=creds)
            
            # Search for thread
            resp = service.users().threads().get(
                userId="me",
                id=thread_id,
                format="full",
            ).execute()
            
            messages = resp.get("messages", []) or []
            if not messages:
                print(f"[ERROR] Thread {thread_id} not found")
                return
            
            # Get first message from thread
            full_msg = messages[0]
            headers = {h["name"]: h["value"] for h in full_msg.get("payload", {}).get("headers", [])}
            subject = headers.get("Subject", "(No subject)")
            sender = headers.get("From", "")
            payload = full_msg.get("payload", {})
            body = _extract_plain_text(payload)
            
            email_data = {
                "thread_id": thread_id,
                "subject": subject,
                "from": sender,
                "body": body[:2000],
            }
            
            print(f"[INFO] Found email:")
            print(f"  Thread ID: {thread_id}")
            print(f"  Subject: {subject}")
            print(f"  From: {sender}")
            print(f"  Body length: {len(body)} chars")
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch email: {e}")
            import traceback
            traceback.print_exc()
            return
    
    elif subject_keyword:
        # Find email by subject
        email_data = find_email_by_subject(user_id, subject_keyword)
        if not email_data:
            print(f"[ERROR] No email found with subject containing '{subject_keyword}'")
            return
    
    else:
        print("[ERROR] Provide either --thread_id or --subject_keyword")
        return
    
    # Check current state
    print("\n[INFO] Checking current state...")
    facts_col = get_memory_facts_collection()
    projects_col = get_projects_collection()
    
    source_ref = f"email:{email_data['thread_id']}"
    existing_facts = list(facts_col.find({
        "user_id": user_id,
        "source_ref": source_ref,
        "is_active": True
    }))
    
    existing_projects = list(projects_col.find({
        "user_id": user_id,
        "related_threads": email_data['thread_id']
    }))
    
    print(f"  Facts found: {len(existing_facts)}")
    print(f"  Projects linked: {len(existing_projects)}")
    
    # Check if subject contains project keywords
    project_keywords = ["project", "launch", "initiative", "campaign", "feature", "release", "sprint", "milestone"]
    subject_lower = email_data['subject'].lower()
    matches = [kw for kw in project_keywords if kw in subject_lower]
    print(f"  Project keywords in subject: {matches if matches else 'None'}")
    
    # Process email
    print("\n[INFO] Processing email...")
    print("  (This will extract facts and create projects if keywords match)")
    
    try:
        # Manually trigger fact extraction and project creation
        extract_facts_from_email(user_id, email_data)
        
        # Wait a bit for background processing
        import time
        print("\n[INFO] Waiting 3 seconds for background processing...")
        time.sleep(3)
        
        # Check results
        print("\n[INFO] Checking results...")
        new_facts = list(facts_col.find({
            "user_id": user_id,
            "source_ref": source_ref,
            "is_active": True
        }))
        
        new_projects = list(projects_col.find({
            "user_id": user_id,
            "related_threads": email_data['thread_id']
        }))
        
        print(f"  Facts after processing: {len(new_facts)} (was {len(existing_facts)})")
        print(f"  Projects after processing: {len(new_projects)} (was {len(existing_projects)})")
        
        if len(new_projects) > len(existing_projects):
            print("\n[SUCCESS] Project created!")
            for proj in new_projects:
                print(f"  - {proj.get('name')}")
        elif matches:
            print("\n[WARNING] Project keywords detected but no project created yet")
            print("  Check logs for [PROJECT] messages to see why")
        else:
            print("\n[INFO] No project keywords in subject - project won't be created")
            
        if len(new_facts) > len(existing_facts):
            print(f"\n[SUCCESS] Extracted {len(new_facts) - len(existing_facts)} new facts!")
        else:
            print("\n[INFO] No new facts extracted (may have been skipped or no facts found)")
            
    except Exception as e:
        print(f"\n[ERROR] Failed to process email: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manually process an email to extract facts and create projects")
    parser.add_argument("--user_id", required=True, help="User ID")
    parser.add_argument("--thread_id", help="Thread ID to process")
    parser.add_argument("--subject_keyword", help="Subject keyword to search for")
    
    args = parser.parse_args()
    
    manually_process_email(args.user_id, args.thread_id, args.subject_keyword)

