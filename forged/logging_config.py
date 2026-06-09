"""Centralized logging configuration for the agentic pipeline.

Provides consistent log format across all pipeline agents and stages.
Used by CLI and programmatic entrypoints.
"""

import logging
import sys
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(debug: bool = False, log_file: Path | None = None) -> None:
    """Configure logging for the agentic pipeline.

    Args:
        debug: If True, set root logger to DEBUG; otherwise INFO
        log_file: Optional file path to write logs to (in addition to stdout)
    """
    level = logging.DEBUG if debug else logging.INFO

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance by name (standard pattern)."""
    return logging.getLogger(name)
