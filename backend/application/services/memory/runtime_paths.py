"""
Import paths that work with repo root on ``sys.path`` (``from backend…``) and
with cwd ``backend/`` only (top-level ``config``, ``database``, ``utils``).
"""

from __future__ import annotations

try:
    from backend.config import Config
except ModuleNotFoundError:  # pragma: no cover
    from config import Config

try:
    from backend.database import get_db as _get_db
except ModuleNotFoundError:  # pragma: no cover
    from database import get_db as _get_db


def get_db():
    return _get_db()


try:
    from backend.utils.user_email import get_user_email
except ModuleNotFoundError:  # pragma: no cover
    from utils.user_email import get_user_email

__all__ = ["Config", "get_db", "get_user_email"]
