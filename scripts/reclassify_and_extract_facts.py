"""
Re-classify Old Emails (v3.0) + Smart Fact Extraction

This script:
1. Re-classifies existing emails using the new v3.0 classification system
2. Only extracts facts from important categories (urgent, action_items, clients, etc.)
3. Skips fact extraction for noise categories (notifications, newsletters, promotional, etc.)

Usage:
    python scripts/reclassify_and_extract_facts.py --max-emails 100

Features:
- Batch processing (efficient)
- Progress tracking
- Cost-optimized (only extracts facts from relevant emails)
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
from app.tools.email.classifier import classify_email, CLASSIFICATION_VERSION
from app.services.gmail_service import extract_facts_from_email


def reclassify_and_extract(user_id: str, max_emails: int = None, batch_size: int = 50):
    """
    Re-classify old emails and extract facts from important ones.
    
    Args:
        user_id: User identifier
        max_emails: Maximum emails to process (None = all)
        batch_size: Emails per batch
    """
    print(f"[*] Starting re-classification and fact extraction")
    print(f"    User: {user_id}")
    print(f"    Classification version: {CLASSIFICATION_VERSION}")
    print(f"    Max emails: {max_emails or 'ALL'}")
    print(f"    Batch size: {batch_size}\n")
    
    try:
        db = get_db()
        if not db.is_connected or db.db is None:
            print("[ERROR] Database not connected!")
            return
        
        emails_col = db.db["emails"]
        
        # Find emails to re-classify (old version or no version)
        query = {
            "user_id": user_id,
            "$or": [
                {"classification_version": {"$ne": CLASSIFICATION_VERSION}},
                {"classification_version": {"$exists": False}}
            ]
        }
        
        total_count = emails_col.count_documents(query)
        print(f"[INFO] Found {total_count} emails to re-classify")
        
        if total_count == 0:
            print("[INFO] All emails are up to date!")
            return
        
        limit = min(max_emails, total_count) if max_emails else total_count
        print(f"[*] Will process {limit} emails\n")
        
        # Process in batches
        processed = 0
        reclassified = 0
        facts_extracted_count = 0
        skipped_count = 0
        
        # Category counters
        category_counts = {}
        fact_extract_categories = []
        
        cursor = emails_col.find(query).limit(limit)
        batch = []
        
        for email_doc in cursor:
            batch.append(email_doc)
            
            # Process batch
            if len(batch) >= batch_size:
                print(f"[*] Processing batch {processed//batch_size + 1}...")
                
                for email in batch:
                    try:
                        thread_id = email.get("thread_id")
                        
                        # Build email data for classification
                        email_data = {
                            "threadId": thread_id,
                            "from": email.get("from", ""),
                            "subject": email.get("subject", ""),
                            "snippet": email.get("snippet", ""),
                            "body": email.get("snippet", "")[:1000],  # Use snippet as body
                        }
                        
                        # Re-classify with v3.0
                        classification = classify_email(email_data, user_id)
                        category = classification["category"]
                        
                        # Update database with new classification
                        emails_col.update_one(
                            {"user_id": user_id, "thread_id": thread_id},
                            {
                                "$set": {
                                    "category": category,
                                    "scores": classification["scores"],
                                    "classified_at": datetime.utcnow().isoformat(),
                                    "classification_version": CLASSIFICATION_VERSION,
                                }
                            }
                        )
                        
                        reclassified += 1
                        category_counts[category] = category_counts.get(category, 0) + 1
                        
                        # Check if we should extract facts
                        IMPORTANT_CATEGORIES = ['urgent', 'action_items', 'clients', 'waiting_for_reply', 'normal']
                        SKIP_CATEGORIES = ['notifications', 'newsletters', 'promotional', 'transactional', 'social', 'invoices']
                        
                        if category in IMPORTANT_CATEGORIES:
                            # Extract facts from important emails
                            email_data['category'] = category
                            extract_facts_from_email(user_id, email_data)
                            facts_extracted_count += 1
                            fact_extract_categories.append(category)
                        else:
                            skipped_count += 1
                        
                        processed += 1
                        
                    except Exception as e:
                        print(f"    [WARNING] Error processing email: {e}")
                
                # Wait for background threads
                import time
                time.sleep(2)
                
                print(f"    [OK] Processed {processed}/{limit} emails")
                print(f"         Re-classified: {reclassified}, Facts extracted: {facts_extracted_count}, Skipped: {skipped_count}")
                batch = []
        
        # Process remaining emails
        if batch:
            print(f"[*] Processing final batch...")
            for email in batch:
                try:
                    thread_id = email.get("thread_id")
                    
                    email_data = {
                        "threadId": thread_id,
                        "from": email.get("from", ""),
                        "subject": email.get("subject", ""),
                        "snippet": email.get("snippet", ""),
                        "body": email.get("snippet", "")[:1000],
                    }
                    
                    classification = classify_email(email_data, user_id)
                    category = classification["category"]
                    
                    emails_col.update_one(
                        {"user_id": user_id, "thread_id": thread_id},
                        {
                            "$set": {
                                "category": category,
                                "scores": classification["scores"],
                                "classified_at": datetime.utcnow().isoformat(),
                                "classification_version": CLASSIFICATION_VERSION,
                            }
                        }
                    )
                    
                    reclassified += 1
                    category_counts[category] = category_counts.get(category, 0) + 1
                    
                    IMPORTANT_CATEGORIES = ['urgent', 'action_items', 'clients', 'waiting_for_reply', 'normal']
                    
                    if category in IMPORTANT_CATEGORIES:
                        email_data['category'] = category
                        extract_facts_from_email(user_id, email_data)
                        facts_extracted_count += 1
                    else:
                        skipped_count += 1
                    
                    processed += 1
                    
                except Exception as e:
                    print(f"    [WARNING] Error processing email: {e}")
        
        # Wait for final batch
        import time
        time.sleep(3)
        
        print(f"\n[OK] Re-classification and fact extraction completed!")
        print(f"     Total processed: {processed}")
        print(f"     Re-classified: {reclassified}")
        print(f"     Facts extracted from: {facts_extracted_count} emails")
        print(f"     Skipped (noise): {skipped_count} emails")
        print(f"\n[INFO] Category breakdown:")
        for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            emoji = "✅" if cat in ['urgent', 'action_items', 'clients', 'waiting_for_reply', 'normal'] else "❌"
            print(f"       {emoji} {cat}: {count}")
        
        print(f"\n[INFO] Check your facts:")
        print(f"       curl http://localhost:10000/memory/facts?user_id={user_id}")
        print(f"\n[NOTE] Facts are extracted in background threads.")
        print(f"       Check server logs for 'Extracted X facts from email'")
        
    except Exception as e:
        print(f"\n[ERROR] Error during re-classification: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Re-classify emails (v3.0) and extract facts")
    parser.add_argument("--user-id", "-u", default="v", help="User ID (default: v)")
    parser.add_argument("--max-emails", "-m", type=int, default=None, help="Max emails to process (default: all)")
    parser.add_argument("--batch-size", "-b", type=int, default=50, help="Batch size (default: 50)")
    
    args = parser.parse_args()
    
    # Run re-classification
    reclassify_and_extract(args.user_id, args.max_emails, args.batch_size)

