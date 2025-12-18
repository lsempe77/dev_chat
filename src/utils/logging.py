"""
DevChat v2.0 SOTA - Logging Configuration

Structured logging with:
- Console output (colored)
- JSON format for production
- Request ID tracking
"""

import logging
import sys
from typing import Optional

from src.config.settings import settings


def setup_logging(
    level: Optional[str] = None,
    json_format: bool = False,
) -> None:
    """
    Configure application logging.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_format: Whether to use JSON format (for production)
    """
    level = level or settings.log_level.value
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    if json_format or settings.is_production:
        # JSON format for production
        formatter = logging.Formatter(
            '{"time": "%(asctime)s", "level": "%(levelname)s", '
            '"logger": "%(name)s", "message": "%(message)s"}'
        )
    else:
        # Human-readable format for development
        try:
            from rich.logging import RichHandler
            console_handler = RichHandler(
                rich_tracebacks=True,
                show_time=True,
                show_path=False,
            )
            formatter = logging.Formatter("%(message)s")
        except ImportError:
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("qdrant_client").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger
    """
    return logging.getLogger(name)


class RequestLogger:
    """
    Context manager for logging requests with timing.
    """
    
    def __init__(self, logger: logging.Logger, operation: str):
        self.logger = logger
        self.operation = operation
        self.start_time = None
    
    def __enter__(self):
        import time
        self.start_time = time.time()
        self.logger.info(f"Starting: {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        elapsed = (time.time() - self.start_time) * 1000
        
        if exc_type is not None:
            self.logger.error(
                f"Failed: {self.operation} ({elapsed:.0f}ms) - {exc_val}"
            )
        else:
            self.logger.info(f"Completed: {self.operation} ({elapsed:.0f}ms)")
        
        return False  # Don't suppress exceptions


# Initialize logging on import
setup_logging()
