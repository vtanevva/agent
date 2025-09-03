import time
import logging
from typing import Dict, Optional
from collections import defaultdict
from threading import Lock

from .error_handler import AppError

logger = logging.getLogger(__name__)

class RateLimiter:
    """Simple in-memory rate limiter for API endpoints"""
    
    def __init__(self):
        self.requests: Dict[str, list] = defaultdict(list)
        self.lock = Lock()
        
    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """
        Check if request is allowed based on rate limit
        
        Args:
            key: Unique identifier (e.g., user_id, IP address)
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds
            
        Returns:
            True if request is allowed, False otherwise
        """
        current_time = time.time()
        
        with self.lock:
            # Clean old requests outside the window
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if current_time - req_time < window_seconds
            ]
            
            # Check if under limit
            if len(self.requests[key]) < max_requests:
                self.requests[key].append(current_time)
                return True
            else:
                return False
    
    def get_remaining(self, key: str, max_requests: int, window_seconds: int) -> int:
        """Get remaining requests allowed for the key"""
        current_time = time.time()
        
        with self.lock:
            # Clean old requests
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if current_time - req_time < window_seconds
            ]
            
            return max(0, max_requests - len(self.requests[key]))
    
    def reset(self, key: str):
        """Reset rate limit for a specific key"""
        with self.lock:
            self.requests[key] = []

# Global rate limiter instance
rate_limiter = RateLimiter()

class RateLimitExceeded(AppError):
    """Rate limit exceeded error"""
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, "RATE_LIMIT_EXCEEDED", 429)

def check_rate_limit(key: str, max_requests: int = 10, window_seconds: int = 60):
    """
    Decorator to check rate limit before executing function
    
    Args:
        key: Rate limit key (usually user_id or IP)
        max_requests: Maximum requests per window
        window_seconds: Time window in seconds
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not rate_limiter.is_allowed(key, max_requests, window_seconds):
                remaining_time = window_seconds
                logger.warning(f"Rate limit exceeded for {key}")
                raise RateLimitExceeded(
                    f"Too many requests. Please wait {remaining_time} seconds before trying again."
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator

def get_rate_limit_headers(key: str, max_requests: int, window_seconds: int) -> Dict[str, str]:
    """Get rate limit headers for API response"""
    remaining = rate_limiter.get_remaining(key, max_requests, window_seconds)
    return {
        "X-RateLimit-Limit": str(max_requests),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(int(time.time()) + window_seconds)
    }
