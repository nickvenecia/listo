"""Download static ffmpeg + ffprobe for this computer into vendor/ffmpeg/.

    python scripts/fetch_ffmpeg.py

The packaged app bundles whatever is in vendor/ffmpeg/, so people who download
Listo never have to install anything. Sources:
  macOS / Linux : https://ffmpeg.martin-riedl.de  (static release builds)
  Windows       : https://github.com/BtbN/FFmpeg-Builds (static GPL release builds)
"""
from __future__ import annotations

import io
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "vendor" / "ffmpeg"
UA = {"User-Agent": "listo-build"}


def get(url: str, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def arch() -> str:
    m = platform.machine().lower()
    return "arm64" if m in ("arm64", "aarch64") else "amd64"


def riedl(os_name: str) -> None:
    for tool in ("ffmpeg", "ffprobe"):
        url = f"https://ffmpeg.martin-riedl.de/redirect/latest/{os_name}/{arch()}/release/{tool}.zip"
        print("downloading", url)
        with zipfile.ZipFile(io.BytesIO(get(url))) as z:
            name = next(n for n in z.namelist() if Path(n).name == tool)
            target = DEST / tool
            target.write_bytes(z.read(name))
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def btbn_windows() -> None:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = None
    try:
        rel = json.loads(get("https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/latest", headers))
        pat = re.compile(r"ffmpeg-n(\d+)\.(\d+)(?:\.\d+)?-latest-win64-gpl-\d+\.\d+\.zip$")
        best = None
        for a in rel.get("assets", []):
            m = pat.search(a["name"])
            if m:
                ver = (int(m.group(1)), int(m.group(2)))
                if best is None or ver > best[0]:
                    best = (ver, a["browser_download_url"])
        if best:
            url = best[1]
    except Exception as e:  # noqa: BLE001
        print("GitHub API lookup failed, using master build:", e)
    url = url or "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    print("downloading", url)
    with zipfile.ZipFile(io.BytesIO(get(url))) as z:
        for tool in ("ffmpeg.exe", "ffprobe.exe"):
            name = next(n for n in z.namelist() if n.endswith("/bin/" + tool))
            (DEST / tool).write_bytes(z.read(name))
        lic = next((n for n in z.namelist() if n.endswith("LICENSE.txt")), None)
        if lic:
            (DEST / "LICENSE.txt").write_bytes(z.read(lic))


def main() -> int:
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    if sys.platform == "darwin":
        riedl("macos")
    elif sys.platform.startswith("linux"):
        riedl("linux")
    elif sys.platform == "win32":
        btbn_windows()
    else:
        print("Unsupported platform", sys.platform)
        return 1
    (DEST / "README.txt").write_text(
        "These are unmodified static builds of FFmpeg (https://ffmpeg.org), licensed under the GPL.\n"
        "Source code: https://ffmpeg.org/download.html\n"
        "macOS/Linux builds: https://ffmpeg.martin-riedl.de  ·  Windows builds: https://github.com/BtbN/FFmpeg-Builds\n"
    )
    exe = ".exe" if sys.platform == "win32" else ""
    out = subprocess.run([str(DEST / f"ffmpeg{exe}"), "-hide_banner", "-version"], capture_output=True, text=True)
    print(out.stdout.splitlines()[0] if out.stdout else out.stderr)
    enc = subprocess.run([str(DEST / f"ffmpeg{exe}"), "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    for e in ("prores_ks", "dnxhd", "libx264", "libx265", "libsvtav1", "libvpx-vp9", "libmp3lame", "libopus"):
        print(f"  {e:12} {'yes' if (' ' + e + ' ') in enc else 'MISSING'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
