"""
Centralized configuration for the core backend and migrated memory stack.

Env access should go through ``Config`` (class attributes). ``settings`` is a
backward-compatible alias for older snippets that used ``backend.config.settings``.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application + integrations configuration (core backend + memory/LLM settings)."""

    # --- Core backend (local SQLite tasks) ---
    SQLITE_PATH: str = os.getenv("SQLITE_PATH", "storage/aivis.db")

    # --- Environment & app ---
    APP_ENV: str = os.getenv("APP_ENV", "development")
    FLASK_ENV: str = os.getenv("FLASK_ENV", "development")
    FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv(
        "LOG_FORMAT",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # --- LLM ---
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.3"))
    OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "768"))
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")

    # --- Vector DB ---
    PINECONE_API_KEY: Optional[str] = os.getenv("PINECONE_API_KEY")
    PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "chatbot-facts")
    PINECONE_ENV: str = os.getenv("PINECONE_ENV", "us-east-1")

    # --- Google ---
    GOOGLE_CLIENT_SECRET_FILE: str = os.getenv("GOOGLE_SECRET_FILE", "google_client_secret.json")
    GOOGLE_SCOPES = [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.readonly",
    ]
    OAUTH_REDIRECT_URI: Optional[str] = os.getenv("OAUTH_REDIRECT_URI")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    CORE_BACKEND_URL: str = os.getenv("CORE_BACKEND_URL", "http://localhost:5000").strip()
    SLACK_WEBHOOK_SECRET: str = os.getenv("SLACK_WEBHOOK_SECRET", "").strip()

    GMAIL_PUBSUB_TOPIC: str = os.getenv("GMAIL_PUBSUB_TOPIC", "")
    GMAIL_PUBSUB_WEBHOOK_SECRET: str = os.getenv("GMAIL_PUBSUB_WEBHOOK_SECRET", "")

    # --- Microsoft ---
    MICROSOFT_CLIENT_ID: Optional[str] = os.getenv("MICROSOFT_CLIENT_ID")
    MICROSOFT_CLIENT_SECRET: Optional[str] = os.getenv("MICROSOFT_CLIENT_SECRET")
    MICROSOFT_TENANT_ID: str = os.getenv("MICROSOFT_TENANT_ID", "common")
    MICROSOFT_SCOPES = [
        "Calendars.ReadWrite",
        "Calendars.ReadWrite.Shared",
        "Mail.ReadWrite",
        "Mail.Send",
        "User.Read",
        "offline_access",
    ]

    # --- Meta / Instagram ---
    IG_APP_ID: Optional[str] = os.getenv("IG_APP_ID")
    IG_APP_SECRET: Optional[str] = os.getenv("IG_APP_SECRET")
    IG_SCOPES = ["instagram_basic", "instagram_manage_messages", "pages_show_list", "pages_messaging"]

    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))

    ENABLE_MEMORY: bool = os.getenv("ENABLE_MEMORY", "true").lower() in ("true", "1", "yes")
    ENABLE_RAG: bool = os.getenv("ENABLE_RAG", "false").lower() in ("true", "1", "yes")
    ENABLE_AUTOGEN: bool = os.getenv("ENABLE_AUTOGEN", "false").lower() in ("true", "1", "yes")

    @classmethod
    def is_production(cls) -> bool:
        return cls.APP_ENV == "production" or cls.FLASK_ENV == "production"

    @classmethod
    def is_development(cls) -> bool:
        return not cls.is_production()

    @classmethod
    def validate(cls) -> list[str]:
        missing: list[str] = []
        if not cls.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        if cls.is_production():
            if not cls.FLASK_SECRET_KEY or cls.FLASK_SECRET_KEY == "dev-secret-key-change-in-prod":
                missing.append("FLASK_SECRET_KEY (production)")
            if not cls.OAUTH_REDIRECT_URI:
                missing.append("OAUTH_REDIRECT_URI (production)")
        return missing

    @classmethod
    def get_log_level(cls) -> int:
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return level_map.get(cls.LOG_LEVEL.upper(), logging.INFO)

    @classmethod
    def print_config_summary(cls) -> None:
        print("\n" + "=" * 60)
        print("Configuration Summary")
        print("=" * 60)
        print(f"Environment: {cls.APP_ENV}")
        print(f"Debug Mode: {cls.DEBUG}")
        print(f"Log Level: {cls.LOG_LEVEL}")
        print(f"LLM Provider: {cls.LLM_PROVIDER}")
        print(f"LLM Model: {cls.OPENAI_MODEL}")
        print("MongoDB: removed (using SQLite core backend)")
        print(f"Pinecone: {'Enabled' if cls.PINECONE_API_KEY else 'Disabled'}")
        print(f"Memory: {'Enabled' if cls.ENABLE_MEMORY else 'Disabled'}")
        print(f"Rate Limiting: {'Enabled' if cls.RATE_LIMIT_ENABLED else 'Disabled'}")
        print("=" * 60 + "\n")


settings = Config()

_missing = Config.validate()
if _missing:
    print(f"WARNING: Missing required environment variables: {', '.join(_missing)}")
    if Config.is_production():
        raise ValueError(f"Missing required configuration in production: {_missing}")
