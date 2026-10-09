"""Background work: probing files, grabbing thumbnails, converting."""
from __future__ import annotations

import io
import subprocess

from PySide6.QtCore import QObject, QRunnable, QThread, Signal

from ..engine import Conversion, Result
from ..probe import MediaInfo, probe
from ..tools import capabilities, detect_hardware, popen_kwargs


class ProbeSignals(QObject):
    done = Signal(int, object, bytes)  # item id, MediaInfo, thumbnail PNG bytes (may be empty)


def video_thumb(path: str, info: MediaInfo, width: int = 240) -> bytes:
    caps = capabilities()
    if not caps.ffmpeg or info.kind != "video":
        return b""
    t = min(1.0, info.duration * 0.1) if info.duration else 0
    vf = ("yadif," if info.interlaced else "") + f"scale={width}:-2"
    try:
        cp = subprocess.run(
            [caps.ffmpeg, "-hide_banner", "-v", "error", "-ss", f"{t:.2f}", "-i", path,
             "-frames:v", "1", "-vf", vf, "-f", "image2pipe", "-c:v", "png", "-"],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=30, **popen_kwargs(),
        )
        return cp.stdout if cp.returncode == 0 else b""
    except (OSError, subprocess.SubprocessError):
        return b""


def photo_thumb(path: str) -> bytes:
    from .. import photo

    im = photo.thumbnail(path, 240)
    if im is None:
        return b""
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


class ProbeTask(QRunnable):
    def __init__(self, item_id: int, path: str, signals: ProbeSignals):
        super().__init__()
        self.item_id, self.path, self.signals = item_id, path, signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            info = probe(self.path)
        except Exception as e:  # noqa: BLE001
            info = MediaInfo(kind="unknown", error=str(e))
        thumb = b""
        try:
            if info.kind == "video":
                thumb = video_thumb(self.path, info)
            elif info.kind == "photo" and not info.error:
                thumb = photo_thumb(self.path)
        except Exception:  # noqa: BLE001
            thumb = b""
        try:
            self.signals.done.emit(self.item_id, info, thumb)
        except RuntimeError:  # window closed while probing
            pass


class HardwareSignals(QObject):
    done = Signal(dict)


class HardwareTask(QRunnable):
    def __init__(self, signals: HardwareSignals):
        super().__init__()
        self.signals = signals

    def run(self) -> None:
        found = detect_hardware(capabilities())
        try:
            self.signals.done.emit(dict(found))
        except RuntimeError:
            pass


class ConvertThread(QThread):
    progress = Signal(int, float, float)  # item id, seconds processed, speed
    finished_item = Signal(int, object)  # item id, Result

    def __init__(self, item_id: int, conversion: Conversion):
        super().__init__()
        self.item_id = item_id
        self.conversion = conversion

    def run(self) -> None:
        try:
            r = self.conversion.run(lambda p, s: self.progress.emit(self.item_id, p, s))
        except Exception as e:  # noqa: BLE001
            r = Result("failed", message=f"{e.__class__.__name__}: {e}")
        self.finished_item.emit(self.item_id, r)
