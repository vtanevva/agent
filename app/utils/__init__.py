"""
Utility modules for the mental health AI assistant.

This package contains:
- error_handler: Centralized error handling and custom exceptions
- validators: Input validation and sanitization utilities
- rate_limiter: API rate limiting functionality
"""

from .error_handler import (
    AppError,
    DatabaseError,
    AuthenticationError,
    ValidationError,
    ServiceError,
    handle_errors,
    safe_execute,
    log_and_raise,
    format_error_response
)

from .validators import InputValidator
from .rate_limiter import rate_limiter, RateLimitExceeded, check_rate_limit

__all__ = [
    'AppError',
    'DatabaseError', 
    'AuthenticationError',
    'ValidationError',
    'ServiceError',
    'handle_errors',
    'safe_execute',
    'log_and_raise',
    'format_error_response',
    'InputValidator',
    'rate_limiter',
    'RateLimitExceeded',
    'check_rate_limit'
]
