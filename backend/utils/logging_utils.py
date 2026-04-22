"""Unified logging for the backend and migrated memory stack."""

from __future__ import annotations

import logging
import sys
from typing import Optional

from backend.config import Config

_loggers: dict[str, logging.Logger] = {}
_configured = False


def configure_logging() -> None:
    global _configured

    if _configured:
        return

    log_level = Config.get_log_level()
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    if Config.is_development():
        try:
            from colorlog import ColoredFormatter

            formatter = ColoredFormatter(
                "%(log_color)s%(asctime)s - %(name)s - %(levelname)s%(reset)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                log_colors={
                    "DEBUG": "cyan",
                    "INFO": "green",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "red,bg_white",
                },
            )
        except ImportError:
            formatter = logging.Formatter(Config.LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    else:
        formatter = logging.Formatter(Config.LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)
    logging.getLogger("google.auth").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.INFO)

    _configured = True


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    if not _configured:
        configure_logging()

    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.propagate = True
    if level is not None:
        logger.setLevel(level)

    _loggers[name] = logger
    return logger


def log_function_call(logger: logging.Logger):
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


configure_logging()
