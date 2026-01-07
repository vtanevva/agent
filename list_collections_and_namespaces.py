"""
Script to list MongoDB collections and Pinecone namespaces
"""

import os
from dotenv import load_dotenv
from app.config import Config
from app.database import DatabaseManager

load_dotenv()

def list_mongodb_collections():
    """List all MongoDB collections"""
    print("\n" + "="*60)
    print("MongoDB Collections")
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
        
        print(f"Database: {db.name}")
        print(f"MongoDB URI: {Config.MONGO_URI}")
        print("\nCollections:")
        
        collections = db.list_collection_names()
        
        if not collections:
            print("  (no collections found)")
        else:
            for i, collection_name in enumerate(sorted(collections), 1):
                collection = db[collection_name]
                count = collection.count_documents({})
                print(f"  {i}. {collection_name} ({count} documents)")
        
        db_manager.disconnect()
        print("\n[OK] MongoDB connection closed")
        
    except Exception as e:
        print(f"[ERROR] Error listing MongoDB collections: {e}")


def list_pinecone_namespaces():
    """List all Pinecone namespaces"""
    print("\n" + "="*60)
    print("Pinecone Namespaces")
    print("="*60)
    
    if not Config.PINECONE_API_KEY:
        print("[ERROR] PINECONE_API_KEY not configured")
        return
    
    try:
        from pinecone import Pinecone
        
        index_name = Config.PINECONE_INDEX_NAME
        print(f"Index Name: {index_name}")
        print(f"Environment: {Config.PINECONE_ENV}")
        
        pc = Pinecone(api_key=Config.PINECONE_API_KEY)
        
        # Check if index exists
        existing_indexes = [idx.name for idx in pc.list_indexes()]
        
        if index_name not in existing_indexes:
            print(f"[ERROR] Index '{index_name}' does not exist")
            print(f"Available indexes: {', '.join(existing_indexes) if existing_indexes else '(none)'}")
            return
        
        # Get index stats which includes namespace information
        index = pc.Index(index_name)
        stats = index.describe_index_stats()
        
        print(f"\nIndex Stats:")
        print(f"  Dimension: {stats.dimension}")
        print(f"  Index Fullness: {stats.index_fullness}")
        print(f"  Total Vector Count: {stats.total_vector_count}")
        
        namespaces = stats.namespaces
        
        if not namespaces:
            print("\nNamespaces:")
            print("  (no namespaces found)")
        else:
            print(f"\nNamespaces ({len(namespaces)} total):")
            for i, (namespace_name, namespace_stats) in enumerate(sorted(namespaces.items()), 1):
                vector_count = namespace_stats.get("vector_count", 0)
                print(f"  {i}. {namespace_name} ({vector_count} vectors)")
        
        print("\n[OK] Pinecone connection successful")
        
    except Exception as e:
        print(f"[ERROR] Error listing Pinecone namespaces: {e}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("MongoDB Collections & Pinecone Namespaces")
    print("="*60)
    
    list_mongodb_collections()
    list_pinecone_namespaces()
    
    print("\n" + "="*60)
    print("Done")
    print("="*60 + "\n")

