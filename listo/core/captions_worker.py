"""Speech to text in its own process, so the window never waits on it.

Loading the speech model and listening are heavy Python work. On a thread inside the app they
take turns with the window (Python runs one thread at a time), which made the whole app stutter
for the first 10-15 seconds. A separate process has its own Python, runs at low priority and
can be stopped instantly.

The app (ui.workers.TranscribeThread) starts `serve` with multiprocessing ("spawn", which also
works in the packaged app) and talks over a Pipe:

    app -> worker   {"path", "model", "language", "words", "lines"}   one clip
                    None                                             no more clips, exit
    worker -> app   ("status", text) | ("progress", 0..1)
                    ("done", transcript_json) | ("error", text)      one of these per clip
"""

from __future__ import annotations

import os
import sys

from . import captions
from .log import get_logger, setup_logging
from .probe import probe

log = get_logger(__name__)


def _lower_priority() -> None:
    """Background work: the window and conversions always go first."""
    try:
        if sys.platform == "win32":
            import psutil

            psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            os.nice(10)
    except Exception:
        log.debug("couldn't lower the captions priority", exc_info=True)


def handle(job: dict, send) -> None:
    """Make captions for one clip and send the result (or a readable error)."""
    try:
        info = probe(job["path"])
        t = captions.transcribe(
            job["path"], info, job.get("model", "balanced"), job.get("language", "auto"),
            int(job.get("words", 7)), int(job.get("lines", 2)),
            on_progress=lambda f: send(("progress", float(f))),
            on_status=lambda m: send(("status", m)),
        )  # fmt: skip
        send(("done", t.to_json()))
    except captions.CaptionError as e:
        send(("error", str(e)))
    except Exception as e:
        log.warning("transcription failed for %s", job.get("path"), exc_info=True)
        send(("error", f"Couldn't make captions ({e.__class__.__name__})."))


def serve(conn) -> None:
    """The worker process: one clip at a time until the app sends None or goes away."""
    setup_logging(filename="listo-captions.log")
    _lower_priority()
    while True:
        try:
            job = conn.recv()
        except (EOFError, OSError):
            return
        if job is None:
            return
        if job == "ping":  # the build's smoke test: can the packaged app start this process?
            conn.send(("pong", _engine_status()))
            continue
        handle(job, conn.send)


def _engine_status() -> str:
    try:
        captions._without_pyav()
        import ctranslate2  # noqa: F401
        import faster_whisper  # noqa: F401
    except Exception as e:
        return f"NOT available ({e.__class__.__name__}: {e})"
    return "ready (speech model downloads on first use)"


def ping(timeout: float = 60.0) -> str:
    """Start the worker process, ask it if the speech engine loads, and stop it. For --smoke-test."""
    import multiprocessing

    ctx = multiprocessing.get_context("spawn")
    mine, theirs = ctx.Pipe()
    proc = ctx.Process(target=serve, args=(theirs,), daemon=True)
    proc.start()
    theirs.close()
    try:
        mine.send("ping")
        if not mine.poll(timeout):
            return ""
        _kind, status = mine.recv()
        mine.send(None)
        return status
    except (EOFError, OSError):
        return ""
    finally:
        proc.join(5)
        if proc.is_alive():
            proc.kill()
