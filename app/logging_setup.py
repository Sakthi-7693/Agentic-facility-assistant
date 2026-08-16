"""Shared logging setup.

    from app.logging_setup import get_logger
    log = get_logger(__name__)
"""

from __future__ import annotations

import logging
import sys

from app.config import settings

NOISY_LIBRARIES = ("httpx", "httpcore", "chromadb", "faster_whisper", "openai")

_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    root.handlers = [handler]

    for name in NOISY_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Chroma logs an error per call even with telemetry disabled. Harmless noise.
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    return logging.getLogger(name)
