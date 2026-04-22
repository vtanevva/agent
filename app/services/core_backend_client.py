"""Compatibility shim — implementation in ``backend.application.services.core_backend_client``."""

from backend.application.services.core_backend_client import (  # noqa: F401
    gmail_pubsub,
    ingest_gmail,
    ingest_slack,
)

__all__ = ["ingest_gmail", "ingest_slack", "gmail_pubsub"]
