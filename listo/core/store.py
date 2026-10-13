"""Saving and loading Listo's own small files (settings.json in data_dir()).

Every write goes to a temp file next to the real one, then replaces it in one step, so a crash
or a full disk never leaves a half-written file. A file that can't be read is set aside as
<name>.unreadable-<time> (never deleted) and logged.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from listo.core.log import get_logger
from listo.core.paths import data_dir

log = get_logger(__name__)


def write_text(path: Path, text: str) -> None:
    """Write a text file atomically: a temp file in the same folder, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            log.warning("couldn't remove %s", tmp, exc_info=True)
        raise


def write_json(path: Path, data: Any) -> None:
    """Write atomically: a temp file in the same folder, then os.replace."""
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def set_aside(path: Path, why: str, copy: bool = False) -> None:
    """Keep a file we couldn't use as <name>.<why>-<time>, so nothing is ever lost. `copy` leaves the
    original in place."""
    aside = path.with_name(f"{path.name}.{why}-{int(time.time())}")
    log.warning("couldn't use all of %s; kept a copy as %s", path, aside.name)
    try:
        if copy:
            aside.write_bytes(path.read_bytes())
        else:
            path.replace(aside)
    except OSError:
        log.warning("couldn't set %s aside", path, exc_info=True)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("couldn't read %s", path, exc_info=True)
        set_aside(path, "unreadable")
        return default


def settings_path() -> Path:
    return data_dir() / "settings.json"


def prefs() -> dict:
    """The app's own preferences (appearance, accent): what's saved, or {} (anything unreadable is set aside)."""
    data = read_json(settings_path(), {})
    return data if isinstance(data, dict) else {}


def save_pref(key: str, value: Any) -> None:
    """Change one preference, keeping every other key in the file as it was."""
    data = prefs()
    if data.get(key) != value:
        data[key] = value
        write_json(settings_path(), data)
        log.info("setting %s = %r", key, value)
