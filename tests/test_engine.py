"""The whole conversion pipeline: verification and running two at once.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from listo.core import naming
from listo.core.engine import Conversion
from listo.core.presets import Settings
from listo.core.probe import probe
from listo.core.tools import capabilities
from tests.helpers import HAS_FFMPEG, ff


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_verify_catches_short_output(tmp_path: Path, monkeypatch):
    from listo.core import engine

    src = tmp_path / "a.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=3", "-c:v", "libx264", str(src))
    info = probe(src)
    info.duration = 60.0  # pretend the original was a minute long
    r = engine.Conversion(str(src), info, Settings(video_preset="h264"), capabilities(), set()).run()
    assert r.status == "done" and "doesn't match" in r.warning


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_two_at_once_never_share_a_name(tmp_path: Path):
    import threading

    srcs = []
    for sub in ("card1", "card2"):
        (tmp_path / sub).mkdir()
        p = tmp_path / sub / "00000.MTS"
        ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=1", "-c:v", "libx264", "-f", "mpegts", str(p))
        srcs.append(p)
    out = tmp_path / "out"
    s = Settings(video_preset="h264", destination="folder", dest_folder=str(out))
    reserved = {naming.reserve_key(p) for p in srcs}
    results = []
    ts = [
        threading.Thread(
            target=lambda p=p: results.append(Conversion(str(p), probe(p), s, capabilities(), reserved).run())
        )
        for p in srcs
    ]
    [t.start() for t in ts]
    [t.join() for t in ts]
    names = sorted(r.output.name for r in results)
    # the second one gets its card folder's name (which one depends on which finished planning first)
    assert names[0] == "00000.mp4" and names[1] in ("00000_card1.mp4", "00000_card2.mp4")
