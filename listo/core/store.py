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


_cache: dict = {"key": None, "data": {}}  # settings.json as last read or written (path, change time)


def _stamp(path: Path) -> tuple:
    try:
        st = path.stat()
        return (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        return (str(path), 0, 0)


def prefs() -> dict:
    """Everything in settings.json (a copy): the Convert To settings, recipes, the folders and LUTs picked
    before, the look and accent, window size… {} when there's nothing yet (an unreadable file is set aside)."""
    path = settings_path()
    key = _stamp(path)
    if key != _cache["key"]:
        data = read_json(path, {})
        if not isinstance(data, dict):
            set_aside(path, "unreadable")
            data = {}
        _cache["key"], _cache["data"] = _stamp(path), data
    return dict(_cache["data"])


def save_prefs(data: dict) -> None:
    path = settings_path()
    write_json(path, data)
    _cache["key"], _cache["data"] = _stamp(path), dict(data)


def save_pref(key: str, value: Any) -> None:
    """Change one preference, keeping every other key in the file as it was."""
    data = prefs()
    if data.get(key) != value:
        data[key] = value
        save_prefs(data)
        log.info("setting %s = %r", key, value)


class Prefs:
    """settings.json, read and written like Qt's QSettings (value / setValue), so every window and panel saves
    to the one file in Listo's data folder. Each change is written at once, safely (a temp file, then a swap)."""

    def __init__(self, *_names: str):
        pass

    def value(self, key: str, default: Any = None, type: Any = None) -> Any:
        data = prefs()
        if key not in data:
            return default
        v = data[key]
        if type is bool:
            return v.strip().lower() in ("true", "1", "yes") if isinstance(v, str) else bool(v)
        if type in (int, float):
            try:
                return type(v)
            except (TypeError, ValueError):
                return default
        if type is str:
            return "" if v is None else str(v)
        return v

    def setValue(self, key: str, value: Any) -> None:
        data = prefs()
        if data.get(key) != value or key not in data:
            data[key] = value
            save_prefs(data)

    def remove(self, key: str) -> None:
        data = prefs()
        if key in data:
            del data[key]
            save_prefs(data)

    def contains(self, key: str) -> bool:
        return key in prefs()


def loads(value: Any, default: Any) -> Any:
    """A saved list or dict: kept as itself in settings.json, or as JSON text (what older versions kept)."""
    if isinstance(value, str):
        try:
            value = json.loads(value or "null")
        except ValueError:
            log.warning("a saved setting couldn't be read; using the default")
            return default
    return value if isinstance(value, type(default)) else default


BACKED_UP = ("settings.json", "captions", "feedback")  # yours; models, tools and logs come back by themselves


def back_up(dest: Path) -> int:
    """Zip what's yours in the data folder (settings and recipes, checked captions, unsent feedback) into
    `dest`, written to a temp file beside it and then moved into place. Returns how many files went in."""
    import zipfile

    root = data_dir()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=dest.parent)
    os.close(fd)
    n = 0
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for name in BACKED_UP:
                p = root / name
                files = (
                    [p]
                    if p.is_file()
                    else sorted(f for f in p.rglob("*") if f.is_file())
                    if p.is_dir()
                    else []
                )
                for f in files:
                    z.write(f, f.relative_to(root).as_posix())
                    n += 1
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            log.warning("couldn't remove %s", tmp, exc_info=True)
        raise
    log.info("backed up %d files to %s", n, dest)
    return n


def documents_dir() -> Path:
    """Where backups go by default: Documents/Listo."""
    docs = Path.home() / "Documents"
    return (docs if docs.is_dir() else Path.home()) / "Listo"
