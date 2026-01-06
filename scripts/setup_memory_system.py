#!/usr/bin/env python3
"""
Setup script for User Awareness memory system

This script:
1. Checks environment variables
2. Creates Pinecone index if needed
3. Creates MongoDB indexes
4. Verifies all components are working
"""

import os
import sys
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()


def check_env_vars():
    """Check required environment variables"""
    print("Checking environment variables...")
    
    required = {
        "OPENAI_API_KEY": "OpenAI API key for LLM and embeddings",
        "MONGO_URI": "MongoDB connection string",
        "PINECONE_API_KEY": "Pinecone API key for vector storage",
    }
    
    missing = []
    for var, description in required.items():
        value = os.getenv(var)
        if not value:
            missing.append(f"  - {var}: {description}")
            print(f"  ❌ {var}: Not set")
        else:
            # Mask sensitive values
            if "KEY" in var or "URI" in var:
                masked = value[:8] + "..." if len(value) > 8 else "***"
                print(f"  ✅ {var}: {masked}")
            else:
                print(f"  ✅ {var}: {value}")
    
    if missing:
        print("\n❌ Missing required environment variables:")
        for m in missing:
            print(m)
        print("\nPlease set these in your .env file")
        return False
    
    print("✅ All required environment variables are set\n")
    return True


def check_mongodb():
    """Check MongoDB connection"""
    print("Checking MongoDB connection...")
    
    try:
        from app.database import init_database
        
        success = init_database()
        if success:
            print("✅ MongoDB connected successfully\n")
            return True
        else:
            print("❌ MongoDB connection failed\n")
            return False
    except Exception as e:
        print(f"❌ MongoDB error: {e}\n")
        return False


def setup_mongodb_indexes():
    """Create MongoDB indexes for memory system"""
    print("Setting up MongoDB indexes...")
    
    try:
        from app.memory.models import ensure_indexes
        
        ensure_indexes()
        print("✅ MongoDB indexes created\n")
        return True
    except Exception as e:
        print(f"❌ Failed to create indexes: {e}\n")
        return False


def check_pinecone():
    """Check Pinecone connection and create index if needed"""
    print("Checking Pinecone connection...")
    
    try:
        from app.memory.vector_store import get_vector_store
        
        store = get_vector_store()
        success = store.initialize()
        
        if success:
            print("✅ Pinecone initialized successfully")
            
            # Get stats
            stats = store.get_stats("test-user")
            if stats:
                print(f"   Index dimension: {stats.get('dimension', 'N/A')}")
            
            print()
            return True
        else:
            print("❌ Pinecone initialization failed\n")
            return False
    except Exception as e:
        print(f"❌ Pinecone error: {e}\n")
        return False


def test_embedding():
    """Test embedding generation"""
    print("Testing embedding generation...")
    
    try:
        from app.services.llm_service import get_llm_service
        
        llm = get_llm_service()
        embedding = llm.generate_embedding("test text")
        
        if embedding and len(embedding) == 1536:
            print(f"✅ Embedding generated successfully (dimension: {len(embedding)})\n")
            return True
        else:
            print("❌ Embedding generation failed\n")
            return False
    except Exception as e:
        print(f"❌ Embedding error: {e}\n")
        return False


def create_upload_folder():
    """Create upload folder if it doesn't exist"""
    print("Checking upload folder...")
    
    upload_folder = os.getenv("UPLOAD_FOLDER", "uploads")
    
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
        print(f"✅ Created upload folder: {upload_folder}\n")
    else:
        print(f"✅ Upload folder exists: {upload_folder}\n")
    
    return True


def print_summary():
    """Print setup summary"""
    print("=" * 60)
    print("Setup Summary")
    print("=" * 60)
    print()
    print("Memory system is ready to use!")
    print()
    print("Next steps:")
    print("1. Start the server: python server.py")
    print("2. Test the system: bash scripts/test_memory_system.sh")
    print("3. Read the docs: docs/USER_AWARENESS.md")
    print()
    print("API endpoints:")
    print("- POST /memory/ingest-message")
    print("- POST /memory/upload-file")
    print("- GET /memory/context")
    print("- GET /memory/facts")
    print()
    print("=" * 60)


def main():
    """Main setup function"""
    print()
    print("=" * 60)
    print("User Awareness Memory System Setup")
    print("=" * 60)
    print()
    
    checks = [
        ("Environment Variables", check_env_vars),
        ("MongoDB Connection", check_mongodb),
        ("MongoDB Indexes", setup_mongodb_indexes),
        ("Pinecone Connection", check_pinecone),
        ("Embedding Generation", test_embedding),
        ("Upload Folder", create_upload_folder),
    ]
    
    results = []
    
    for name, check_func in checks:
        try:
            success = check_func()
            results.append((name, success))
        except Exception as e:
            print(f"❌ {name} failed with error: {e}\n")
            results.append((name, False))
    
    # Print results
    print()
    print("=" * 60)
    print("Setup Results")
    print("=" * 60)
    print()
    
    all_passed = True
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")
        if not success:
            all_passed = False
    
    print()
    
    if all_passed:
        print_summary()
        return 0
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

