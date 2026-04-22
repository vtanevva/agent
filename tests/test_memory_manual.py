"""
Manual test script for User Awareness memory system
Run this while server is running to test all features
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:5000"
USER_ID = f"test-user-{int(time.time())}"
THREAD_ID = "test-thread-001"

print("=" * 60)
print("User Awareness Memory System Test")
print("=" * 60)
print(f"\nUser ID: {USER_ID}")
print(f"Thread ID: {THREAD_ID}")
print(f"Base URL: {BASE_URL}\n")

def test_health():
    """Test 1: Health Check"""
    print("\n[TEST 1] Health Check")
    print("-" * 40)
    try:
        response = requests.get(f"{BASE_URL}/memory/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_ingest_message():
    """Test 2: Ingest a Message"""
    print("\n[TEST 2] Ingest Message")
    print("-" * 40)
    try:
        payload = {
            "user_id": USER_ID,
            "thread_id": THREAD_ID,
            "channel": "test",
            "direction": "in",
            "text": "I prefer morning meetings and I work as a software engineer at TechCorp. I like async communication over phone calls."
        }
        
        response = requests.post(
            f"{BASE_URL}/memory/ingest-message",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_upload_document():
    """Test 3: Upload a Document"""
    print("\n[TEST 3] Upload Document")
    print("-" * 40)
    try:
        # Create a test document
        test_content = """
Project Requirements Document

Overview:
This project aims to build an AI assistant with memory capabilities.

Key Features:
1. Natural language understanding
2. Context awareness from past conversations
3. Document upload and semantic search (RAG)
4. Integration with email and calendar

Technical Stack:
- Backend: Python with Flask
- Database: MongoDB
- Vector Database: Pinecone
- LLM: OpenAI GPT-4

The assistant should remember user preferences and provide personalized responses.
"""
        
        # Save to temp file
        with open('temp_test_doc.txt', 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        # Upload
        with open('temp_test_doc.txt', 'rb') as f:
            files = {'file': ('test_document.txt', f, 'text/plain')}
            data = {
                'user_id': USER_ID,
                'title': 'Project Requirements Test'
            }
            
            response = requests.post(
                f"{BASE_URL}/memory/upload-file",
                files=files,
                data=data
            )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        # Clean up
        import os
        if os.path.exists('temp_test_doc.txt'):
            os.remove('temp_test_doc.txt')
        
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_list_facts():
    """Test 4: List Extracted Facts"""
    print("\n[TEST 4] List Facts (wait 5 seconds for background processing)")
    print("-" * 40)
    
    print("Waiting for background fact extraction...")
    time.sleep(5)
    
    try:
        response = requests.get(
            f"{BASE_URL}/memory/facts",
            params={"user_id": USER_ID}
        )
        
        print(f"Status: {response.status_code}")
        result = response.json()
        print(f"Facts found: {result.get('count', 0)}")
        
        if result.get('facts'):
            print("\nExtracted Facts:")
            for fact in result['facts']:
                print(f"  - {fact['text']} (type: {fact['type']}, confidence: {fact['confidence']})")
        else:
            print("No facts extracted yet (this is normal if background processing is still running)")
        
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_retrieve_context():
    """Test 5: Retrieve Context"""
    print("\n[TEST 5] Retrieve Context")
    print("-" * 40)
    try:
        response = requests.get(
            f"{BASE_URL}/memory/context",
            params={
                "user_id": USER_ID,
                "thread_id": THREAD_ID,
                "q": "project requirements"
            }
        )
        
        print(f"Status: {response.status_code}")
        result = response.json()
        
        if result.get('success'):
            stats = result.get('stats', {})
            print(f"\nContext Stats:")
            print(f"  - Facts: {stats.get('facts_count', 0)}")
            print(f"  - Summaries: {stats.get('summaries_count', 0)}")
            print(f"  - Doc Chunks: {stats.get('doc_chunks_count', 0)}")
            print(f"  - Recent Messages: {stats.get('recent_messages_count', 0)}")
            
            # Show profile summary
            profile = result.get('context', {}).get('profile_summary', '')
            if profile:
                print(f"\nProfile Summary: {profile}")
            
            # Show doc chunks
            doc_chunks = result.get('context', {}).get('doc_chunks', [])
            if doc_chunks:
                print(f"\nDocument Excerpts Found: {len(doc_chunks)}")
                for chunk in doc_chunks[:2]:  # Show first 2
                    print(f"  - Doc: {chunk.get('doc_title', 'Unknown')}")
                    print(f"    Text: {chunk.get('text', '')[:100]}...")
        else:
            print(f"Response: {json.dumps(result, indent=2)}")
        
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_add_fact_manually():
    """Test 6: Add Fact Manually"""
    print("\n[TEST 6] Add Fact Manually")
    print("-" * 40)
    try:
        payload = {
            "user_id": USER_ID,
            "text": "User prefers written documentation over verbal explanations",
            "type": "preference",
            "confidence": 0.9
        }
        
        response = requests.post(
            f"{BASE_URL}/memory/facts",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_send_multiple_messages():
    """Test 7: Send Multiple Messages (for thread summary)"""
    print("\n[TEST 7] Send Multiple Messages for Thread Summary")
    print("-" * 40)
    
    messages = [
        "Let's discuss the project timeline.",
        "We need to complete phase 1 by next week.",
        "The design mockups look great!",
        "Can you send me the latest requirements?",
        "I'll schedule a meeting for tomorrow.",
        "Thanks for the update!"
    ]
    
    try:
        for i, msg in enumerate(messages, 1):
            payload = {
                "user_id": USER_ID,
                "thread_id": THREAD_ID,
                "channel": "test",
                "direction": "in",
                "text": msg
            }
            
            response = requests.post(
                f"{BASE_URL}/memory/ingest-message",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            print(f"Message {i}/6: {response.status_code}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_thread_summary():
    """Test 8: Get Thread Summary"""
    print("\n[TEST 8] Get Thread Summary (wait 5 seconds for processing)")
    print("-" * 40)
    
    print("Waiting for background summarization...")
    time.sleep(5)
    
    try:
        response = requests.get(
            f"{BASE_URL}/memory/threads/{THREAD_ID}/summary",
            params={"user_id": USER_ID}
        )
        
        print(f"Status: {response.status_code}")
        result = response.json()
        
        if result.get('success'):
            summary = result.get('summary', {})
            print(f"\nThread Summary:")
            print(f"  Text: {summary.get('text', 'No summary yet')}")
            print(f"  Messages: {summary.get('message_count', 0)}")
            print(f"  Updated: {summary.get('updated_at', 'N/A')}")
        else:
            print(f"Response: {json.dumps(result, indent=2)}")
        
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def run_all_tests():
    """Run all tests"""
    tests = [
        ("Health Check", test_health),
        ("Ingest Message", test_ingest_message),
        ("Upload Document", test_upload_document),
        ("List Facts", test_list_facts),
        ("Retrieve Context", test_retrieve_context),
        ("Add Fact Manually", test_add_fact_manually),
        ("Send Multiple Messages", test_send_multiple_messages),
        ("Thread Summary", test_thread_summary),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ Test failed with exception: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Memory system is working!")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Check the errors above.")
    
    print(f"\nYou can now check the facts for your test user:")
    print(f"  User ID: {USER_ID}")
    print(f"  URL: {BASE_URL}/memory/facts?user_id={USER_ID}")

if __name__ == "__main__":
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")

