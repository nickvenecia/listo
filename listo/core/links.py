"""Paste a link: download a video (YouTube, Vimeo, Instagram…) into the list with yt-dlp.

yt-dlp (and Deno, which it needs for YouTube) are downloaded the first time a link is
used, into Listo's own folder, and yt-dlp updates itself at most once a day — sites
change often and an old copy stops working.
"""

from __future__ import annotations

import hashlib
import io
import os
import platform
import re
import shutil
import ssl
import stat
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from listo.core.log import get_logger
from listo.core.paths import downloads_dir, tools_dir
from listo.core.tools import EXE, IS_WIN, capabilities, popen_kwargs

log = get_logger(__name__)

YTDLP_URLS = {
    "darwin": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos",
    "win32": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
    "linux-x86_64": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux",
    "linux-aarch64": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux_aarch64",
}
YTDLP_SUMS = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS"
DENO_BASE = "https://github.com/denoland/deno/releases/latest/download/"
UPDATE_EVERY = 24 * 3600


class LinkError(Exception):
    pass


class Canceled(Exception):
    pass


def is_link(text: str) -> bool:
    t = text.strip().lower()
    return (t.startswith("http://") or t.startswith("https://")) and " " not in t and len(t) > 10


def _arch() -> str:
    m = platform.machine().lower()
    return "aarch64" if m in ("arm64", "aarch64") else "x86_64"


