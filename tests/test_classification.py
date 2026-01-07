"""Test email classification with SSL fix"""
from app.database import init_database, get_db
from app.services.gmail_service import classify_background
from app.tools.email.classifier import CLASSIFICATION_VERSION
import time

print("=" * 60)
print("TESTING EMAIL CLASSIFICATION (WITH SSL FIX)")
print("=" * 60)

# Initialize
init_database()
user_id = "deya"

# Check before
db = get_db()
emails_col = db.db['emails']
total_before = emails_col.count_documents({'user_id': user_id})
classified_before = emails_col.count_documents({'user_id': user_id, 'classification_version': CLASSIFICATION_VERSION})

print(f"\n[BEFORE]")
print(f"  Total emails: {total_before}")
print(f"  Classified (v{CLASSIFICATION_VERSION}): {classified_before}")

# Start classification
print(f"\n[STARTING] Classifying up to 50 emails...")
print("  (This may take 1-2 minutes with reduced threading)")
result = classify_background(user_id, max_emails=50)
print(f"  API Response: {result}")

# Wait a bit for background thread
print("\n[WAITING] Giving background thread time to work (30 seconds)...")
time.sleep(30)

# Check after
classified_after = emails_col.count_documents({'user_id': user_id, 'classification_version': CLASSIFICATION_VERSION})

print(f"\n[AFTER]")
print(f"  Total emails: {total_before}")
print(f"  Classified (v{CLASSIFICATION_VERSION}): {classified_after}")
print(f"  Newly classified: {classified_after - classified_before}")

if classified_after > classified_before:
    print(f"\n[SUCCESS] Classification working! {classified_after - classified_before} emails classified")
    
    # Show category breakdown
    categories = emails_col.aggregate([
        {"$match": {"user_id": user_id, "classification_version": CLASSIFICATION_VERSION}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}}
    ])
    print(f"\n[CATEGORIES]")
    for cat in categories:
        print(f"  {cat['_id']}: {cat['count']}")
else:
    print(f"\n[WARNING] No new emails classified. Check server logs for errors.")

print("\n" + "=" * 60)

