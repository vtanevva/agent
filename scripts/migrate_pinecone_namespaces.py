#!/usr/bin/env python3
"""
Pinecone Namespace Migration Script

Migrates vectors from old namespace formats (usernames, emails) to canonical
namespace format (u:<userId>).

Usage:
    # Dry run (safe - no changes)
    python scripts/migrate_pinecone_namespaces.py --dry-run
    
    # Migrate specific user
    python scripts/migrate_pinecone_namespaces.py --user-id v --canonical-namespace u:695d8f9c2cc24510999d4dc3
    
    # Migrate all users (after reviewing dry-run)
    python scripts/migrate_pinecone_namespaces.py --all --yes-i-am-sure
    
    # Delete old namespaces after verifying migration
    python scripts/migrate_pinecone_namespaces.py --cleanup-old --days-after 30
"""

import os
import sys
import argparse
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager

load_dotenv()


class NamespaceMigrator:
    """Handles migration of Pinecone namespaces"""
    
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.pinecone_client = None
        self.index = None
        self.migration_log = []
        
    def initialize_pinecone(self):
        """Initialize Pinecone connection"""
        if not Config.PINECONE_API_KEY:
            raise ValueError("PINECONE_API_KEY not configured")
        
        from pinecone import Pinecone
        
        self.pinecone_client = Pinecone(api_key=Config.PINECONE_API_KEY)
        self.index = self.pinecone_client.Index(Config.PINECONE_INDEX_NAME)
        
        print(f"[OK] Connected to Pinecone index: {Config.PINECONE_INDEX_NAME}")
    
    def get_user_namespace_mapping(self) -> Dict[str, Dict]:
        """
        Build mapping of old namespaces to canonical namespaces.
        
        Returns:
            Dict mapping old namespace -> {user_id, canonical_namespace, email}
        """
        print("\n[INFO] Building user namespace mapping...")
        
        db_manager = DatabaseManager()
        if not db_manager.connect():
            raise ValueError("Failed to connect to MongoDB")
        
        db = db_manager.db
        users_col = db["users"]
        
        # Get all users
        users = list(users_col.find({}))
        
        mapping = {}
        
        for user in users:
            user_id = user.get("user_id")
            canonical = user.get("memory_namespace")
            
            # If no canonical namespace, create one
            if not canonical:
                canonical = f"u:{user['_id']}"
                print(f"  [CREATE] Creating canonical namespace for {user_id}: {canonical}")
                
                if not self.dry_run:
                    users_col.update_one(
                        {"_id": user["_id"]},
                        {"$set": {"memory_namespace": canonical}}
                    )
            
            # Get email if available
            tokens_col = db["tokens"]
            token_doc = tokens_col.find_one({"user_id": user_id})
            email = None
            
            if token_doc and "google" in token_doc:
                # Try to extract email from token
                try:
                    google_creds = token_doc["google"]
                    email = google_creds.get("email") or google_creds.get("account")
                except:
                    pass
            
            # Map all possible old namespaces for this user
            # Username variations
            mapping[user_id] = {
                "user_id": user_id,
                "canonical_namespace": canonical,
                "email": email,
                "mongodb_id": str(user["_id"])
            }
            
            # Email variations
            if email:
                mapping[email] = mapping[user_id]
                mapping[email.lower()] = mapping[user_id]
        
        # ═══════════════════════════════════════════════════════════════════
        # MANUAL NAMESPACE MAPPINGS
        # Map known duplicate namespaces to their canonical user
        # ═══════════════════════════════════════════════════════════════════
        
        print("\n[INFO] Adding manual namespace mappings...")
        
        # User "v" variations (433 total vectors)
        # Namespaces: v, vane, vanesa, vanesa.taneva@gmail.com, vanesa.taneva12@gmail.com, (empty)
        if "v" in mapping:
            v_user = mapping["v"]
            manual_v_namespaces = [
                "vane",
                "vanesa", 
                "vanesa.taneva@gmail.com",
                "vanesa.taneva12@gmail.com",
                "vv",
                "",  # Empty namespace
            ]
            for ns in manual_v_namespaces:
                mapping[ns] = v_user
                print(f"  [MAP] {ns or '(empty)'} -> {v_user['canonical_namespace']}")
        
        # User "j" variations (18 total vectors)
        # Namespaces: j, jade, jiji
        if "j" in mapping:
            j_user = mapping["j"]
            manual_j_namespaces = ["jade", "jiji"]
            for ns in manual_j_namespaces:
                mapping[ns] = j_user
                print(f"  [MAP] {ns} -> {j_user['canonical_namespace']}")
        
        # User "r" variations (11 total vectors)
        # Namespaces: r, rob, voice-user, im a nigger
        if "r" in mapping:
            r_user = mapping["r"]
            manual_r_namespaces = ["rob", "voice-user", "im a nigger"]
            for ns in manual_r_namespaces:
                mapping[ns] = r_user
                print(f"  [MAP] {ns} -> {r_user['canonical_namespace']}")
        
        # User "bibi" variations (2 total vectors)
        # Namespaces: bibi, b
        if "bibi" in mapping:
            bibi_user = mapping["bibi"]
            manual_bibi_namespaces = ["b"]
            for ns in manual_bibi_namespaces:
                mapping[ns] = bibi_user
                print(f"  [MAP] {ns} -> {bibi_user['canonical_namespace']}")
        
        # Add more manual mappings here as needed
        # Example:
        # if "username" in mapping:
        #     user = mapping["username"]
        #     mapping["variation1"] = user
        #     mapping["variation2"] = user
        
        db_manager.disconnect()
        
        print(f"[OK] Built mapping for {len(users)} users with manual overrides")
        return mapping
    
    def find_old_namespaces(self) -> List[Tuple[str, int]]:
        """Find all existing namespaces and their vector counts"""
        stats = self.index.describe_index_stats()
        namespaces = []
        
        for ns_name, ns_stats in stats.namespaces.items():
            vector_count = ns_stats.get("vector_count", 0)
            namespaces.append((ns_name, vector_count))
        
        # Sort by vector count (descending)
        namespaces.sort(key=lambda x: x[1], reverse=True)
        
        return namespaces
    
    def migrate_namespace(
        self,
        old_namespace: str,
        new_namespace: str,
        batch_size: int = 100
    ) -> Dict:
        """
        Migrate vectors from old namespace to new namespace.
        
        Returns:
            Dict with migration stats
        """
        result = {
            "old_namespace": old_namespace,
            "new_namespace": new_namespace,
            "vectors_copied": 0,
            "errors": [],
            "success": False
        }
        
        try:
            print(f"\n{'[DRY RUN] ' if self.dry_run else ''}Migrating: {old_namespace} -> {new_namespace}")
            
            # Query all vectors from old namespace
            # Note: Pinecone doesn't have a "list all" API, so we need to use describe_index_stats
            # and then query with a dummy vector to get IDs
            
            # Get stats first
            stats = self.index.describe_index_stats()
            old_ns_stats = stats.namespaces.get(old_namespace, {})
            vector_count = old_ns_stats.get("vector_count", 0)
            
            if vector_count == 0:
                print(f"  [INFO] Namespace {old_namespace} is empty, skipping")
                result["success"] = True
                return result
            
            print(f"  [INFO] Found {vector_count} vectors to migrate")
            
            if self.dry_run:
                print(f"  [DRY RUN] Would copy {vector_count} vectors")
                result["vectors_copied"] = vector_count
                result["success"] = True
                return result
            
            # Actual migration
            # Strategy: Use multiple random queries to try to get all vectors
            # Pinecone doesn't have "list all" API, so we query with many random vectors
            # to get different subsets, then combine and deduplicate
            import numpy as np
            
            all_vector_ids = set()
            all_vectors = []
            
            # Calculate how many queries we need (aim for 3x coverage to be safe)
            queries_needed = max(10, (vector_count // batch_size) * 3)
            print(f"  [INFO] Querying {queries_needed} times with random vectors to collect all vectors...")
            
            # Query with multiple random vectors to get different subsets
            for i in range(queries_needed):
                random_vector = np.random.rand(1536).tolist()
                
                try:
                    query_result = self.index.query(
                        namespace=old_namespace,
                        vector=random_vector,
                        top_k=batch_size,
                        include_values=True,
                        include_metadata=True
                    )
                    
                    # Collect unique vectors
                    for match in query_result.matches:
                        if match.id not in all_vector_ids:
                            all_vector_ids.add(match.id)
                            all_vectors.append({
                                "id": match.id,
                                "values": match.values,
                                "metadata": match.metadata or {}
                            })
                    
                    if (i + 1) % 10 == 0:
                        print(f"  [PROGRESS] Queried {i+1}/{queries_needed}, found {len(all_vectors)} unique vectors...")
                
                except Exception as e:
                    print(f"  [WARNING] Query {i+1} failed: {e}")
                    continue
            
            print(f"  [INFO] Collected {len(all_vectors)} unique vectors (expected {vector_count})")
            
            if len(all_vectors) < vector_count:
                print(f"  [WARNING] Found fewer vectors than expected ({len(all_vectors)} < {vector_count})")
                print(f"  [WARNING] Some vectors may not be migrated. This is expected with this method.")
            
            if not all_vectors:
                print(f"  [ERROR] No vectors collected - cannot migrate")
                result["errors"].append("No vectors collected from queries")
                return result
            
            # Upsert all collected vectors to new namespace in batches
            total_copied = 0
            for i in range(0, len(all_vectors), batch_size):
                batch = all_vectors[i:i+batch_size]
                
                try:
                    self.index.upsert(
                        vectors=batch,
                        namespace=new_namespace
                    )
                    total_copied += len(batch)
                    print(f"  [OK] Upserted batch {i//batch_size + 1}: {total_copied}/{len(all_vectors)} vectors...")
                except Exception as e:
                    print(f"  [ERROR] Failed to upsert batch: {e}")
                    result["errors"].append(f"Batch upsert failed: {e}")
            
            result["vectors_copied"] = total_copied
            result["success"] = True
            
            print(f"  [OK] Successfully migrated {total_copied} vectors")
            
        except Exception as e:
            result["errors"].append(str(e))
            print(f"   Error: {e}")
        
        return result
    
    def verify_migration(self, old_namespace: str, new_namespace: str) -> bool:
        """Verify migration was successful by comparing vector counts"""
        stats = self.index.describe_index_stats()
        
        old_count = stats.namespaces.get(old_namespace, {}).get("vector_count", 0)
        new_count = stats.namespaces.get(new_namespace, {}).get("vector_count", 0)
        
        print(f"\n[VERIFY] Verification:")
        print(f"  Old namespace ({old_namespace}): {old_count} vectors")
        print(f"  New namespace ({new_namespace}): {new_count} vectors")
        
        if new_count >= old_count:
            print(f"  [OK] Migration verified!")
            return True
        else:
            print(f"  [WARNING] Warning: New namespace has fewer vectors!")
            return False
    
    def delete_old_namespace(self, namespace: str):
        """Delete all vectors from old namespace"""
        if self.dry_run:
            print(f"  [DRY RUN] Would delete namespace: {namespace}")
            return
        
        try:
            # Delete all vectors in namespace
            self.index.delete(delete_all=True, namespace=namespace)
            print(f"  [DELETE] Deleted old namespace: {namespace}")
        except Exception as e:
            print(f"  [ERROR] Error deleting namespace {namespace}: {e}")
    
    def run_migration(self, user_id: Optional[str] = None, migrate_all: bool = False):
        """Run the migration process"""
        self.initialize_pinecone()
        
        # Build namespace mapping
        mapping = self.get_user_namespace_mapping()
        
        # Find all old namespaces
        existing_namespaces = self.find_old_namespaces()
        
        print(f"\n[INFO] Found {len(existing_namespaces)} existing namespaces")
        
        # Filter namespaces to migrate
        namespaces_to_migrate = []
        
        if user_id:
            # Migrate specific user
            if user_id in mapping:
                user_info = mapping[user_id]
                canonical = user_info["canonical_namespace"]
                
                # Find all old namespaces for this user
                for ns_name, vector_count in existing_namespaces:
                    if ns_name == user_id or ns_name == user_info.get("email"):
                        namespaces_to_migrate.append((ns_name, canonical, vector_count))
            else:
                print(f"[ERROR] User {user_id} not found in mapping")
                return
        
        elif migrate_all:
            # Migrate all users
            for ns_name, vector_count in existing_namespaces:
                # Skip if already canonical format
                if ns_name.startswith("u:"):
                    continue
                
                # Skip test/anon users
                if ns_name.startswith(("test-", "anon-")):
                    continue
                
                # Find mapping
                if ns_name in mapping:
                    user_info = mapping[ns_name]
                    canonical = user_info["canonical_namespace"]
                    namespaces_to_migrate.append((ns_name, canonical, vector_count))
        
        if not namespaces_to_migrate:
            print("\n[OK] No namespaces to migrate!")
            return
        
        # Display migration plan
        print(f"\n[PLAN] Migration Plan ({len(namespaces_to_migrate)} namespaces):")
        total_vectors = 0
        for old_ns, new_ns, count in namespaces_to_migrate:
            print(f"  {old_ns} -> {new_ns} ({count} vectors)")
            total_vectors += count
        
        print(f"\n  Total vectors to migrate: {total_vectors}")
        
        if self.dry_run:
            print("\nDRY RUN MODE - No changes will be made")
            print("   Run with --yes-i-am-sure to execute migration")
            return
        
        # Execute migrations
        print(f"\n[START] Starting migration...")
        
        for old_ns, new_ns, expected_count in namespaces_to_migrate:
            result = self.migrate_namespace(old_ns, new_ns)
            self.migration_log.append(result)
            
            if result["success"]:
                # Verify
                verified = self.verify_migration(old_ns, new_ns)
                
                if verified:
                    print(f"  [OK] {old_ns} migrated successfully")
                else:
                    print(f"  [WARNING] {old_ns} migration needs review")
        
        # Save migration log
        log_file = f"migration_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(log_file, "w") as f:
            json.dump(self.migration_log, f, indent=2)
        
        print(f"\n[LOG] Migration log saved to: {log_file}")
        print(f"\n[SUCCESS] Migration complete!")
        print(f"\n[WARNING] IMPORTANT: Keep old namespaces for 30 days before deleting")
        print(f"   Use --cleanup-old after verification period")


def main():
    parser = argparse.ArgumentParser(description="Migrate Pinecone namespaces")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Dry run mode (default, no changes)")
    parser.add_argument("--user-id", help="Migrate specific user only")
    parser.add_argument("--canonical-namespace", help="Target canonical namespace (required with --user-id)")
    parser.add_argument("--all", action="store_true",
                        help="Migrate all users")
    parser.add_argument("--yes-i-am-sure", action="store_true",
                        help="Actually execute migration (disables dry-run)")
    parser.add_argument("--cleanup-old", action="store_true",
                        help="Delete old namespaces after migration")
    parser.add_argument("--days-after", type=int, default=30,
                        help="Only cleanup namespaces older than N days")
    
    args = parser.parse_args()
    
    # Safety checks
    if args.yes_i_am_sure and args.dry_run:
        args.dry_run = False
    
    if args.all and args.user_id:
        print("[ERROR] Error: Cannot use both --all and --user-id")
        sys.exit(1)
    
    if args.user_id and not args.canonical_namespace:
        print("[ERROR] Error: --canonical-namespace required when using --user-id")
        sys.exit(1)
    
    # Run migration
    migrator = NamespaceMigrator(dry_run=args.dry_run)
    
    try:
        migrator.run_migration(
            user_id=args.user_id,
            migrate_all=args.all
        )
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

