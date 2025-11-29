"""
Quick test script to check calendar connection status
"""

from app.database import init_database
from app.services.calendar import check_user_calendar_connections, list_calendar_events
from app.utils.oauth_utils import load_google_credentials
from app.db.collections import get_tokens_collection

def test_calendar_connection(user_id: str):
    """Test calendar connection for a specific user"""
    
    print(f"\n🔍 Testing calendar connection for user: {user_id}")
    print("=" * 60)
    
    # 1. Check MongoDB tokens collection
    print("\n1️⃣ Checking MongoDB tokens collection...")
    tokens_col = get_tokens_collection()
    if tokens_col:
        token_doc = tokens_col.find_one({"user_id": user_id})
        if token_doc:
            print(f"   ✅ Token document found")
            print(f"   Fields: {list(token_doc.keys())}")
            if "google" in token_doc:
                print(f"   ✅ Google credentials exist")
                google_data = token_doc["google"]
                print(f"   Token fields: {list(google_data.keys())}")
            else:
                print(f"   ❌ No 'google' field in token document")
        else:
            print(f"   ❌ No token document found for this user_id")
            
            # Try to find ANY token documents
            all_tokens = list(tokens_col.find({}).limit(5))
            if all_tokens:
                print(f"\n   📋 Found {len(all_tokens)} token documents in collection:")
                for token in all_tokens:
                    print(f"      - user_id: {token.get('user_id')}, fields: {list(token.keys())}")
            else:
                print(f"   ⚠️ No token documents found in collection at all")
    else:
        print(f"   ❌ Cannot access tokens collection (MongoDB not connected?)")
    
    # 2. Try to load Google credentials
    print(f"\n2️⃣ Trying to load Google credentials...")
    try:
        creds = load_google_credentials(user_id)
        if creds:
            print(f"   ✅ Credentials loaded successfully")
            print(f"   Valid: {creds.valid if hasattr(creds, 'valid') else 'unknown'}")
            print(f"   Expired: {creds.expired if hasattr(creds, 'expired') else 'unknown'}")
            print(f"   Has refresh token: {bool(creds.refresh_token) if hasattr(creds, 'refresh_token') else 'unknown'}")
        else:
            print(f"   ❌ Could not load credentials")
    except Exception as e:
        print(f"   ❌ Error loading credentials: {e}")
    
    # 3. Check connection status
    print(f"\n3️⃣ Checking connection status...")
    try:
        connections = check_user_calendar_connections(user_id)
        print(f"   Google connected: {connections.get('google_connected')}")
        print(f"   Outlook connected: {connections.get('outlook_connected')}")
        print(f"   Default provider: {connections.get('default_provider')}")
    except Exception as e:
        print(f"   ❌ Error checking connections: {e}")
    
    # 4. Try to fetch events
    print(f"\n4️⃣ Trying to fetch calendar events...")
    try:
        result = list_calendar_events(user_id=user_id, unified=True, max_results=5)
        if result.get("success"):
            events = result.get("events", [])
            print(f"   ✅ Successfully fetched {len(events)} events")
            for event in events[:3]:
                print(f"      - [{event.get('provider')}] {event.get('summary')}")
        else:
            print(f"   ❌ Failed to fetch events: {result.get('error')}")
    except Exception as e:
        print(f"   ❌ Error fetching events: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Test complete!\n")


if __name__ == "__main__":
    import sys
    
    # Initialize database
    init_database()
    
    # Get user_id from command line or use default
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
    else:
        print("Usage: python test_calendar_connection.py <user_id>")
        print("\nExample: python test_calendar_connection.py user@gmail.com")
        print("\nOr try with common user_ids:")
        
        # Try to find some user_ids in the database
        tokens_col = get_tokens_collection()
        if tokens_col:
            all_users = tokens_col.distinct("user_id")
            if all_users:
                print(f"\nFound {len(all_users)} user(s) in database:")
                for user in all_users[:5]:
                    print(f"   - {user}")
                print(f"\nTrying first user: {all_users[0]}")
                user_id = all_users[0]
            else:
                print("\n❌ No users found in tokens collection")
                sys.exit(1)
        else:
            print("\n❌ Cannot access database")
            sys.exit(1)
    
    test_calendar_connection(user_id)

