"""Finding ffmpeg/ffprobe and learning what they can do.

Lookup order:
  1. $LISTO_FFMPEG_DIR
  2. Bundled copy inside the packaged app (PyInstaller) -> <bundle>/ffmpeg/
  3. vendor/ffmpeg/ in a source checkout (scripts/fetch_ffmpeg.py puts it there)
  4. PATH and the usual Homebrew / system locations
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
EXE = ".exe" if IS_WIN else ""


def popen_kwargs() -> dict:
    """Keeps Windows from flashing a console window for every ffmpeg call."""
    if IS_WIN:
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    env = os.environ.get("LISTO_FFMPEG_DIR")
    if env:
        dirs.append(Path(env))
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        dirs += [base / "ffmpeg", Path(sys.executable).parent / "ffmpeg"]
    repo = Path(__file__).resolve().parent.parent
    dirs.append(repo / "vendor" / "ffmpeg")
    return dirs


def find_tool(name: str) -> str | None:
    for d in _candidate_dirs():
        p = d / f"{name}{EXE}"
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    found = shutil.which(name)
    if found:
        return found
    for d in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"):
        p = Path(d) / name
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def run_quiet(args: list[str], timeout: float = 30) -> tuple[int, str]:
    """Run a short command, capturing everything safely (no pipe deadlocks)."""
    try:
        cp = subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **popen_kwargs(),
        )
        return cp.returncode, (cp.stdout or "") + (cp.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return -1, str(e)


@dataclass
class Capabilities:
    ffmpeg: str | None = None
    ffprobe: str | None = None
    version: str = ""
    encoders: set[str] = field(default_factory=set)
    filters: set[str] = field(default_factory=set)
    hw: dict[str, str] = field(default_factory=dict)  # "h264"/"hevc" -> encoder name
    hw_checked: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.ffmpeg and self.ffprobe)

    def has_encoder(self, name: str) -> bool:
        return name in self.encoders

    def has_filter(self, name: str) -> bool:
        return name in self.filters


def _parse_names(text: str, header_end: str) -> set[str]:
    names: set[str] = set()
    started = False
    for line in text.splitlines():
        if not started:
            if line.strip().startswith(header_end):
                started = True
            continue
        parts = line.split()
        if len(parts) >= 2:
            names.add(parts[1])
    return names


_caps: Capabilities | None = None
_caps_lock = threading.Lock()


def capabilities(refresh: bool = False) -> Capabilities:
    global _caps
    with _caps_lock:
        if _caps is not None and not refresh:
            return _caps
        caps = Capabilities(ffmpeg=find_tool("ffmpeg"), ffprobe=find_tool("ffprobe"))
        if caps.ffmpeg:
            _, out = run_quiet([caps.ffmpeg, "-hide_banner", "-version"])
            caps.version = out.splitlines()[0] if out else ""
            _, enc = run_quiet([caps.ffmpeg, "-hide_banner", "-encoders"])
            caps.encoders = _parse_names(enc, "------")
            _, flt = run_quiet([caps.ffmpeg, "-hide_banner", "-filters"])
            # filter lines look like: " TS. bwdif   V->V   Deinterlace..."
            caps.filters = {
                ln.split()[1]
                for ln in flt.splitlines()
                if len(ln.split()) >= 3 and "->" in ln.split()[2]
            }
        _caps = caps
        return caps


HW_CANDIDATES = {
    "h264": ["h264_videotoolbox", "h264_nvenc"],
    "hevc": ["hevc_videotoolbox", "hevc_nvenc"],
}


def detect_hardware(caps: Capabilities) -> dict[str, str]:
    """Try a tiny real encode with each hardware encoder; keep the ones that work."""
    if caps.hw_checked or not caps.ffmpeg:
        return caps.hw
    found: dict[str, str] = {}
    for codec, encs in HW_CANDIDATES.items():
        for enc in encs:
            if enc not in caps.encoders:
                continue
            rc, _ = run_quiet(
                [
                    caps.ffmpeg, "-hide_banner", "-v", "error",
                    "-f", "lavfi", "-i", "testsrc2=s=640x360:d=0.2",
                    "-c:v", enc, "-b:v", "2M", "-f", "null", "-",
                ],
                timeout=20,
            )
            if rc == 0:
                found[codec] = enc
                break
    caps.hw = found
    caps.hw_checked = True
    return found