def _ssl_context() -> ssl.SSLContext:
    if os.environ.get("SSL_CERT_FILE"):  # respect a custom CA (company proxies)
        return ssl.create_default_context()
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _fetch(
    url: str, on_status: Callable[[str], None], label: str, cancel: threading.Event | None = None
) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Listo"})
    with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as r:
        total = int(r.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        got = 0
        last = 0.0
        while True:
            if cancel is not None and cancel.is_set():
                raise Canceled()
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            buf.write(chunk)
            got += len(chunk)
            if total and time.monotonic() - last > 0.3:
                last = time.monotonic()
                on_status(f"{label} {int(got / total * 100)}%")
        return buf.getvalue()


def expected_sha256(sums: str, name: str | None = None) -> str | None:
    """Pull the SHA-256 for `name` out of a checksum file.

    Handles `<hash>  <file>` lines (yt-dlp's SHA2-256SUMS, Deno on mac/Linux) and files that
    hold a single hash (Deno's Windows .sha256sum is a PowerShell table)."""
    hashes = []
    for line in sums.splitlines():
        m = re.search(r"\b([0-9a-fA-F]{64})\b", line)
        if not m:
            continue
        if name is None:
            hashes.append(m.group(1).lower())
        elif line.split()[-1].lstrip("*").replace("\\", "/").rsplit("/", 1)[-1] == name:
            return m.group(1).lower()
    return hashes[0] if len(hashes) == 1 else None


def _verified(data: bytes, sums: bytes, name: str | None) -> bytes:
    """Refuse a download whose SHA-256 doesn't match the one published with the release."""
    want = expected_sha256(sums.decode("utf-8", "replace"), name)
    if not want:
        raise LinkError("Couldn't check the download (no checksum published).")
    if hashlib.sha256(data).hexdigest() != want:
        raise LinkError("The download didn't match its checksum, so it wasn't used. Try again later.")
    return data


def _make_exec(p: Path) -> None:
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def ytdlp_command() -> list[str] | None:
    """How to run yt-dlp: Listo's own copy, else one on this computer."""
    own = tools_dir() / f"yt-dlp{EXE}"
    if own.is_file():
        return [str(own)]
    found = shutil.which("yt-dlp")
    if found:
        return [found]
    if not getattr(sys, "frozen", False):
        try:
            import yt_dlp  # noqa: F401

            return [sys.executable, "-m", "yt_dlp"]
        except ImportError:
            pass
    return None


def deno_path() -> str | None:
    own = tools_dir() / f"deno{EXE}"
    if own.is_file():
        return str(own)
    return shutil.which("deno")


_setup_lock = threading.Lock()


def ensure_tools(
    on_status: Callable[[str], None], cancel: threading.Event | None = None
) -> tuple[list[str], str | None]:
    """Make sure yt-dlp (and Deno) are available; download them the first time."""
    with _setup_lock:
        tdir = tools_dir()
        tdir.mkdir(parents=True, exist_ok=True)
        own = tdir / f"yt-dlp{EXE}"
        # The packaged app always uses its own copy (so it can update itself);
        # a source checkout uses any yt-dlp it can find unless LISTO_OWN_TOOLS=1.
        want_own = getattr(sys, "frozen", False) or os.environ.get("LISTO_OWN_TOOLS") == "1"
        if not own.is_file() and (want_own or ytdlp_command() is None):
            key = sys.platform if sys.platform in ("darwin", "win32") else f"linux-{_arch()}"
            url = YTDLP_URLS.get(key)
            if not url:
                raise LinkError("Link downloads aren't available on this kind of computer.")
            try:
                data = _fetch(url, on_status, "Setting up link downloads (one time)…", cancel)
                sums = _fetch(YTDLP_SUMS, lambda _: None, "", cancel)
            except Canceled:
                raise
            except Exception as e:
                log.warning("yt-dlp download failed", exc_info=True)
                raise LinkError(f"Couldn't download the link tool: {e}") from e
            data = _verified(data, sums, url.rsplit("/", 1)[-1])
            tmp = own.with_suffix(".part")
            tmp.write_bytes(data)
            _make_exec(tmp)
            os.replace(tmp, own)
            (tdir / "yt-dlp.updated").write_text(str(time.time()))
        deno_fail = tdir / "deno.failed"
        recently_failed = deno_fail.exists() and time.time() - deno_fail.stat().st_mtime < UPDATE_EVERY
        if not deno_path() and not recently_failed:
            target = {
                ("darwin", "aarch64"): "deno-aarch64-apple-darwin.zip",
                ("darwin", "x86_64"): "deno-x86_64-apple-darwin.zip",
                ("win32", "x86_64"): "deno-x86_64-pc-windows-msvc.zip",
                ("win32", "aarch64"): "deno-x86_64-pc-windows-msvc.zip",
                ("linux", "x86_64"): "deno-x86_64-unknown-linux-gnu.zip",
                ("linux", "aarch64"): "deno-aarch64-unknown-linux-gnu.zip",
            }.get(("linux" if sys.platform.startswith("linux") else sys.platform, _arch()))
            if target:
                try:
                    data = _fetch(
                        DENO_BASE + target, on_status, "Setting up YouTube support (one time)…", cancel
                    )
                    sums = _fetch(DENO_BASE + target + ".sha256sum", lambda _: None, "", cancel)
                    data = _verified(data, sums, None)
                    with zipfile.ZipFile(io.BytesIO(data)) as z:
                        name = next(n for n in z.namelist() if Path(n).name == f"deno{EXE}")
                        dest = tdir / f"deno{EXE}"
                        tmp = dest.with_name(dest.name + ".part")
                        tmp.write_bytes(z.read(name))
                        _make_exec(tmp)
                        os.replace(tmp, dest)
                    deno_fail.unlink(missing_ok=True)
                except Canceled:
                    raise
                except Exception:
                    log.warning("Deno setup failed; YouTube may not work", exc_info=True)
                    try:
                        deno_fail.write_text(str(time.time()))
                    except OSError:
                        pass
        cmd = ytdlp_command()
        if not cmd:
            raise LinkError("The link tool isn't available.")
        return cmd, deno_path()


def _kill_tree(proc: subprocess.Popen) -> None:
    """Stop a process and anything it started (yt-dlp may hand downloads to ffmpeg)."""
    if proc.poll() is not None:
        return
    try:
        if IS_WIN:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, **popen_kwargs()
            )
        else:
            import signal

            os.killpg(proc.pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        try:
            proc.terminate()
        except OSError:
            pass


def _group_kwargs() -> dict:
    return {} if IS_WIN else {"start_new_session": True}


def maybe_update(cmd: list[str], on_status: Callable[[str], None], job: LinkDownload | None = None) -> None:
    """Keep Listo's own yt-dlp fresh (at most once a day)."""
    own = tools_dir() / f"yt-dlp{EXE}"
    if cmd != [str(own)]:
        return
    with _setup_lock:
        _update_locked(cmd, on_status, job)


def _update_locked(cmd: list[str], on_status: Callable[[str], None], job: LinkDownload | None) -> None:
    stamp = tools_dir() / "yt-dlp.updated"
    try:
        last = float(stamp.read_text())
    except (OSError, ValueError):
        last = 0.0
    if time.time() - last < UPDATE_EVERY:
        return
    on_status("Checking for link tool updates…")
    try:
        proc = subprocess.Popen(
            [*cmd, "-U"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **popen_kwargs(),
            **_group_kwargs(),
        )
        if job is not None:
            job.proc = proc
            if job._canceled:
                _kill_tree(proc)
        try:
            proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
    except OSError:
        pass
    if job is not None and job._canceled:
        raise Canceled()
    try:
        stamp.write_text(str(time.time()))
    except OSError:
        pass


class LinkDownload:
    """Download one link. run() blocks; cancel() from any thread."""

    def __init__(self, url: str, dest: Path | None = None):
        self.url = url.strip()
        self.dest = dest or downloads_dir()
        self.proc: subprocess.Popen | None = None
        self._canceled = False
        self._cancel_ev = threading.Event()
        self.title = ""

    def cancel(self) -> None:
        self._canceled = True
        self._cancel_ev.set()
        p = self.proc
        if p is not None:
            _kill_tree(p)

    def run(self, on_progress: Callable[[float, str], None], on_title: Callable[[str], None]) -> str:
        status = lambda text: on_progress(-1.0, text)  # noqa: E731
        cmd, deno = ensure_tools(status, self._cancel_ev)
        if self._canceled:
            raise Canceled()
        maybe_update(cmd, status, self)
        if self._canceled:
            raise Canceled()
        self.dest.mkdir(parents=True, exist_ok=True)
        caps = capabilities()
        args = [
            *cmd,
            "--no-playlist",
            "-I",
            "1",
            "--newline",
            "--progress",
            "--no-simulate",
            "--no-colors",
            "--print",
            "before_dl:LISTO_TITLE %(title)s",
            "--print",
            "after_move:LISTO_FILE %(filepath)s",
            "--progress-template",
            "download:LISTO_PROG %(progress._percent_str)s|%(progress._eta_str)s",
            "--progress-template",
            "postprocess:LISTO_PP %(progress.postprocessor)s|%(progress.status)s",
            "-f",
            "bv*[vcodec^=avc1]+ba[ext=m4a]/bv*+ba/b",
            "--merge-output-format",
            "mp4/mkv",
            "--windows-filenames",
            "--no-mtime",
            "-o",
            "%(title).120B [%(id)s].%(ext)s",
            "-P",
            str(self.dest),
        ]
        if caps.ffmpeg:
            args += ["--ffmpeg-location", str(Path(caps.ffmpeg).parent)]
        if deno:
            args += ["--js-runtimes", f"deno:{deno}"]
        args.append(self.url)
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            **popen_kwargs(),
            **_group_kwargs(),
        )
        if self._canceled:
            self.cancel()
        path = ""
        errors: list[str] = []
        streams = 0
        last_pct = 0.0
        if self.proc.stdout is None:
            raise LinkError("Couldn't start the download.")
        for raw in self.proc.stdout:
            line = raw.strip()
            if line.startswith("LISTO_TITLE "):
                self.title = line[len("LISTO_TITLE ") :]
                on_title(self.title)
            elif line.startswith("LISTO_FILE "):
                path = line[len("LISTO_FILE ") :]
            elif line.startswith("LISTO_PROG "):
                pct_s, _, eta = line[len("LISTO_PROG ") :].partition("|")
                try:
                    pct = float(pct_s.strip().rstrip("%"))
                except ValueError:
                    continue
                if pct + 50 < last_pct:  # a second stream (the sound) started
                    streams += 1
                last_pct = pct
                part = " sound" if streams else ""
                text = f"Downloading{part} {int(pct)}%"
                if eta.strip() and eta.strip() not in ("NA", "Unknown", "00:00"):
                    text += f" · {eta.strip()} left"
                on_progress(pct / 100.0, text)
            elif line.startswith("LISTO_PP ") or line.startswith("[Merger]"):
                if "Merger" in line or "started" in line:
                    on_progress(1.0, "Putting it together…")
            elif line.startswith("ERROR:"):
                errors.append(line[len("ERROR:") :].strip())
        rc = self.proc.wait()
        if self._canceled:
            raise Canceled()
        if rc != 0 or not path or not Path(path).is_file():
            msg = errors[-1] if errors else "The download didn't finish."
            raise LinkError(_friendly(msg))
        return path


def _friendly(msg: str) -> str:
    low = msg.lower()
    if "unsupported url" in low:
        return "Listo can't download from that site."
    if "private video" in low or "sign in" in low or "login" in low:
        return "That video needs a sign-in, so it can't be downloaded."
    if "unavailable" in low:
        return "That video isn't available."
    if "unable to download webpage" in low or "name or service not known" in low or "timed out" in low:
        return "Couldn't reach that link — check your internet connection."
    return msg
