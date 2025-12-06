import logging
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

from .config import Config

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Centralized database connection and management"""
    
    def __init__(self):
        self.client: Optional[MongoClient] = None
        self.db: Optional[Database] = None
        self.conversations: Optional[Collection] = None
        self.tokens: Optional[Collection] = None
        self._connected = False
        
    def connect(self) -> bool:
        """Establish database connection with error handling"""
        if not Config.MONGO_URI:
            logger.warning("MONGO_URI not configured - running in offline mode")
            return False
            
        try:
            self.client = MongoClient(
                Config.MONGO_URI, 
                serverSelectionTimeoutMS=5000,
                maxPoolSize=10,
                retryWrites=True
            )
            
            # Test connection
            self.client.admin.command('ping')
            
            # Initialize collections
            self.db = self.client.get_database()
            self.conversations = self.db["conversations"]
            self.tokens = self.db["tokens"]
            
            # Create indexes for performance (idempotent - safe to call multiple times)
            self._ensure_indexes()
            
            self._connected = True
            logger.info(f"✅ MongoDB connected successfully. DB={self.db.name}")
            return True
    
    def _ensure_indexes(self):
        """Create indexes for optimal query performance"""
        try:
            # Indexes for emails collection (critical for fast triaged inbox loading)
            emails_col = self.db.get_collection("emails")
            # Compound index: user_id + classified_at (descending) for fast sorted queries
            emails_col.create_index([("user_id", 1), ("classified_at", -1)])
            # Index on thread_id for lookups
            emails_col.create_index("thread_id")
            logger.info("✅ Created indexes on emails collection")
        except Exception as e:
            logger.warning(f"⚠️ Failed to create indexes (may already exist): {e}")
            
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            self._connected = False
            return False
    
    def disconnect(self):
        """Safely close database connection"""
        if self.client:
            try:
                self.client.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
            finally:
                self.client = None
                self.db = None
                self.conversations = None
                self.tokens = None
                self._connected = False
    
    @property
    def is_connected(self) -> bool:
        """Check if database is connected"""
        return self._connected and self.client is not None
    
    def health_check(self) -> bool:
        """Perform health check on database connection"""
        if not self.is_connected:
            return False
            
        try:
            self.client.admin.command('ping')
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            self._connected = False
            return False

# Global database instance
db_manager = DatabaseManager()

def get_db() -> DatabaseManager:
    """Get the global database manager instance"""
    return db_manager

def init_database() -> bool:
    """Initialize database connection on app startup"""
    return db_manager.connect()
