"""
Compatibility wrapper: keep backend/core_app.py imports stable.
"""

from api.routes.classify import classify_bp

__all__ = ["classify_bp"]

