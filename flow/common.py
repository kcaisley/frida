"""
Shared utilities for flow scripts.

Provides common logging configuration and utilities used across
netlist generation, simulation, measurement, and plotting scripts.
"""

import logging
import sys
from pathlib import Path


class CustomFormatter(logging.Formatter):
    """Custom formatter that doesn't add [INFO] prefix for info messages."""

    def format(self, record):
        if record.levelno == logging.INFO:
            # For INFO level, just output the message without level name
            return record.getMessage()
        elif record.levelno == logging.WARNING:
            return f"[WARNING] {record.getMessage()}"
        elif record.levelno == logging.ERROR:
            return f"[ERROR] {record.getMessage()}"
        else:
            return record.getMessage()


def setup_logging(log_file: Path | None = None, logger_name: str | None = None):
    """
    Setup logging with custom formatter.

    Args:
        log_file: Optional path to log file. If provided, logs to both file and console.
        logger_name: Optional logger name. If None, configures root logger.

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console handler with custom formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(CustomFormatter())
    logger.addHandler(console_handler)

    # File handler if log file specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(CustomFormatter())
        logger.addHandler(file_handler)

    # Prevent propagation to avoid duplicate messages if not root logger
    if logger_name:
        logger.propagate = False

    return logger
