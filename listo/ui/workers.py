"""Background work: probing files, grabbing thumbnails, converting."""

from __future__ import annotations

import contextlib
import io
import multiprocessing
import os
import subprocess
import threading

from PySide6.QtCore import QObject, QRunnable, QThread, Signal

from ..core.captions_worker import serve as serve_captions
from ..core.engine import Conversion, Result
from ..core.log import get_logger
from ..core.probe import MediaInfo, probe
from ..core.tools import capabilities, detect_hardware, popen_kwargs

log = get_logger(__name__)


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
            [
                caps.ffmpeg,
                "-hide_banner",
                "-v",
                "error",
                "-ss",
                f"{t:.2f}",
                "-i",
                path,
                "-frames:v",
                "1",
                "-vf",
                vf,
                "-f",
                "image2pipe",
                "-c:v",
                "png",
                "-",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            **popen_kwargs(),
        )
        return cp.stdout if cp.returncode == 0 else b""
    except (OSError, subprocess.SubprocessError):
        return b""


def photo_thumb(path: str) -> bytes:
    from ..core import photo

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
        except Exception as e:
            info = MediaInfo(kind="unknown", error=str(e))
        thumb = b""
        try:
            if info.kind == "video":
                thumb = video_thumb(self.path, info)
            elif info.kind == "photo" and not info.error:
                thumb = photo_thumb(self.path)
        except Exception:
            log.warning("thumbnail failed for %s", self.path, exc_info=True)
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


class FrameSignals(QObject):
    done = Signal(int, bytes)  # request number, PNG bytes


class FrameTask(QRunnable):
    """Grab one frame at a time position (for the trim previews)."""

    def __init__(
        self, seq: int, path: str, t: float, info: MediaInfo, signals: FrameSignals, width: int = 320
    ):
        super().__init__()
        self.seq, self.path, self.t, self.info, self.signals, self.width = seq, path, t, info, signals, width
        self.setAutoDelete(True)

    def run(self) -> None:
        caps = capabilities()
        data = b""
        if caps.ffmpeg:
            vf = ("yadif," if self.info.interlaced else "") + f"scale={self.width}:-2"
            try:
                cp = subprocess.run(
                    [
                        caps.ffmpeg,
                        "-hide_banner",
                        "-v",
                        "error",
                        "-ss",
                        f"{max(0.0, self.t):.3f}",
                        "-i",
                        self.path,
                        "-frames:v",
                        "1",
                        "-vf",
                        vf,
                        "-f",
                        "image2pipe",
                        "-c:v",
                        "png",
                        "-",
                    ],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=20,
                    **popen_kwargs(),
                )
                data = cp.stdout if cp.returncode == 0 else b""
            except (OSError, subprocess.SubprocessError):
                data = b""
        try:
            self.signals.done.emit(self.seq, data)
        except RuntimeError:
            pass


class DownloadThread(QThread):
    progress = Signal(int, float, str)  # item id, 0..1 (or -1 for a status message), text
    titled = Signal(int, str)
    done = Signal(int, str, str)  # item id, saved path, error ("" if ok)

    def __init__(self, item_id: int, url: str):
        super().__init__()
        from ..core.links import LinkDownload

        self.item_id = item_id
        self.job = LinkDownload(url)

    def run(self) -> None:
        from ..core.links import Canceled, LinkError

        try:
            path = self.job.run(
                lambda p, t: self.progress.emit(self.item_id, p, t),
                lambda title: self.titled.emit(self.item_id, title),
            )
            self.done.emit(self.item_id, path, "")
        except Canceled:
            self.done.emit(self.item_id, "", "Canceled")
        except LinkError as e:
            self.done.emit(self.item_id, "", str(e))
        except Exception as e:
            self.done.emit(self.item_id, "", f"{e.__class__.__name__}: {e}")


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
        except Exception as e:
            r = Result("failed", message=f"{e.__class__.__name__}: {e}")
        self.finished_item.emit(self.item_id, r)


class JoinThread(QThread):
    """Glues the converted parts into one video (core.join.Join) off the main thread."""

    progress = Signal(float, float)  # seconds written, speed
    joined = Signal(object)  # Result

    def __init__(self, job):
        super().__init__()
        self.job = job

    def run(self) -> None:
        try:
            r = self.job.run(lambda p, s: self.progress.emit(p, s))
        except Exception as e:
            r = Result("failed", message=f"Couldn't join the clips ({e.__class__.__name__}).")
        self.joined.emit(r)


class PreviewSignals(QObject):
    done = Signal(int, bytes, str)  # request number, PNG bytes, error message


