"""Logging utilities and logger factory."""

from __future__ import annotations

import logging
from typing import Any

_BASE_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "request_id=%(request_id)s phase=%(phase)s component=%(component)s "
    "%(message)s"
)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure application logging once."""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(level)
        return
    logging.basicConfig(level=level, format=_BASE_FORMAT)


def get_logger(
    name: str,
    *,
    request_id: str = "n/a",
    phase: str = "phase-0",
    component: str = "app",
) -> logging.LoggerAdapter[logging.Logger]:
    """Return a logger adapter with consistent structured context."""
    configure_logging()
    base_logger = logging.getLogger(name)
    context = {
        "request_id": request_id,
        "phase": phase,
        "component": component,
    }
    return logging.LoggerAdapter(base_logger, context)


def log_event(
    logger: logging.LoggerAdapter[logging.Logger], event: str, **fields: Any
) -> None:
    """Log a lightweight structured event message."""
    if not fields:
        logger.info(event)
        return
    suffix = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("%s %s", event, suffix)
