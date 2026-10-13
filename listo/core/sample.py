"""A sample clip for the live preview when the list is empty (a soft, slowly moving colour gradient
with timecode, a recording date and a tone), made once with Listo's ffmpeg and kept in the data folder."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime

from listo.core.log import get_logger
from listo.core.paths import data_dir
from listo.core.tools import capabilities, popen_kwargs

log = get_logger(__name__)
NAME = "sample-v2.mov"  # bump the number when the look changes


# Calm, clean colours (no test-pattern lines): deep blue → teal → warm amber → magenta.
GRADIENT = (
    "gradients=s=1920x1080:r=30000/1001:d=6:speed=0.008:nb_colors=4"
    ":c0=0x1f3b73:c1=0x1f8a8a:c2=0xe0a040:c3=0xa0306a:x0=0:y0=0:x1=1920:y1=1080"
)


def sample_clip_if_made() -> str | None:
    """The sample clip if it's already been made (no waiting on ffmpeg)."""
    target = data_dir() / "sample" / NAME
    return str(target) if target.is_file() else None


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
        "-f", "lavfi", "-i", GRADIENT,
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
