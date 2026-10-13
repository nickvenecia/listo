"""Where Listo keeps its own files on each operating system."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_override: Path | None = None

ASSETS = Path(__file__).resolve().parent.parent / "assets"  # fonts, icon: shipped inside the app


def use_data_dir(path: Path | None) -> None:
    """Point Listo at another data folder (tests, the smoke test). None goes back to the normal one."""
    global _override
    _override = path


def data_dir() -> Path:
    """Per-user folder for Listo's settings, tools, speech models, captions and logs (never inside the app)."""
    if _override is not None:
        return _override
    env = os.environ.get("LISTO_DATA_DIR")
    if env:
        return Path(env)
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
