"""
Simple caching service using MongoDB.
No Redis required - uses your existing MongoDB.

This provides fast caching for:
- Gmail API responses (email lists, thread details)
- Email style analysis results
- Calendar events
- Contact lookups
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Any, Optional, Dict
from app.db.collections import get_db
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)

# Default TTLs (in seconds)
CACHE_TTL_EMAIL_LIST = 300  # 5 minutes
CACHE_TTL_EMAIL_STYLE = 86400  # 24 hours
CACHE_TTL_CALENDAR = 300  # 5 minutes
CACHE_TTL_THREAD_DETAIL = 600  # 10 minutes


def _get_cache_collection():
    """Get or create cache collection."""
    db = get_db()
    if db and db.is_connected:
        return db.db.get_collection("cache")
    return None


def _make_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a cache key from prefix and arguments."""
    key_parts = [prefix]
    key_parts.extend(str(arg) for arg in args)
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    key_string = "|".join(key_parts)
    # Hash if too long (MongoDB key limit)
    if len(key_string) > 200:
        key_string = hashlib.md5(key_string.encode()).hexdigest()
    return f"{prefix}:{key_string}"


def cache_get(key: str, default: Any = None) -> Optional[Any]:
    """
    Get value from cache.
    
    Parameters
    ----------
    key : str
        Cache key
    default : Any
        Default value if not found or expired
        
    Returns
    -------
    Any or None
        Cached value or default
    """
    cache_col = _get_cache_collection()
    if not cache_col:
        return default
    
    try:
        doc = cache_col.find_one({"key": key})
        if not doc:
            return default
        
        # Check expiration
        expires_at = doc.get("expires_at")
        if expires_at and datetime.utcnow() > expires_at:
            # Expired - delete it
            cache_col.delete_one({"key": key})
            return default
        
        # Return cached value
        value = doc.get("value")
        logger.debug(f"Cache HIT: {key[:50]}")
        return value
    except Exception as e:
        logger.warning(f"Cache get error: {e}")
        return default


def cache_set(key: str, value: Any, ttl: int = 3600) -> bool:
    """
    Set value in cache with TTL.
    
    Parameters
    ----------
    key : str
        Cache key
    value : Any
        Value to cache (must be JSON serializable)
    ttl : int
        Time to live in seconds (default: 1 hour)
        
    Returns
    -------
    bool
        True if cached successfully
    """
    cache_col = _get_cache_collection()
    if not cache_col:
        return False
    
    try:
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        cache_col.update_one(
            {"key": key},
            {
                "$set": {
                    "key": key,
                    "value": value,
                    "expires_at": expires_at,
                    "cached_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )
        logger.debug(f"Cache SET: {key[:50]} (TTL: {ttl}s)")
        return True
    except Exception as e:
        logger.warning(f"Cache set error: {e}")
        return False


def cache_delete(key: str) -> bool:
    """Delete a cache entry."""
    cache_col = _get_cache_collection()
    if not cache_col:
        return False
    
    try:
        cache_col.delete_one({"key": key})
        return True
    except Exception as e:
        logger.warning(f"Cache delete error: {e}")
        return False


def cache_clear_pattern(pattern: str) -> int:
    """
    Clear all cache entries matching a pattern.
    
    Parameters
    ----------
    pattern : str
        Pattern to match (e.g., "email_list:*")
        
    Returns
    -------
    int
        Number of entries deleted
    """
    cache_col = _get_cache_collection()
    if not cache_col:
        return 0
    
    try:
        # MongoDB regex pattern
        regex_pattern = pattern.replace("*", ".*")
        result = cache_col.delete_many({"key": {"$regex": regex_pattern}})
        logger.info(f"Cleared {result.deleted_count} cache entries matching {pattern}")
        return result.deleted_count
    except Exception as e:
        logger.warning(f"Cache clear error: {e}")
        return 0


def cache_clear_expired() -> int:
    """Clear all expired cache entries. Returns number deleted."""
    cache_col = _get_cache_collection()
    if not cache_col:
        return 0
    
    try:
        result = cache_col.delete_many({"expires_at": {"$lt": datetime.utcnow()}})
        return result.deleted_count
    except Exception as e:
        logger.warning(f"Cache cleanup error: {e}")
        return 0


# Convenience functions for common cache operations

def cache_email_list(user_id: str, query: str, max_results: int, value: Any) -> bool:
    """Cache email list results."""
    key = _make_cache_key("email_list", user_id, query, max_results)
    return cache_set(key, value, ttl=CACHE_TTL_EMAIL_LIST)


def get_cached_email_list(user_id: str, query: str, max_results: int) -> Optional[Any]:
    """Get cached email list."""
    key = _make_cache_key("email_list", user_id, query, max_results)
    return cache_get(key)


def cache_email_style(user_id: str, value: Any) -> bool:
    """Cache email style analysis."""
    key = _make_cache_key("email_style", user_id)
    return cache_set(key, value, ttl=CACHE_TTL_EMAIL_STYLE)


def get_cached_email_style(user_id: str) -> Optional[Any]:
    """Get cached email style."""
    key = _make_cache_key("email_style", user_id)
    return cache_get(key)


def cache_thread_detail(user_id: str, thread_id: str, value: Any) -> bool:
    """Cache thread detail."""
    key = _make_cache_key("thread_detail", user_id, thread_id)
    return cache_set(key, value, ttl=CACHE_TTL_THREAD_DETAIL)


def get_cached_thread_detail(user_id: str, thread_id: str) -> Optional[Any]:
    """Get cached thread detail."""
    key = _make_cache_key("thread_detail", user_id, thread_id)
    return cache_get(key)


def cache_calendar_events(user_id: str, time_min: str, time_max: str, value: Any) -> bool:
    """Cache calendar events."""
    key = _make_cache_key("calendar_events", user_id, time_min, time_max)
    return cache_set(key, value, ttl=CACHE_TTL_CALENDAR)


def get_cached_calendar_events(user_id: str, time_min: str, time_max: str) -> Optional[Any]:
    """Get cached calendar events."""
    key = _make_cache_key("calendar_events", user_id, time_min, time_max)
    return cache_get(key)

