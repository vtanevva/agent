import logging
import traceback
from typing import Any, Dict, Optional
from functools import wraps
from flask import jsonify

logger = logging.getLogger(__name__)

class AppError(Exception):
    """Base application error class"""
    def __init__(self, message: str, error_code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(self.message)

class DatabaseError(AppError):
    """Database-related errors"""
    def __init__(self, message: str = "Database operation failed"):
        super().__init__(message, "DATABASE_ERROR", 503)

class AuthenticationError(AppError):
    """Authentication-related errors"""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, "AUTH_ERROR", 401)

class ValidationError(AppError):
    """Input validation errors"""
    def __init__(self, message: str = "Invalid input"):
        super().__init__(message, "VALIDATION_ERROR", 400)

class ServiceError(AppError):
    """External service errors"""
    def __init__(self, message: str = "External service unavailable"):
        super().__init__(message, "SERVICE_ERROR", 503)

def handle_errors(f):
    """Decorator for consistent error handling in API endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except AppError as e:
            logger.warning(f"Application error: {e.error_code} - {e.message}")
            return jsonify({
                "error": e.error_code,
                "message": e.message
            }), e.status_code
        except Exception as e:
            logger.error(f"Unexpected error in {f.__name__}: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({
                "error": "INTERNAL_ERROR",
                "message": "An unexpected error occurred"
            }), 500
    return decorated_function

def safe_execute(func, *args, default_return=None, **kwargs):
    """Safely execute a function with error handling"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Error in {func.__name__}: {str(e)}")
        return default_return

def log_and_raise(error_class: type, message: str, **kwargs):
    """Log an error and raise an appropriate exception"""
    logger.error(f"{error_class.__name__}: {message}")
    raise error_class(message, **kwargs)

def format_error_response(error: Exception) -> Dict[str, Any]:
    """Format error for API response"""
    if isinstance(error, AppError):
        return {
            "error": error.error_code,
            "message": error.message,
            "status_code": error.status_code
        }
    else:
        return {
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "status_code": 500
        }
