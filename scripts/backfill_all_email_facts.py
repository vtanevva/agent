"""
Comprehensive Email Fact Backfill - Extract facts from ALL existing emails

This script processes ALL your existing emails (even already classified ones)
and extracts facts from them without storing full email bodies.

Usage:
    python scripts/backfill_all_email_facts.py

Note: This may take a while depending on how many emails you have.
      It processes in batches and shows progress.
"""

import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Initialize database connection
from app.database import init_database
print("Initializing database connection...")
init_database()
print("[OK] Database initialized\n")

from app.database import get_db
from app.services.gmail_service import extract_facts_from_email


def backfill_all_email_facts(user_id: str, batch_size: int = 50, max_emails: int = None):
    """
    Extract facts from ALL existing classified emails.
    
    Args:
        user_id: User identifier
        batch_size: Number of emails to process per batch
        max_emails: Maximum total emails to process (None = all)
    """
    print(f"[*] Starting comprehensive email fact extraction")
    print(f"    User: {user_id}")
    print(f"    Batch size: {batch_size}")
    print(f"    Max emails: {max_emails or 'ALL'}\n")
    
    try:
        # Get database
        db = get_db()
        if not db.is_connected or db.db is None:
            print("[ERROR] Database not connected!")
            return
        
        emails_col = db.db["emails"]
        
        # Count total emails
        query = {"user_id": user_id}
        total_count = emails_col.count_documents(query)
        
        print(f"[INFO] Found {total_count} emails for user {user_id}")
        
        if total_count == 0:
            print("[INFO] No emails found. Try syncing your inbox first.")
            return
        
        # Limit if specified
        limit = min(max_emails, total_count) if max_emails else total_count
        
        print(f"[*] Will process {limit} emails\n")
        
        # Process in batches
        processed = 0
        facts_extracted = 0
        
        cursor = emails_col.find(query).limit(limit)
        batch = []
        
        for email_doc in cursor:
            # Build email data structure
            email_data = {
                "thread_id": email_doc.get("thread_id"),
                "from": email_doc.get("from", ""),
                "subject": email_doc.get("subject", ""),
                "snippet": email_doc.get("snippet", ""),
                "body": email_doc.get("snippet", "")[:1000],  # Use snippet as body proxy
            }
            
            batch.append(email_data)
            
            # Process batch
            if len(batch) >= batch_size:
                print(f"[*] Processing batch {processed//batch_size + 1}...")
                
                for email in batch:
                    try:
                        # Extract facts (runs in background thread)
                        extract_facts_from_email(user_id, email)
                        processed += 1
                    except Exception as e:
                        print(f"    [WARNING] Error processing email: {e}")
                
                # Wait a bit for background threads
                import time
                time.sleep(2)
                
                print(f"    [OK] Processed {processed}/{limit} emails")
                batch = []
        
        # Process remaining emails
        if batch:
            print(f"[*] Processing final batch...")
            for email in batch:
                try:
                    extract_facts_from_email(user_id, email)
                    processed += 1
                except Exception as e:
                    print(f"    [WARNING] Error processing email: {e}")
        
        # Wait for final batch
        import time
        time.sleep(3)
        
        print(f"\n[OK] Backfill completed!")
        print(f"     Processed: {processed} emails")
        print(f"\n[INFO] Check your facts:")
        print(f"       curl http://localhost:10000/memory/facts?user_id={user_id}")
        print(f"\n[NOTE] Facts are extracted in background threads.")
        print(f"       Check server logs for 'Extracted X facts from email'")
        
    except Exception as e:
        print(f"\n[ERROR] Error during backfill: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract facts from all existing emails")
    parser.add_argument("--user-id", "-u", default="v", help="User ID (default: v)")
    parser.add_argument("--batch-size", "-b", type=int, default=50, help="Batch size (default: 50)")
    parser.add_argument("--max-emails", "-m", type=int, default=None, help="Max emails to process (default: all)")
    
    args = parser.parse_args()
    
    # Run backfill
    backfill_all_email_facts(args.user_id, args.batch_size, args.max_emails)

