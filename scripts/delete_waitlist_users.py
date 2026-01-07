"""
Script to delete all waitlist users from the MongoDB database.
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def delete_all_waitlist_users():
    """Delete all users from the waitlist collection."""
    try:
        # Get MongoDB URI from environment
        mongo_uri = os.getenv('MONGO_URI')
        
        if not mongo_uri:
            print("❌ Error: MONGO_URI not found in environment variables")
            print("Make sure you have a .env file with MONGO_URI configured")
            return False
        
        # Connect to MongoDB
        print("🔄 Connecting to MongoDB...")
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        
        # Test connection
        client.admin.command('ping')
        print("✅ Connected to MongoDB successfully")
        
        # Get database and collection
        db = client.get_database()
        waitlist_col = db["waitlist"]
        
        # Count existing users
        count_before = waitlist_col.count_documents({})
        print(f"\n📊 Found {count_before} users in waitlist")
        
        if count_before == 0:
            print("ℹ️  No users to delete")
            return True
        
        # Ask for confirmation
        print("\n⚠️  WARNING: This will delete ALL waitlist users permanently!")
        confirmation = input("Type 'DELETE' to confirm: ").strip()
        
        if confirmation != 'DELETE':
            print("❌ Deletion cancelled")
            return False
        
        # Delete all users
        print("\n🔄 Deleting all waitlist users...")
        result = waitlist_col.delete_many({})
        
        print(f"✅ Successfully deleted {result.deleted_count} users from waitlist")
        
        # Verify deletion
        count_after = waitlist_col.count_documents({})
        print(f"📊 Remaining users in waitlist: {count_after}")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("   DELETE ALL WAITLIST USERS")
    print("=" * 60)
    delete_all_waitlist_users()
    print("\n✨ Done!")

