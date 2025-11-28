"""
Unified logging configuration for the productivity assistant.

Usage:
    from app.utils.logging_utils import get_logger
    
    logger = get_logger(__name__)
    logger.info("Starting process...")
    logger.debug("Debug information")
    logger.error("Error occurred", exc_info=True)
"""

import logging
import sys
from typing import Optional

from app.config import Config


# ═══════════════════════════════════════════════════════════════════════
# Logger Configuration
# ═══════════════════════════════════════════════════════════════════════

_loggers: dict[str, logging.Logger] = {}
_configured = False


def configure_logging():
    """
    Configure the root logger with consistent settings.
    
    This should be called once at application startup.
    """
    global _configured
    
    if _configured:
        return
    
    # Get log level from config
    log_level = Config.get_log_level()
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Create formatter
    if Config.is_development():
        # Colored output for development (if available)
        try:
            from colorlog import ColoredFormatter
            formatter = ColoredFormatter(
                "%(log_color)s%(asctime)s - %(name)s - %(levelname)s%(reset)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                log_colors={
                    'DEBUG': 'cyan',
                    'INFO': 'green',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'red,bg_white',
                }
            )
        except ImportError:
            # Fallback to standard formatter
            formatter = logging.Formatter(
                Config.LOG_FORMAT,
                datefmt="%Y-%m-%d %H:%M:%S"
            )
    else:
        # Production: Simple formatter
        formatter = logging.Formatter(
            Config.LOG_FORMAT,
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Silence noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)
    logging.getLogger("google.auth").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    
    _configured = True


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Get a logger instance for the specified module.
    
    Parameters
    ----------
    name : str
        Logger name (typically __name__)
    level : int, optional
        Override log level for this logger
    
    Returns
    -------
    logging.Logger
        Configured logger instance
        
    Example
    -------
    >>> from app.utils.logging_utils import get_logger
    >>> logger = get_logger(__name__)
    >>> logger.info("Operation completed")
    """
    # Ensure logging is configured
    if not _configured:
        configure_logging()
    
    # Return cached logger if exists
    if name in _loggers:
        return _loggers[name]
    
    # Create new logger
    logger = logging.getLogger(name)
    
    # Set custom level if specified
    if level is not None:
        logger.setLevel(level)
    
    # Cache and return
    _loggers[name] = logger
    return logger


def log_function_call(logger: logging.Logger):
    """
    Decorator to log function calls (useful for debugging).
    
    Example
    -------
    >>> @log_function_call(logger)
    >>> def process_data(data):
    >>>     return data
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"{func.__name__} completed successfully")
                return result
            except Exception as e:
                logger.error(f"{func.__name__} failed with error: {e}", exc_info=True)
                raise
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════════
# Configure logging on module import
# ═══════════════════════════════════════════════════════════════════════

configure_logging()

