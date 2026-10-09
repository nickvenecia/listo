"""Troubleshooting log: a small rotating file in Listo's data folder.

Use ``log = get_logger(__name__)`` in any module. Nothing is ever sent anywhere.
Started from a terminal (`python -m listo`), the same lines also print there. Help › Open Debug
Console follows these files live (core/console.py).
"""

from __future__ import annotations

import logging
import logging.handlers
import sys

from .paths import log_dir

_configured = False


def setup_logging(level: int = logging.INFO, filename: str = "listo.log") -> None:
    """Write to <data dir>/logs/<filename> (1 MB x 3 files). Safe to call more than once.
    Each process gets its own file (rotating a file another process has open fails on Windows)."""
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger("listo")
    root.setLevel(level)
    try:
        log_dir().mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            log_dir() / filename, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
    except OSError:
        handler = logging.NullHandler()  # read-only home folder etc. — logging is optional
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    stream = sys.stderr
    if (
        stream is not None and hasattr(stream, "isatty") and stream.isatty()
    ):  # run from a terminal: show it there too
        console = logging.StreamHandler(stream)
        console.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
        )
        root.addHandler(console)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name if name.startswith("listo") else f"listo.{name}")
