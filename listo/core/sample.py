"""A sample clip for the live preview when the list is empty (a colour test pattern with timecode,
a recording date and a tone), made once with Listo's ffmpeg and kept in the data folder."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime

from .log import get_logger
from .paths import data_dir
from .tools import capabilities, popen_kwargs

log = get_logger(__name__)
NAME = "sample-v1.mov"


def sample_clip() -> str | None:
    target = data_dir() / "sample" / NAME
    if target.is_file():
        return str(target)
    caps = capabilities()
    if not caps.ffmpeg:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(".making-" + NAME)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    cmd = [
        caps.ffmpeg, "-hide_banner", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30000/1001:d=6",
        "-f", "lavfi", "-i", "sine=frequency=440:d=6",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-timecode", "01:00:00;00", "-metadata", f"creation_time={now}", "-f", "mov", str(tmp),
    ]  # fmt: skip
    try:
        subprocess.run(
            cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=60, check=True, **popen_kwargs()
        )
        tmp.replace(target)
        return str(target)
    except (OSError, subprocess.SubprocessError):
        log.warning("couldn't make the sample clip", exc_info=True)
        tmp.unlink(missing_ok=True)
        return None
