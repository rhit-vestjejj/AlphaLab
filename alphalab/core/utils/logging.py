"""Logging utilities for AlphaLab."""

from __future__ import annotations

import logging


def _parse_level(level: str) -> int:
    """Parse a logging level string into a logging numeric level."""
    resolved_level = getattr(logging, level.upper(), None)
    if not isinstance(resolved_level, int):
        raise ValueError(f"Invalid logging level: {level}")
    return resolved_level


def configure_logging(level: str = "INFO") -> None:
    """
    Configure process-wide logging.

    Args:
        level: Logging level (for example ``INFO`` or ``DEBUG``).
    """
    logging.basicConfig(
        level=_parse_level(level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        force=True,
    )
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger.

    Args:
        name: Logger name.

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)
