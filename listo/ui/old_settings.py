"""Bringing settings over from older Listo versions, once.

Before 3.0, Listo kept its settings, recipes and recent folders in the system's own settings store (Qt's
QSettings: the registry on Windows, a .plist on the Mac, an .ini file on Linux). Now everything is in
settings.json in Listo's data folder. The first launch copies every old value across; the old store is left
exactly as it was (a backup), and a value already in settings.json is never replaced.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings

from listo.core import store
from listo.core.log import get_logger

log = get_logger(__name__)

DONE = "copied_old_settings"  # in settings.json once it's been done
RENAMED = {"updates/auto": "auto_update"}  # older names -> today's (the old value is kept beside it)


def old_store() -> QSettings:
    """Where older versions kept their settings (the tests point this at a file of their own)."""
    return QSettings("Listo", "Listo")


def bring_over() -> int:
    """Copy the old settings into settings.json (once). Returns how many values came over."""
    data = store.prefs()
    if data.get(DONE):
        if _rename(data):
            store.save_prefs(data)
        return 0
    old = old_store()
    n = 0
    for key in old.allKeys():
        if key in data:
            continue
        value = old.value(key)
        if isinstance(value, QByteArray):  # the window's size and place
            value = bytes(value.toHex()).decode()
        elif not isinstance(value, (str, bool, int, float, list, dict)) and value is not None:
            log.info("old setting %s left behind (can't be kept as text)", key)
            continue
        data[key] = value
        n += 1
    data[DONE] = True
    _rename(data)
    store.save_prefs(data)
    if n:
        log.info(
            "copied %d settings from the old settings store into settings.json (the old store is kept)", n
        )
    return n


def _rename(data: dict) -> bool:
    """Give values kept under an older name today's name too (never over one already set)."""
    changed = False
    for was, now in RENAMED.items():
        if was in data and now not in data:
            data[now] = data[was]
            changed = True
    return changed
