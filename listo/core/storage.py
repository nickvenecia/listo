"""What Listo keeps on the computer, how big it is, and deleting it (Storage & Cache window).

Everything lives in data_dir(). None of it is needed to keep your converted files; each kind is
downloaded or made again when it's needed. Settings and recipes (the system's settings store) and
anything in your own folders (converted files, ~/Downloads/Listo) are never touched here.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .log import get_logger
from .paths import data_dir, log_dir, tools_dir

log = get_logger(__name__)


@dataclass
class Kind:
    key: str
    title: str
    note: str  # what happens if you delete it
    paths: list[Path]


def kinds() -> list[Kind]:
    d = data_dir()
    return [
        Kind(
            "models", "Speech Models",
            "Used to make captions. Downloaded again the next time you make captions.",
            [d / "models"],
        ),
        Kind(
            "captions", "Saved Captions",
            "The words Listo heard in your clips, and your fixes. Clips are listened to again if you need them.",
            [d / "captions"],
        ),
        Kind(
            "tools", "Link Download Tools",
            "Used to download video links. Downloaded again the next time you add a link.",
            [tools_dir()],
        ),
        Kind(
            "logs", "Logs",
            "What Listo did, for troubleshooting. New logs start right away.",
            [log_dir()],
        ),
        Kind(
            "extras", "Small Extras",
            "The sample picture's clip and interface images. Made again when needed.",
            [d / "sample", d / "ui", d / "Listo Debug Console.command"],
        ),
    ]  # fmt: skip


def size_of(path: Path) -> int:
    """Bytes in a file or folder (0 if it isn't there)."""
    try:
        if path.is_file():
            return path.stat().st_size
        if path.is_dir():
            total = 0
            for p in path.rglob("*"):
                try:
                    if p.is_file() and not p.is_symlink():
                        total += p.stat().st_size
                except OSError:
                    pass
            return total
    except OSError:
        pass
    return 0


def kind_size(k: Kind) -> int:
    return sum(size_of(p) for p in k.paths)


def total_size() -> int:
    return sum(kind_size(k) for k in kinds())


def human(n: int) -> str:
    """1.6 GB, 470 MB, 12 KB."""
    size = float(n)
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            if unit == "bytes":
                return f"{int(size)} bytes"
            return f"{size:.1f} {unit}" if size < 10 else f"{size:.0f} {unit}"
        size /= 1000
    return f"{size:.1f} GB"


def clear(key: str) -> int:
    """Delete one kind. Returns the bytes freed. Logs that are open are emptied, not deleted."""
    k = next(k for k in kinds() if k.key == key)
    freed = 0
    for p in k.paths:
        before = size_of(p)
        try:
            if key == "logs" and p.is_dir():
                for f in p.iterdir():
                    if f.suffix == ".log":
                        f.write_bytes(b"")  # Listo (and maybe the debug console) still has it open
                    elif f.is_file():
                        f.unlink()
            elif p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()
        except OSError:
            log.warning("couldn't delete %s", p, exc_info=True)
        freed += before - size_of(p)
    log.info("storage: cleared %s (%s)", k.title, human(freed))
    return freed
