"""
MongoDB has been removed.

Kept for imports that still expect ``get_db`` / ``DatabaseManager`` from the
legacy app layer. Core persistence is SQLite under ``backend.storage``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.client: Optional[Any] = None
        self.db: Optional[Any] = None
        self.conversations: Optional[Any] = None
        self.tokens: Optional[Any] = None
        self._connected = False

    def connect(self) -> bool:
        logger.info("MongoDB removed; DatabaseManager is offline.")
        self._connected = False
        return False

    def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return False

    def health_check(self) -> bool:
        return False


db_manager = DatabaseManager()


def get_db() -> DatabaseManager:
    return db_manager


def init_database() -> bool:
    return False
