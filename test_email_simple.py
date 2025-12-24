"""
Simple test script to test email sending functionality.
Run this while your server is running, or it will test the email function directly.
"""
import sys
import os
import requests
import json

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_via_api():
    """Test email sending via the API endpoint."""
    print("=" * 60)
    print("Testing email via API endpoint...")
    print("=" * 60)
    
    # Change this to your server URL
    server_url = "http://aivis.pw"
    
    test_data = {
        "email": "vanesa.taneva@gmail.com",
        "name": "Test User"
    }
    
    try:
        response = requests.post(
            f"{server_url}/api/waitlist/test-email",
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("\n[SUCCESS] Email test endpoint responded successfully!")
        else:
            print(f"\n[FAILED] Email test endpoint returned error: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Could not connect to server at {server_url}")
        print("Make sure your server is running!")
        return False
    except Exception as e:
        print(f"\n[ERROR] Error calling API: {e}")
        return False
    
    return True

def test_direct():
    """Test email sending directly (without API)."""
    print("=" * 60)
    print("Testing email directly (bypassing API)...")
    print("=" * 60)
    
    try:
        from app.utils.email_resend import send_waitlist_welcome_email
        
        success = send_waitlist_welcome_email(
            to_email="vanesa.taneva@gmail.com",
            name="Test User (Direct)"
        )
        
        if success:
            print("\n[SUCCESS] Email sent directly!")
        else:
            print("\n[FAILED] Email sending returned False")
            
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    print("\nEmail Testing Script")
    print("=" * 60)
    print("\n1. Testing via API endpoint...")
    api_success = test_via_api()
    
    if not api_success:
        print("\n" + "=" * 60)
        print("\n2. Server not running or API failed. Testing directly...")
        test_direct()
    
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)

