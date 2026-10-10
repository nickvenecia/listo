"""Shared test helpers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

HAS_FFMPEG = shutil.which("ffmpeg") is not None


def ff(*args: str) -> None:
    """Run ffmpeg quietly (used to generate small test clips)."""
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *args], check=True)


def write_moi(path: Path, when: tuple[int, int, int, int, int, int], aspect_byte: int = 0x44) -> None:
    """A JVC .MOI sidecar recorded at `when` (+ 250 ms) local time; 0x44 = 16:9 NTSC."""
    y, mo, d, h, mi, sec = when
    data = bytearray(0x100)
    data[0:2] = b"V6"
    data[6:8] = y.to_bytes(2, "big")
    data[8:12] = bytes([mo, d, h, mi])
    data[12:14] = (sec * 1000 + 250).to_bytes(2, "big")
    data[0x80] = aspect_byte
    path.write_bytes(bytes(data))


def camcorder_clip(folder: Path, name: str, when: tuple[int, int, int, int, int, int], secs: int = 2) -> Path:
    """A JVC-style .MOD (MPEG-2 program stream with sound, no date inside) and its .MOI."""
    clip = folder / f"{name}.MOD"
    ff("-f", "lavfi", "-i", f"testsrc2=s=320x240:r=30000/1001:d={secs}", "-f", "lavfi", "-i", f"sine=d={secs}",
       "-c:v", "mpeg2video", "-c:a", "mp2", "-f", "vob", str(clip))  # fmt: skip
    write_moi(clip.with_suffix(".MOI"), when)
    return clip
