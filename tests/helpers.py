"""Shared test helpers."""

from __future__ import annotations

import shutil
import subprocess

HAS_FFMPEG = shutil.which("ffmpeg") is not None


def ff(*args: str) -> None:
    """Run ffmpeg quietly (used to generate small test clips)."""
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *args], check=True)
