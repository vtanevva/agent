import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Centralized configuration management"""
    
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Database
    MONGO_URI: Optional[str] = os.getenv("MONGO_URI")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "mentalassistant")
    
    # Google OAuth
    GOOGLE_CLIENT_SECRET_FILE: str = os.getenv("GOOGLE_SECRET_FILE", "google_client_secret.json")
    GOOGLE_SCOPES = [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify", 
        "https://www.googleapis.com/auth/calendar.events",
    ]
    
    # Instagram/Facebook OAuth
    IG_APP_ID: Optional[str] = os.getenv("IG_APP_ID")
    IG_APP_SECRET: Optional[str] = os.getenv("IG_APP_SECRET")
    
    # Flask
    FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "")
    FLASK_ENV: str = os.getenv("FLASK_ENV", "development")
    
    # Pinecone
    PINECONE_API_KEY: Optional[str] = os.getenv("PINECONE_API_KEY")
    PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "mental-chat")
    
    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration and return list of missing items"""
        missing = []
        
        if not cls.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        
        if not cls.FLASK_SECRET_KEY:
            missing.append("FLASK_SECRET_KEY")
            
        if cls.FLASK_ENV == "production" and not cls.MONGO_URI:
            missing.append("MONGO_URI")
            
        return missing
    
    @classmethod
    def is_production(cls) -> bool:
        return cls.FLASK_ENV == "production"

# Validate configuration on import
missing_config = Config.validate()
if missing_config:
    print(f"⚠️  Missing required environment variables: {', '.join(missing_config)}")
    if Config.is_production():
        raise ValueError(f"Missing required configuration in production: {missing_config}")
