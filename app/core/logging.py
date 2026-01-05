import logging
import logging.handlers
import sys
from pathlib import Path

from app.core.config import settings


def setup_logging() -> None:
    """
    Configure centralized logging for the application.

    Sets up:
    - Console handler with formatted output
    - Format: timestamp, logger name, level, message
    - Log level based on environment (DEBUG for dev, INFO for prod)
    """
    # Determine log level based on environment
    log_level = logging.DEBUG if settings.ENVIRONMENT == "dev" else logging.INFO

    # Define log format: timestamp, logger, level, message
    log_format = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(log_format)
    root_logger.addHandler(console_handler)

    # Set specific logger levels
    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Log the configuration
    root_logger.info(
        f"Logging configured - Level: {logging.getLevelName(log_level)}, "
        f"Environment: {settings.ENVIRONMENT}, "
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Typically __name__ of the calling module

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
