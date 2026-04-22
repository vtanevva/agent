"""
Compatibility wrapper: keep backend/app.py imports stable.
"""

from api.routes.classify import classify_bp

__all__ = ["classify_bp"]

