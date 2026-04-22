"""
Compatibility wrapper: keep backend/app.py imports stable.
"""

from api.routes.sql_debug import sql_debug_bp

__all__ = ["sql_debug_bp"]

