"""Copy file dates (including 'Date Created' on macOS and Windows) and reveal files."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

from .tools import popen_kwargs


def copy_dates(src: str | Path, dst: str | Path) -> None:
    try:
        st = os.stat(src)
        os.utime(dst, (st.st_atime, st.st_mtime))
        birth = getattr(st, "st_birthtime", None)
        if sys.platform == "win32":
            birth = st.st_ctime if birth is None else birth
        if birth:
            _set_creation_time(str(dst), birth)
    except OSError:
        pass


def _set_creation_time(path: str, ts: float) -> None:
    try:
        if sys.platform == "darwin":
            _mac_set_crtime(path, ts)
        elif sys.platform == "win32":
            _win_set_crtime(path, ts)
    except Exception:  # noqa: BLE001 — best effort only
        pass


def _mac_set_crtime(path: str, ts: float) -> None:
    import ctypes.util

    class AttrList(ctypes.Structure):
        _fields_ = [
            ("bitmapcount", ctypes.c_ushort), ("reserved", ctypes.c_uint16),
            ("commonattr", ctypes.c_uint32), ("volattr", ctypes.c_uint32),
            ("dirattr", ctypes.c_uint32), ("fileattr", ctypes.c_uint32),
            ("forkattr", ctypes.c_uint32),
        ]

    class Timespec(ctypes.Structure):
        _fields_ = [("tv_sec", ctypes.c_long), ("tv_nsec", ctypes.c_long)]

    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    attrs = AttrList(5, 0, 0x00000200, 0, 0, 0, 0)  # ATTR_BIT_MAP_COUNT, ATTR_CMN_CRTIME
    spec = Timespec(int(ts), int((ts % 1) * 1e9))
    libc.setattrlist(path.encode(), ctypes.byref(attrs), ctypes.byref(spec), ctypes.sizeof(spec), 0)


def _win_set_crtime(path: str, ts: float) -> None:
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    k32.CreateFileW.restype = wintypes.HANDLE
    handle = k32.CreateFileW(path, 0x0100, 0x7, None, 3, 0x02000000, None)  # FILE_WRITE_ATTRIBUTES
    if handle in (None, wintypes.HANDLE(-1).value):
        return
    try:
        t = int((ts + 11644473600) * 10_000_000)
        ft = wintypes.FILETIME(t & 0xFFFFFFFF, t >> 32)
        k32.SetFileTime(handle, ctypes.byref(ft), None, None)
    finally:
        k32.CloseHandle(handle)


def reveal(path: str | Path) -> None:
    path = str(path)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)], **popen_kwargs())
        else:
            target = path if os.path.isdir(path) else os.path.dirname(path)
            subprocess.Popen(["xdg-open", target])
    except OSError:
        pass
