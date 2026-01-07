#!/usr/bin/env python3
"""
Add Memory Namespace to Users Collection

Adds memory_namespace field to users collection with canonical format u:<userId>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager
from app.utils.oauth_utils import load_google_credentials, get_gmail_profile

load_dotenv()


def add_memory_namespace_to_users():
    """Add memory_namespace to all users"""
    
    print("=" * 70)
    print("Add Memory Namespace to Users Collection")
    print("=" * 70)
    
    if not Config.MONGO_URI:
        print("[ERROR] MONGO_URI not configured")
        return False
    
    db_manager = DatabaseManager()
    if not db_manager.connect():
        print("[ERROR] Failed to connect to MongoDB")
        return False
    
    db = db_manager.db
    if db is None:
        print("[ERROR] Database not initialized")
        return False
    
    users_col = db["users"]
    users = list(users_col.find({}))
    
    print(f"\n[INFO] Found {len(users)} users to process\n")
    
    if not users:
        print("[OK] No users found")
        db_manager.disconnect()
        return True
    
    updated_count = 0
    created_count = 0
    
    for user in users:
        user_id = user.get("user_id")
        mongodb_id = str(user["_id"])
        canonical_namespace = f"u:{mongodb_id}"
        
        # Check if already has memory_namespace
        if "memory_namespace" in user:
            existing = user["memory_namespace"]
            if existing == canonical_namespace:
                print(f"  [SKIP] {user_id}: Already has correct namespace {canonical_namespace}")
                continue
            else:
                print(f"  [UPDATE] {user_id}: Updating namespace from {existing} to {canonical_namespace}")
        else:
            print(f"  [CREATE] {user_id}: Creating namespace {canonical_namespace}")
            created_count += 1
        
        # Try to get email
        email = None
        try:
            creds = load_google_credentials(user_id)
            if creds:
                email = get_gmail_profile(creds)
        except:
            pass
        
        # Update user
        update_data = {
            "memory_namespace": canonical_namespace
        }
        
        if email:
            update_data["primary_email"] = email
        
        users_col.update_one(
            {"_id": user["_id"]},
            {"$set": update_data}
        )
        
        updated_count += 1
        print(f"    [OK] Namespace: {canonical_namespace}")
        if email:
            print(f"    [OK] Email: {email}")
    
    db_manager.disconnect()
    
    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"[SUCCESS] Updated: {updated_count} users")
    print(f"[INFO] Created: {created_count} new namespaces")
    print(f"\n[OK] All users now have memory_namespace field")
    
    return True


if __name__ == "__main__":
    try:
        add_memory_namespace_to_users()
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

