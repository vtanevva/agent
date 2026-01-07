"""
Script to check user structure in MongoDB and see how user_id is being used
"""

import os
from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager

load_dotenv()

def check_users():
    """Check users collection structure"""
    print("\n" + "="*60)
    print("MongoDB Users Collection Analysis")
    print("="*60)
    
    if not Config.MONGO_URI:
        print("[ERROR] MONGO_URI not configured")
        return
    
    try:
        db_manager = DatabaseManager()
        if not db_manager.connect():
            print("[ERROR] Failed to connect to MongoDB")
            return
        
        db = db_manager.db
        if db is None:
            print("[ERROR] Database not initialized")
            return
        
        users_col = db["users"]
        users = list(users_col.find({}))
        
        print(f"\nTotal users: {len(users)}")
        print("\nUser Documents:")
        for i, user in enumerate(users, 1):
            print(f"\n  User {i}:")
            print(f"    _id: {user.get('_id')}")
            print(f"    Fields: {list(user.keys())}")
            for key, value in user.items():
                if key != '_id':
                    print(f"    {key}: {value}")
        
        # Check memory_facts to see what user_ids are used
        print("\n" + "="*60)
        print("Memory Facts - User ID Analysis")
        print("="*60)
        
        facts_col = db["memory_facts"]
        # Get distinct user_ids
        pipeline = [
            {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        user_fact_counts = list(facts_col.aggregate(pipeline))
        
        print(f"\nDistinct user_ids in memory_facts: {len(user_fact_counts)}")
        print("\nTop user_ids by fact count:")
        for item in user_fact_counts[:10]:
            print(f"  {item['_id']}: {item['count']} facts")
        
        db_manager.disconnect()
        print("\n[OK] Analysis complete")
        
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_users()

