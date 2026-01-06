"""Quick test to verify Gmail API connection and OAuth credentials"""
from app.utils.oauth_utils import load_google_credentials
from googleapiclient.discovery import build
import sys

def test_gmail_connection(user_id="deya"):
    """Test Gmail API connection for a user"""
    try:
        print(f"\n[TEST] Loading credentials for user: {user_id}")
        creds = load_google_credentials(user_id)
        
        if not creds:
            print("[ERROR] No credentials found!")
            print("         User needs to log in via OAuth")
            return False
        
        print("[OK] Credentials loaded")
        print(f"     Token valid: {creds.valid}")
        print(f"     Token expired: {creds.expired}")
        
        if creds.expired and creds.refresh_token:
            print("[INFO] Token expired, attempting refresh...")
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            print("[OK] Token refreshed successfully")
            
            from app.utils.oauth_utils import save_google_credentials
            save_google_credentials(user_id, creds)
            print("[OK] Saved refreshed token")
        
        print("\n[TEST] Testing Gmail API access...")
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        print("[OK] Gmail API working!")
        print(f"     Email: {profile.get('emailAddress')}")
        print(f"     Total messages: {profile.get('messagesTotal')}")
        
        print("\n[TEST] Fetching 1 email as test...")
        resp = service.users().messages().list(userId="me", maxResults=1).execute()
        messages = resp.get("messages", [])
        if messages:
            print(f"[OK] Successfully fetched {len(messages)} message(s)")
        else:
            print("[WARN] No messages found")
        
        print("\n[SUCCESS] All tests passed!")
        print("          Classification should work now")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        print("\nPossible solutions:")
        print("  1. Log out and log back in to refresh OAuth tokens")
        print("  2. Check network/firewall settings")
        print("  3. Verify GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    user_id = sys.argv[1] if len(sys.argv) > 1 else "deya"
    success = test_gmail_connection(user_id)
    sys.exit(0 if success else 1)

