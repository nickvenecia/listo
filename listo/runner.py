"""Run ffmpeg with live progress, pause/resume and cancel — on every OS."""
from __future__ import annotations

import collections
import subprocess
import threading
import time
from typing import Callable

import psutil

from .tools import popen_kwargs


class Canceled(Exception):
    pass


class FFmpegFailed(Exception):
    def __init__(self, message: str, log: str):
        super().__init__(message)
        self.log = log


ProgressFn = Callable[[float, float], None]  # (seconds processed, speed multiplier)


class FFmpegRun:
    def __init__(self, ffmpeg: str, args: list[str]):
        self.cmd = [ffmpeg, *args]
        self.proc: subprocess.Popen | None = None
        self._paused = False
        self._canceled = False
        self._lock = threading.Lock()
        self.log_tail: collections.deque[str] = collections.deque(maxlen=120)

    # -- control (safe to call from the UI thread)
    def pause(self) -> bool:
        with self._lock:
            if self.proc and self.proc.poll() is None and not self._paused:
                try:
                    psutil.Process(self.proc.pid).suspend()
                    self._paused = True
                except psutil.Error:
                    return False
            return self._paused

    def resume(self) -> bool:
        with self._lock:
            if self.proc and self._paused:
                try:
                    psutil.Process(self.proc.pid).resume()
                except psutil.Error:
                    pass
                self._paused = False
            return True

    def cancel(self) -> None:
        with self._lock:
            self._canceled = True
            proc = self.proc
            paused = self._paused
        if proc and proc.poll() is None:
            try:
                if paused:  # a frozen process can't receive the quit signal on all OSes
                    psutil.Process(proc.pid).resume()
                proc.terminate()
            except (psutil.Error, OSError):
                pass

    @property
    def paused(self) -> bool:
        return self._paused

    # -- run (blocks; call from a worker thread)
    def run(self, on_progress: ProgressFn | None = None) -> None:
        if self._canceled:
            raise Canceled()
        self.proc = subprocess.Popen(
            self.cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **popen_kwargs(),
        )
        if self._canceled:  # cancel arrived while we were starting up
            self.cancel()

        # Drain stderr continuously so a chatty file can never fill the pipe and freeze ffmpeg.
        def drain() -> None:
            assert self.proc and self.proc.stderr
            for line in self.proc.stderr:
                line = line.rstrip()
                if line:
                    self.log_tail.append(line)

        t = threading.Thread(target=drain, daemon=True)
        t.start()

        processed, speed = 0.0, 0.0
        last_emit = 0.0
        assert self.proc.stdout
        for line in self.proc.stdout:
            key, _, val = line.strip().partition("=")
            if key in ("out_time_us", "out_time_ms"):  # both are microseconds in ffmpeg
                try:
                    processed = max(processed, int(val) / 1_000_000)
                except ValueError:
                    continue
            elif key == "speed":
                try:
                    speed = float(val.rstrip("x").strip())
                except ValueError:
                    pass
            elif key == "progress":
                now = time.monotonic()
                if on_progress and (now - last_emit > 0.2 or val == "end"):
                    last_emit = now
                    on_progress(processed, speed)
        rc = self.proc.wait()
        t.join(timeout=2)
        if self._canceled:
            raise Canceled()
        if rc != 0:
            log = "\n".join(self.log_tail)
            raise FFmpegFailed(_friendly(log), log)


def _friendly(log: str) -> str:
    """Best one-line explanation from ffmpeg's log."""
    lines = [ln for ln in log.splitlines() if ln.strip()]
    low = log.lower()
    if "no space left" in low:
        return "The destination drive is full."
    if "permission denied" in low:
        return "Listo isn't allowed to write to that folder."
    if "could not find tag for codec" in low or "not currently supported in container" in low:
        return "That video or audio codec can't go in this container — try ProRes or H.264 instead of Rewrap."
    if "channel layout" in low:
        return "This file's audio channel layout isn't supported by that format."
    if "only supported in" in low:
        return [ln.strip() for ln in lines if "only supported in" in ln.lower()][-1]
    if "dimensions" in low and ("too small" in low or "not supported" in low or "invalid" in low):
        return "The video size isn't supported by that format."
    if "invalid data found" in low:
        return "This file looks damaged or isn't a format ffmpeg understands."
    for ln in reversed(lines):
        if "error" in ln.lower() or "invalid" in ln.lower():
            return ln.strip()
    return lines[-1].strip() if lines else "ffmpeg stopped with an error."
