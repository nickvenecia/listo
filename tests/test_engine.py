"""The whole conversion pipeline: verification and running two at once.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from listo.core import naming
from listo.core.engine import Conversion
from listo.core.presets import Settings
from listo.core.probe import probe
from listo.core.tools import capabilities
from tests.helpers import HAS_FFMPEG, camcorder_clip, ff


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


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("preset", ["h264", "prores", "rewrap", "webm"])
def test_camcorder_recording_time_travels_with_the_file(tmp_path: Path, preset: str, caplog):
    """A .MOD + .MOI converted: copy only the new file somewhere else, delete the clip and its .MOI,
    and the recording date and time still come back (to the second, in this computer's zone)."""
    import logging

    from listo.core.probe import file_date

    card = tmp_path / "card"
    card.mkdir()
    clip = camcorder_clip(card, "MOV01A", (2007, 7, 14, 19, 22, 5))
    s = Settings(video_preset=preset, destination="folder", dest_folder=str(tmp_path / "out"))
    with caplog.at_level(logging.INFO, logger="listo"):
        r = Conversion(str(clip), probe(clip), s, capabilities(), set()).run()
    assert r.status == "done", (r.message, r.log)
    assert "recording time stored" in caplog.text and "2007-07-14T19:22:05" in caplog.text
    uploaded = tmp_path / "uploaded"
    uploaded.mkdir()
    copy = uploaded / r.output.name
    shutil.copyfile(r.output, copy)  # only what's inside the file travels (no file dates)
    shutil.rmtree(card)
    got = probe(copy)
    shot = datetime(2007, 7, 14, 19, 22, 5)
    assert got.created.replace(tzinfo=None) == shot
    assert got.created.utcoffset() == shot.astimezone().utcoffset()  # this computer's zone on that date
    assert got.creation_time == shot.astimezone(UTC)
    assert file_date(copy, got) == shot  # what Listo's date burn-in and {date} names read
    if preset == "h264":
        data = copy.read_bytes()
        assert data.index(b"moov") < data.index(b"mdat")  # still fast-start (plays while downloading)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_trimmed_clip_gets_the_time_of_its_new_first_frame(tmp_path: Path):
    clip = camcorder_clip(tmp_path, "MOV01A", (2007, 7, 14, 19, 22, 5), secs=4)
    s = Settings(video_preset="h264")
    r = Conversion(str(clip), probe(clip), s, capabilities(), set(), trim=(2.0, 3.5)).run()
    assert r.status == "done", (r.message, r.log)
    assert probe(r.output).created.replace(tzinfo=None) == datetime(2007, 7, 14, 19, 22, 7)  # 05.25 + 2 s


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("preset", ["h264", "prores"])
def test_clip_with_its_own_creation_time_keeps_it(tmp_path: Path, preset: str):
    plain = tmp_path / "plain.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=1", "-c:v", "libx264",
       "-metadata", "creation_time=2024-05-01T18:30:00Z", str(plain))  # fmt: skip
    phone = tmp_path / "phone.mov"  # like an iPhone: local time with its zone + its own creation_time
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=1", "-c:v", "libx264", "-movflags", "use_metadata_tags",
       "-metadata", "com.apple.quicktime.creationdate=2019-08-11T19:13:57+0200",
       "-metadata", "creation_time=2019-08-11T17:14:12Z", str(phone))  # fmt: skip
    s = Settings(video_preset=preset, destination="folder", dest_folder=str(tmp_path / "out"))
    for src, created in (
        (plain, "2024-05-01T18:30:00+00:00"),
        (phone, "2019-08-11T19:13:57+02:00"),
    ):
        before = probe(src)
        r = Conversion(str(src), before, s, capabilities(), set()).run()
        assert r.status == "done", (r.message, r.log)
        got = probe(r.output)
        assert got.creation_time == before.creation_time
        assert got.created == before.created and before.created.isoformat() == created
        if src is phone:
            assert got.created.isoformat() == created  # the zone it was shot in, not this computer's
