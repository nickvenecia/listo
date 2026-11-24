"""Move Originals to the Trash: a converted file's original goes to the system's Trash / Recycle Bin.
Never deleted outright: what the Trash can't take stays where it is."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QFile

from listo.core.log import get_logger
from listo.core.probe import ext_of

log = get_logger(__name__)


def with_sidecar(path: str | Path) -> list[Path]:
    """The original and what only makes sense beside it: a JVC clip's .MOI (probe.read_moi)."""
    p = Path(path)
    files = [p]
    if ext_of(p) in ("mod", "tod"):
        files += [m for m in (p.with_suffix(".MOI"), p.with_suffix(".moi")) if m.is_file()][:1]
    return files


def safe_to_trash(original: str | Path, new: str | Path | None) -> bool:
    """Only when the new file is really there, has something in it, and isn't the original itself."""
    try:
        return (
            new is not None
            and os.path.getsize(new) > 0
            and os.path.isfile(original)
            and not os.path.samefile(original, new)
        )
    except OSError:
        return False


def to_trash(original: str | Path) -> bool:
    """Move the original (and its sidecar) to the Trash. False = it's still where it was."""
    ok = False
    for n, p in enumerate(with_sidecar(original)):
        moved = bool(QFile.moveToTrash(str(p)))
        if n == 0:
            ok = moved
            if not moved:
                log.warning("couldn't move the original to the trash: %s", p)
                break
            log.info("original moved to the trash: %s", p)
    return ok
