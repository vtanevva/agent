"""
Batch extract facts from existing messages in MongoDB

Run this script to backfill facts from historical messages.
Useful for:
- Processing old messages after deploying User Awareness
- Re-processing messages after improving extraction logic
- Fixing issues where facts weren't extracted
"""

import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.memory.models import get_messages_collection, get_memory_facts_collection
from app.memory.memory_gate import get_memory_gate
from app.memory.vector_store import get_vector_store


def backfill_facts_for_user(user_id: str, limit: int = 100, min_length: int = 20):
    """
    Extract facts from existing messages for a user.
    
    Args:
        user_id: User ID to process
        limit: Max number of messages to process
        min_length: Minimum message length to consider
    
    Returns:
        dict: Statistics about the backfill
    """
    print(f"\n{'='*60}")
    print(f"Backfilling facts for user: {user_id}")
    print(f"{'='*60}\n")
    
    messages_col = get_messages_collection()
    facts_col = get_memory_facts_collection()
    
    if not messages_col or not facts_col:
        print("❌ Database not available")
        return None
    
    # Get incoming messages from user
    print(f"Fetching messages (limit: {limit})...")
    messages = list(messages_col.find(
        {
            "user_id": user_id,
            "direction": "in",  # Only user's messages, not bot responses
        },
        {"text": 1, "_id": 1, "ts": 1}
    ).sort("ts", -1).limit(limit))
    
    print(f"Found {len(messages)} messages")
    
    if not messages:
        print("No messages found for this user")
        return {
            "messages_processed": 0,
            "facts_extracted": 0,
            "facts_stored": 0,
        }
    
    # Get existing facts for deduplication
    print("Loading existing facts...")
    existing_facts = list(facts_col.find(
        {"user_id": user_id, "is_active": True},
        {"text": 1}
    ))
    print(f"Found {len(existing_facts)} existing facts")
    
    # Process each message
    gate = get_memory_gate()
    vector_store = get_vector_store()
    
    total_candidates = 0
    total_stored = 0
    processed = 0
    
    print(f"\nProcessing messages...")
    print("-" * 60)
    
    for i, msg in enumerate(messages, 1):
        text = msg.get("text", "").strip()
        
        # Skip short messages
        if len(text) < min_length:
            continue
        
        processed += 1
        message_id = msg["_id"]
        ts = msg.get("ts", datetime.utcnow())
        
        print(f"\n[{i}/{len(messages)}] Processing message: {message_id}")
        print(f"Text: {text[:100]}{'...' if len(text) > 100 else ''}")
        
        try:
            # Extract candidate facts
            candidates = gate.extract_candidate_facts(
                text=text,
                user_id=user_id,
                source_ref=message_id,
            )
            
            if not candidates:
                print("  → No facts extracted")
                continue
            
            print(f"  → Extracted {len(candidates)} candidate facts")
            total_candidates += len(candidates)
            
            # Deduplicate against existing facts
            unique = gate.deduplicate_facts(candidates, existing_facts)
            
            if len(unique) < len(candidates):
                print(f"  → {len(candidates) - len(unique)} duplicates removed")
            
            if not unique:
                print("  → All facts were duplicates")
                continue
            
            # Store unique facts
            stored = gate.store_facts(user_id, unique)
            total_stored += stored
            
            if stored > 0:
                print(f"  ✅ Stored {stored} new facts")
                
                # Add to existing facts list for deduplication
                for candidate in unique:
                    existing_facts.append({"text": candidate.text})
                
                # Embed facts to vector store
                try:
                    from uuid import uuid4
                    vectors = []
                    for candidate in unique:
                        vectors.append({
                            "id": f"fact-{uuid4().hex[:8]}",
                            "text": candidate.text,
                            "metadata": {
                                "fact_type": candidate.fact_type.value,
                                "confidence": candidate.confidence,
                            }
                        })
                    
                    if vectors:
                        vector_store.upsert_vectors(
                            user_id=user_id,
                            vectors=vectors,
                            vector_type="fact"
                        )
                        print(f"  ✅ Embedded {len(vectors)} facts to vector store")
                except Exception as e:
                    print(f"  ⚠️ Failed to embed facts: {e}")
            
        except Exception as e:
            print(f"  ❌ Error processing message: {e}")
            continue
    
    # Summary
    print(f"\n{'='*60}")
    print("Backfill Complete")
    print(f"{'='*60}")
    print(f"Messages processed: {processed}")
    print(f"Candidate facts extracted: {total_candidates}")
    print(f"New facts stored: {total_stored}")
    print(f"Existing facts (before): {len(existing_facts) - total_stored}")
    print(f"Total facts (after): {len(existing_facts)}")
    print(f"{'='*60}\n")
    
    return {
        "messages_processed": processed,
        "facts_extracted": total_candidates,
        "facts_stored": total_stored,
    }


def backfill_all_users(limit_per_user: int = 50):
    """
    Backfill facts for all users in the database.
    
    Args:
        limit_per_user: Max messages to process per user
    """
    print("\n" + "="*60)
    print("Backfilling Facts for All Users")
    print("="*60 + "\n")
    
    messages_col = get_messages_collection()
    if not messages_col:
        print("❌ Database not available")
        return
    
    # Get all unique user IDs
    print("Finding all users...")
    user_ids = messages_col.distinct("user_id")
    print(f"Found {len(user_ids)} users\n")
    
    if not user_ids:
        print("No users found in messages collection")
        return
    
    # Process each user
    total_stats = {
        "users_processed": 0,
        "total_messages": 0,
        "total_facts": 0,
    }
    
    for i, user_id in enumerate(user_ids, 1):
        print(f"\n{'='*60}")
        print(f"User {i}/{len(user_ids)}: {user_id}")
        print(f"{'='*60}")
        
        stats = backfill_facts_for_user(user_id, limit=limit_per_user)
        
        if stats:
            total_stats["users_processed"] += 1
            total_stats["total_messages"] += stats["messages_processed"]
            total_stats["total_facts"] += stats["facts_stored"]
    
    # Final summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    print(f"Users processed: {total_stats['users_processed']}")
    print(f"Total messages: {total_stats['total_messages']}")
    print(f"Total facts extracted: {total_stats['total_facts']}")
    print("="*60 + "\n")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Backfill facts from existing messages")
    parser.add_argument(
        "--user-id",
        help="Specific user ID to process (if not provided, processes all users)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of messages to process per user (default: 100)",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=20,
        help="Minimum message length to consider (default: 20)",
    )
    
    args = parser.parse_args()
    
    # Initialize database
    from app.database import init_database
    if not init_database():
        print("❌ Failed to connect to database")
        return 1
    
    # Process specific user or all users
    if args.user_id:
        backfill_facts_for_user(
            user_id=args.user_id,
            limit=args.limit,
            min_length=args.min_length
        )
    else:
        response = input("Process all users? This may take a while. (y/n): ")
        if response.lower() == 'y':
            backfill_all_users(limit_per_user=args.limit)
        else:
            print("Cancelled")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

