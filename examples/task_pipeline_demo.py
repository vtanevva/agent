"""
Task Pipeline MVP Demo

This script demonstrates the Event → TaskCandidate → AivisTask pipeline.

Usage:
    python examples/task_pipeline_demo.py
"""

import sys
import os
from datetime import datetime, timedelta

# Fix Windows console encoding for emoji support
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_database
from app.services.task_pipeline_service import get_task_pipeline_service
from app.memory.task_models import ensure_task_pipeline_indexes
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def demo_gmail_task_extraction():
    """Demo: Process a Gmail email into tasks"""
    
    print("\n" + "="*80)
    print("MVP TASK PIPELINE DEMO")
    print("="*80)
    
    # Initialize database
    print("\n1. Initializing database...")
    if not init_database():
        print("❌ Failed to connect to database")
        return
    print("✅ Database connected")
    
    # Create indexes
    print("\n2. Creating task pipeline indexes...")
    ensure_task_pipeline_indexes()
    print("✅ Indexes created")
    
    # Sample email data
    print("\n3. Sample Email:")
    print("-" * 80)
    
    email_data = {
        "message_id": "msg_demo_001",
        "thread_id": "thread_demo_001",
        "sender": "sam@company.com",
        "sender_name": "Sam Chen",
        "subject": "Quick sync on Q1 presentation",
        "snippet": "Hey! Can we have a quick call tomorrow to finalize the Q1 deck?",
        "body": """Hey!

Can we have a quick call tomorrow at 2pm to finalize the Q1 presentation? 

I reviewed the latest version and it looks great, but I have a few questions about the revenue projections on slide 8. Also, we should probably add a competitive analysis section.

Let me know if 2pm works for you. If not, I'm free anytime after 3pm.

Thanks!
Sam""",
        "timestamp": datetime.utcnow(),
        "labels": ["INBOX", "UNREAD"]
    }
    
    print(f"From: {email_data['sender_name']} <{email_data['sender']}>")
    print(f"Subject: {email_data['subject']}")
    print(f"Body:\n{email_data['body']}")
    print("-" * 80)
    
    # Process through pipeline
    print("\n4. Processing through task pipeline...")
    print("   Event → TaskCandidate → AivisTask")
    
    user_id = "demo_user_123"
    pipeline = get_task_pipeline_service()
    
    task_id = pipeline.process_gmail_event(user_id, email_data)
    
    if not task_id:
        print("❌ No tasks extracted from email")
        return
    
    print(f"✅ Task created: {task_id}")
    
    # Fetch and display the task
    print("\n5. Fetching created task...")
    tasks = pipeline.get_tasks_by_priority(user_id, limit=10)
    
    if not tasks:
        print("❌ Task not found")
        return
    
    task = tasks[0]
    
    print("\n" + "="*80)
    print("AIVIS TASK (User-Facing)")
    print("="*80)
    print(f"\n📋 Title: {task['title']}")
    print(f"🚦 Priority: {task['priority']} (score: {task.get('priority_score', 0)})")
    print(f"💡 Reason: {task['reason']}")
    print(f"⏰ Due: {task.get('due_datetime', 'No deadline')}")
    print(f"📍 Status: {task['status']}")
    
    print(f"\n🎯 Available Actions:")
    for i, action in enumerate(task.get('actions', []), 1):
        print(f"   {i}. {action}")
        if action in task.get('action_metadata', {}):
            metadata = task['action_metadata'][action]
            for key, value in metadata.items():
                if isinstance(value, dict):
                    print(f"      - {key}: {value}")
                else:
                    print(f"      - {key}: {value}")
    
    print(f"\n🔗 Source: {task['source_event']}")
    print(f"🤖 Candidate: {task['task_candidate']}")
    
    # Show all tasks by priority
    print("\n" + "="*80)
    print("ALL TASKS (Grouped by Priority)")
    print("="*80)
    
    for priority in ["NOW", "SOON", "LATER"]:
        priority_tasks = pipeline.get_tasks_by_priority(user_id, priority=priority)
        if priority_tasks:
            print(f"\n🚦 {priority} ({len(priority_tasks)} tasks)")
            for t in priority_tasks:
                score = t.get('priority_score', 0)
                print(f"   • [{score}] {t['title'][:60]}")
                print(f"     Reason: {t['reason']}")
    
    print("\n" + "="*80)
    print("Demo complete!")
    print("="*80)


def demo_multiple_emails():
    """Demo: Process multiple emails to show prioritization"""
    
    print("\n" + "="*80)
    print("MULTI-EMAIL PRIORITIZATION DEMO")
    print("="*80)
    
    # Initialize
    if not init_database():
        print("❌ Failed to connect to database")
        return
    
    user_id = "demo_user_multi"
    pipeline = get_task_pipeline_service()
    
    # Sample emails with different urgencies
    emails = [
        {
            "message_id": "msg_urgent_1",
            "thread_id": "thread_urgent_1",
            "sender": "boss@company.com",
            "sender_name": "Alice Boss",
            "subject": "URGENT: Board deck needed by EOD",
            "body": "Can you send me the board deck by 5pm today? The meeting got moved up.",
            "timestamp": datetime.utcnow(),
        },
        {
            "message_id": "msg_normal_1",
            "thread_id": "thread_normal_1",
            "sender": "colleague@company.com",
            "sender_name": "Bob Colleague",
            "subject": "Lunch next week?",
            "body": "Want to grab lunch sometime next week? Let me know what works for you.",
            "timestamp": datetime.utcnow(),
        },
        {
            "message_id": "msg_info_1",
            "thread_id": "thread_info_1",
            "sender": "newsletter@tech.com",
            "sender_name": "Tech Newsletter",
            "subject": "Weekly tech roundup",
            "body": "Here's what happened in tech this week...",
            "timestamp": datetime.utcnow(),
        },
    ]
    
    print(f"\nProcessing {len(emails)} emails...\n")
    
    for email in emails:
        print(f"📧 {email['subject']}")
        task_id = pipeline.process_gmail_event(user_id, email)
        if task_id:
            print(f"   ✅ Task created: {task_id}")
        else:
            print(f"   ⚪ No task (informational email)")
    
    # Show prioritized list
    print("\n" + "="*80)
    print("PRIORITIZED TASK LIST")
    print("="*80)
    
    all_tasks = pipeline.get_tasks_by_priority(user_id)
    
    for task in all_tasks:
        emoji = {
            "NOW": "🔴",
            "SOON": "🟡",
            "LATER": "⚪"
        }.get(task['priority'], "⚪")
        
        score = task.get('priority_score', 0)
        print(f"\n{emoji} [{task['priority']}] (score: {score}) {task['title']}")
        print(f"   {task['reason']}")
        print(f"   Actions: {', '.join(task['actions'])}")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    # Run basic demo
    demo_gmail_task_extraction()
    
    # Uncomment to run multi-email demo:
    # demo_multiple_emails()
