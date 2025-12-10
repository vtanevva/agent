"""
Centralized configuration management for the productivity assistant.

All environment variables should be accessed through this module.
This provides:
- Type safety
- Default values
- Validation
- Environment-specific behavior
"""

import os
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Centralized configuration management"""
    
    # ═══════════════════════════════════════════════════════════════════
    # Environment & App Settings
    # ═══════════════════════════════════════════════════════════════════
    
    APP_ENV: str = os.getenv("APP_ENV", "development")  # development | production
    FLASK_ENV: str = os.getenv("FLASK_ENV", "development")
    FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")  # DEBUG | INFO | WARNING | ERROR
    LOG_FORMAT: str = os.getenv(
        "LOG_FORMAT",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # ═══════════════════════════════════════════════════════════════════
    # LLM Configuration
    # ═══════════════════════════════════════════════════════════════════
    
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")  # openai | anthropic | azure
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.3"))
    OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "768"))
    
    # Embedding model
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")
    
    # ═══════════════════════════════════════════════════════════════════
    # Database Configuration
    # ═══════════════════════════════════════════════════════════════════
    
    MONGO_URI: Optional[str] = os.getenv("MONGO_URI")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "productivity-assistant")
    
    # ═══════════════════════════════════════════════════════════════════
    # Vector Database (Pinecone)
    # ═══════════════════════════════════════════════════════════════════
    
    PINECONE_API_KEY: Optional[str] = os.getenv("PINECONE_API_KEY")
    PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "chatbot-facts")
    PINECONE_ENV: str = os.getenv("PINECONE_ENV", "us-east-1")
    
    # ═══════════════════════════════════════════════════════════════════
    # Google OAuth & APIs
    # ═══════════════════════════════════════════════════════════════════
    
    GOOGLE_CLIENT_SECRET_FILE: str = os.getenv("GOOGLE_SECRET_FILE", "google_client_secret.json")
    GOOGLE_SCOPES = [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.readonly",
    ]
    
    # OAuth redirect URLs
    OAUTH_REDIRECT_URI: Optional[str] = os.getenv("OAUTH_REDIRECT_URI")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    
    # ═══════════════════════════════════════════════════════════════════
    # Microsoft/Outlook OAuth
    # ═══════════════════════════════════════════════════════════════════
    
    MICROSOFT_CLIENT_ID: Optional[str] = os.getenv("MICROSOFT_CLIENT_ID")
    MICROSOFT_CLIENT_SECRET: Optional[str] = os.getenv("MICROSOFT_CLIENT_SECRET")
    MICROSOFT_TENANT_ID: str = os.getenv("MICROSOFT_TENANT_ID", "common")  # common, organizations, consumers, or tenant ID
    MICROSOFT_SCOPES = [
        "Calendars.ReadWrite",
        "Calendars.ReadWrite.Shared",
        "User.Read",
        "offline_access",  # For refresh tokens
    ]
    
    # ═══════════════════════════════════════════════════════════════════
    # Instagram/Facebook OAuth
    # ═══════════════════════════════════════════════════════════════════
    
    IG_APP_ID: Optional[str] = os.getenv("IG_APP_ID")
    IG_APP_SECRET: Optional[str] = os.getenv("IG_APP_SECRET")
    IG_SCOPES = ["instagram_basic", "instagram_manage_messages", "pages_show_list", "pages_messaging"]
    
    # ═══════════════════════════════════════════════════════════════════
    # Rate Limiting
    # ═══════════════════════════════════════════════════════════════════
    
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")  # Enabled by default
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))  # Default: 10 requests per minute for chat (cost control)
    
    # ═══════════════════════════════════════════════════════════════════
    # Feature Flags
    # ═══════════════════════════════════════════════════════════════════
    
    ENABLE_MEMORY: bool = os.getenv("ENABLE_MEMORY", "true").lower() in ("true", "1", "yes")
    ENABLE_RAG: bool = os.getenv("ENABLE_RAG", "false").lower() in ("true", "1", "yes")
    ENABLE_AUTOGEN: bool = os.getenv("ENABLE_AUTOGEN", "false").lower() in ("true", "1", "yes")
    
    # ═══════════════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════════════
    
    @classmethod
    def is_production(cls) -> bool:
        """Check if running in production mode"""
        return cls.APP_ENV == "production" or cls.FLASK_ENV == "production"
    
    @classmethod
    def is_development(cls) -> bool:
        """Check if running in development mode"""
        return not cls.is_production()
    
    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration and return list of missing items"""
        missing = []
        
        # Always required
        if not cls.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        
        # Production-only requirements
        if cls.is_production():
            if not cls.FLASK_SECRET_KEY or cls.FLASK_SECRET_KEY == "dev-secret-key-change-in-prod":
                missing.append("FLASK_SECRET_KEY (production)")
            
            if not cls.MONGO_URI:
                missing.append("MONGO_URI (production)")
            
            if not cls.OAUTH_REDIRECT_URI:
                missing.append("OAUTH_REDIRECT_URI (production)")
        
        return missing
    
    @classmethod
    def get_log_level(cls) -> int:
        """Get logging level as int"""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return level_map.get(cls.LOG_LEVEL.upper(), logging.INFO)
    
    @classmethod
    def print_config_summary(cls):
        """Print configuration summary (safe for logs)"""
        print("\n" + "="*60)
        print("Configuration Summary")
        print("="*60)
        print(f"Environment: {cls.APP_ENV}")
        print(f"Debug Mode: {cls.DEBUG}")
        print(f"Log Level: {cls.LOG_LEVEL}")
        print(f"LLM Provider: {cls.LLM_PROVIDER}")
        print(f"LLM Model: {cls.OPENAI_MODEL}")
        print(f"MongoDB: {'Connected' if cls.MONGO_URI else 'Not configured'}")
        print(f"Pinecone: {'Enabled' if cls.PINECONE_API_KEY else 'Disabled'}")
        print(f"Memory: {'Enabled' if cls.ENABLE_MEMORY else 'Disabled'}")
        print(f"Rate Limiting: {'Enabled' if cls.RATE_LIMIT_ENABLED else 'Disabled'}")
        print("="*60 + "\n")


# ═══════════════════════════════════════════════════════════════════════
# Validate Configuration on Import
# ═══════════════════════════════════════════════════════════════════════

missing_config = Config.validate()
if missing_config:
    print(f"WARNING: Missing required environment variables: {', '.join(missing_config)}")
    if Config.is_production():
        raise ValueError(f"Missing required configuration in production: {missing_config}")
