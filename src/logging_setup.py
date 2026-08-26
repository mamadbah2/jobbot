"""Logs structurés JSON (CLAUDE.md §3 et §13 : aucun `print()`)."""

from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(level: str = "INFO", *, json_output: bool = True) -> None:
    """Configure structlog et la stdlib. Appelé une fois par entrypoint."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Logger nommé, à utiliser partout à la place de `print`."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
