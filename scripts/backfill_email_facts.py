"""
Email Fact Backfill - Extract facts from existing emails

This script processes your existing emails and extracts facts from them.
It works by triggering the classification system which now includes fact extraction.

Usage:
    python scripts/backfill_email_facts.py

Note: This will process up to 100 emails per run. Run multiple times for more emails.
"""

import sys
import os

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

from app.services.gmail_service import classify_background


def backfill_email_facts(user_id: str, max_emails: int = 100):
    """
    Extract facts from existing emails for a user.
    
    Args:
        user_id: User identifier
        max_emails: Maximum number of emails to process (default: 100)
    """
    print(f"[*] Starting email fact extraction for user: {user_id}")
    print(f"    Processing up to {max_emails} emails...\n")
    
    try:
        result = classify_background(user_id, max_emails=max_emails)
        
        print(f"\n[OK] Backfill completed!")
        print(f"     Result: {result}")
        print("\n[INFO] Check your facts:")
        print(f"       curl http://localhost:10000/memory/facts?user_id={user_id}")
        print("\n[TIP] Run this script multiple times to process more emails")
        
    except Exception as e:
        print(f"\n[ERROR] Error during backfill: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Configuration
    USER_ID = "v"  # Change this to your user ID
    MAX_EMAILS = 100  # Process 100 emails per run
    
    # Run backfill
    backfill_email_facts(USER_ID, MAX_EMAILS)