class PreviewTask(QRunnable):
    """Render one frame exactly as the conversion would (or the untouched original)."""

    def __init__(
        self,
        seq: int,
        path: str,
        info: MediaInfo,
        settings,
        at: float,
        original: bool,
        signals: PreviewSignals,
        captions: list | None = None,
    ):
        super().__init__()
        self.captions = captions
        self.seq, self.path, self.info, self.s = seq, path, info, settings
        self.at, self.original, self.signals = at, original, signals
        self.setAutoDelete(True)

    def run(self) -> None:
        import tempfile
        from pathlib import Path

        from ..core.video import PlanError, original_frame_args, preview_plan

        caps = capabilities()
        data, error, plan = b"", "", None
        if not self.path:  # nothing in the list: show the settings on the sample clip
            from ..core.sample import sample_clip

            sample = sample_clip()
            if not sample:
                self._emit(b"", "No preview (ffmpeg is missing)")
                return
            self.path, self.info = sample, probe(sample)
        fd, name = tempfile.mkstemp(prefix="listo-preview-", suffix=".png")
        os.close(fd)
        try:
            if self.original:
                args = original_frame_args(self.path, self.info, self.at, name)
            else:
                args, plan = preview_plan(self.path, self.info, self.s, caps, self.at, name, self.captions)
            cp = subprocess.run(
                [caps.ffmpeg, *args],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=60,
                **popen_kwargs(),
            )
            if cp.returncode == 0:
                data = Path(name).read_bytes()
            else:
                error = "Couldn't make a preview of this file."
                log.warning("preview failed: %s", cp.stderr[-2000:].decode("utf-8", "replace"))
        except PlanError as e:
            error = str(e)
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            error = "Couldn't make a preview of this file."
            log.warning("preview failed", exc_info=e)
        finally:
            if plan is not None:
                plan.cleanup()
            Path(name).unlink(missing_ok=True)
        self._emit(data, error)

    def _emit(self, data: bytes, error: str) -> None:
        try:
            self.signals.done.emit(self.seq, data, error)
        except RuntimeError:  # the window closed meanwhile
            pass


class TranscribeThread(QThread):
    """Turns speech into captions in the background, one clip at a time.
    The listening itself happens in a separate low-priority process (core.captions_worker), so the
    window never waits on it; this thread only hands over clips and relays progress.
    Jobs can be added while it runs; it ends when the queue is empty."""

    progress = Signal(int, float)  # item id, 0..1
    status = Signal(int, str)  # item id, what's happening ("Downloading the speech model…")
    done = Signal(int, object, str)  # item id, Transcript or None, error message

    target = staticmethod(serve_captions)  # what the worker process runs (tests swap in a stand-in)

    def __init__(self, jobs: list[tuple[int, str, MediaInfo, object]]):
        """jobs: (item id, path, info, settings)."""
        super().__init__()
        self._jobs = list(jobs)
        self._lock = threading.Lock()
        self._closing = False
        self._cancel = threading.Event()
        self._proc = None
        self._conn = None
        self.current: int | None = None

    def add(self, job: tuple[int, str, MediaInfo, object]) -> bool:
        """Queue one more clip. False if the thread is already finishing (start a new one)."""
        with self._lock:
            if self._closing:
                return False
            self._jobs.append(job)
            return True

    def queued(self) -> set[int]:
        with self._lock:
            return {j[0] for j in self._jobs} | ({self.current} if self.current is not None else set())

    def cancel(self) -> None:
        """Stop now: the worker process is ended mid-clip (nothing half-made is kept)."""
        self._cancel.set()
        with self._lock:
            proc = self._proc
        if proc is not None and proc.is_alive():
            proc.kill()

    # ------------------------------------------------------------------ worker process
    def _start_worker(self) -> None:
        ctx = multiprocessing.get_context("spawn")  # same on every OS, and works when packaged
        mine, theirs = ctx.Pipe()
        proc = ctx.Process(target=self.target, args=(theirs,), daemon=True, name="listo-captions")
        proc.start()
        theirs.close()
        with self._lock:
            self._proc, self._conn = proc, mine

    def _stop_worker(self) -> None:
        with self._lock:
            proc, conn = self._proc, self._conn
            self._proc = self._conn = None
        if conn is not None:
            with contextlib.suppress(OSError):
                conn.send(None)
            conn.close()
        if proc is not None:
            proc.join(2)
            if proc.is_alive():
                proc.kill()
                proc.join(2)

    def _one(self, iid: int, path: str, s) -> tuple[object | None, str]:
        """Send one clip to the worker and relay what it says until it's done."""
        from ..core import captions

        if self._proc is None or not self._proc.is_alive():
            self._start_worker()
        conn = self._conn
        conn.send({"path": path, "model": s.caption_model, "language": s.caption_language,
                   "words": s.caption_words, "lines": s.caption_lines})  # fmt: skip
        while True:
            if self._cancel.is_set():
                return None, "Canceled"
            try:
                if not conn.poll(0.2):
                    if not self._proc.is_alive():
                        raise EOFError
                    continue
                kind, value = conn.recv()
            except (EOFError, OSError):
                self._stop_worker()
                if self._cancel.is_set():
                    return None, "Canceled"
                log.warning("captions worker stopped while working on %s", path)
                return None, "Captions stopped unexpectedly. Click the CC icon to try again."
            if kind == "progress":
                self.progress.emit(iid, value)
            elif kind == "status":
                self.status.emit(iid, value)
            elif kind == "done":
                return captions.Transcript.from_json(value), ""
            else:
                return None, str(value)

    def run(self) -> None:
        from ..core import captions

        try:
            while True:
                with self._lock:
                    if not self._jobs or self._cancel.is_set():
                        self._closing = True
                        self.current = None
                        return
                    iid, path, _info, s = self._jobs.pop(0)
                    self.current = iid
                try:
                    t, error = self._one(iid, path, s)
                    if t is not None:
                        captions.save(t)
                    self.done.emit(iid, t, error)
                except Exception as e:
                    log.warning("transcription failed for %s", path, exc_info=True)
                    self.done.emit(iid, None, f"Couldn't make captions ({e.__class__.__name__}).")
        finally:
            self._stop_worker()
