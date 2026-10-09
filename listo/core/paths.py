"""Where Listo keeps its own files on each operating system."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """Per-user folder for Listo's tools and logs (never inside the app bundle)."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Listo"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "Listo"
    return Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "listo"


def tools_dir() -> Path:
    """yt-dlp and Deno live here so they can update themselves."""
    return data_dir() / "tools"


def log_dir() -> Path:
    return data_dir() / "logs"


def downloads_dir() -> Path:
    """Where 'Add a link' saves the original downloads."""
    return Path.home() / "Downloads" / "Listo"
