"""Troubleshooting log: a small rotating file in Listo's data folder.

Use ``log = get_logger(__name__)`` in any module. Nothing is ever sent anywhere.
"""

from __future__ import annotations

import logging
import logging.handlers

from .paths import log_dir

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """Write to <data dir>/logs/listo.log (1 MB x 3 files). Safe to call more than once."""
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger("listo")
    root.setLevel(level)
    try:
        log_dir().mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            log_dir() / "listo.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
    except OSError:
        handler = logging.NullHandler()  # read-only home folder etc. — logging is optional
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name if name.startswith("listo") else f"listo.{name}")
