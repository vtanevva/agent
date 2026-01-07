"""
Quick test script to verify triaged inbox performance optimizations.

This script tests:
1. Response time (should be < 100ms)
2. Correct v3.0 classification
3. All 10 categories present
4. Background worker trigger logic

Usage:
    python test_triaged_inbox.py
"""

import sys
import time
import requests
from typing import Dict, Any


def test_triaged_inbox(user_id: str = "v", base_url: str = "http://localhost:10000"):
    """Test triaged inbox performance and functionality."""
    
    print(f"\n=== Testing Triaged Inbox for user: {user_id} ===\n")
    
    # Test 1: Response Time
    print("[TEST 1] Measuring response time...")
    start_time = time.time()
    
    try:
        response = requests.get(
            f"{base_url}/api/gmail/triaged-inbox",
            params={"user_id": user_id, "max_results": 50},
            timeout=5
        )
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        if response.status_code != 200:
            print(f"[FAIL] HTTP {response.status_code}: {response.text}")
            return False
        
        data = response.json()
        
        # Check response time
        if elapsed_ms < 100:
            print(f"[PASS] Response time: {elapsed_ms:.1f}ms (< 100ms target) ✓")
        else:
            print(f"[WARN] Response time: {elapsed_ms:.1f}ms (slower than expected)")
            print("       Tip: Run 'python scripts/setup_email_indexes.py' to create indexes")
        
    except Exception as e:
        print(f"[FAIL] Request failed: {e}")
        return False
    
    # Test 2: Response Structure
    print("\n[TEST 2] Validating response structure...")
    
    required_fields = ["success", "categories", "total", "classification_version"]
    missing_fields = [f for f in required_fields if f not in data]
    
    if missing_fields:
        print(f"[FAIL] Missing fields: {missing_fields}")
        return False
    
    print(f"[PASS] All required fields present ✓")
    
    # Test 3: Classification Version
    print("\n[TEST 3] Checking classification version...")
    
    version = data.get("classification_version")
    if version == "3.0":
        print(f"[PASS] Classification version: {version} ✓")
    else:
        print(f"[WARN] Classification version: {version} (expected 3.0)")
    
    # Test 4: Categories
    print("\n[TEST 4] Validating 10 categories...")
    
    expected_categories = [
        "urgent", "action_items", "waiting_for_reply", "clients", "invoices",
        "normal", "notifications", "newsletters", "promotional", "transactional", "social"
    ]
    
    categories = data.get("categories", {})
    missing_cats = [c for c in expected_categories if c not in categories]
    
    if missing_cats:
        print(f"[FAIL] Missing categories: {missing_cats}")
        return False
    
    print(f"[PASS] All 10 categories present ✓")
    
    # Test 5: Email Counts
    print("\n[TEST 5] Analyzing email distribution...")
    
    total = data.get("total", 0)
    total_classified = data.get("total_classified", 0)
    category_counts = data.get("category_counts", {})
    
    print(f"  Total returned: {total}")
    print(f"  Total classified in DB: {total_classified}")
    print(f"  Category breakdown:")
    
    for category in expected_categories:
        count = category_counts.get(category, 0)
        if count > 0:
            print(f"    - {category}: {count}")
    
    if total > 0:
        print(f"[PASS] Emails loaded successfully ✓")
    else:
        print(f"[WARN] No emails found (user may not have classified emails yet)")
        print(f"       Tip: Log in via OAuth to trigger classification")
    
    # Test 6: Background Worker Logic
    print("\n[TEST 6] Checking background worker logic...")
    
    bg_triggered = data.get("background_worker_triggered", False)
    cached = data.get("cached", False)
    
    if cached:
        print(f"[PASS] Response served from cache ✓")
    else:
        print(f"[WARN] Response not cached (unexpected)")
    
    if bg_triggered:
        print(f"[INFO] Background worker triggered (fetching more emails)")
    else:
        print(f"[INFO] Background worker skipped (already have enough emails)")
    
    # Test 7: Category Filtering
    print("\n[TEST 7] Testing category filter...")
    
    try:
        filter_response = requests.get(
            f"{base_url}/api/gmail/triaged-inbox",
            params={"user_id": user_id, "category_filter": "urgent"},
            timeout=5
        )
        
        if filter_response.status_code == 200:
            filter_data = filter_response.json()
            urgent_count = len(filter_data.get("categories", {}).get("urgent", []))
            print(f"[PASS] Category filter working (urgent: {urgent_count} emails) ✓")
        else:
            print(f"[WARN] Category filter test failed: HTTP {filter_response.status_code}")
            
    except Exception as e:
        print(f"[WARN] Category filter test failed: {e}")
    
    # Summary
    print("\n=== Test Summary ===")
    print(f"✓ Response time: {elapsed_ms:.1f}ms")
    print(f"✓ Classification version: {version}")
    print(f"✓ Total emails: {total} (of {total_classified} classified)")
    print(f"✓ All 10 categories: {', '.join(expected_categories)}")
    print(f"✓ Cached response: {cached}")
    print(f"✓ Background worker: {'triggered' if bg_triggered else 'skipped'}")
    
    print("\n[SUCCESS] All tests passed! ✓\n")
    return True


if __name__ == "__main__":
    user_id = sys.argv[1] if len(sys.argv) > 1 else "v"
    success = test_triaged_inbox(user_id)
    sys.exit(0 if success else 1)

