"""The command-line tool (`python -m listo cli ...`) and module wiring.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

import listo
from listo import cli

from .helpers import HAS_FFMPEG, ff


def test_every_module_imports():
    """Catches stale imports after files move (a missing module only fails when its code runs)."""
    for mod in pkgutil.walk_packages(listo.__path__, "listo."):
        if not mod.name.endswith("__main__"):  # that one starts the app
            importlib.import_module(mod.name)


def test_cli_converts_a_photo(tmp_path: Path):
    from PIL import Image

    src = tmp_path / "p.png"
    Image.new("RGB", (40, 30), (200, 100, 50)).save(src)
    assert cli.main([str(src), "--photo", "jpeg"]) == 0
    assert (tmp_path / "p.jpg").is_file()


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_cli_converts_a_video(tmp_path: Path):
    src = tmp_path / "clip.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=160x120:d=0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src))
    assert cli.main([str(src), "--video", "prores", "--out", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "clip.mov").is_file()


def test_photo_thumbnail():
    pytest.importorskip("PySide6")
    import io
    import tempfile

    from PIL import Image

    from listo.ui import workers

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.png"
        Image.new("RGB", (300, 200), (10, 20, 30)).save(p)
        data = workers.photo_thumb(str(p))
    assert data and Image.open(io.BytesIO(data)).size[0] > 0
