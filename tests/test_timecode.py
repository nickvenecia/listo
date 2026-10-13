"""Timecode for clips without their own (camcorders, phones): Continuous (one Convert = one tape),
Restart Each Clip, or Match Record Time. Burned in and stored in the file.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

import pytest

from listo.core import join
from listo.core.engine import Conversion
from listo.core.presets import Settings, timecode_mode
from listo.core.probe import MediaInfo, probe, record_timecode, tc_add
from listo.core.tools import capabilities

from .helpers import HAS_FFMPEG, camcorder_clip, ff


def test_record_time_is_the_time_of_day_it_was_shot():
    """Same clock as the Date & Time burn-in (the .MOI's 19:22:05.25), counted in frames."""
    moi = MediaInfo(kind="video", rate="25/1", created=datetime(2007, 7, 14, 19, 22, 5, 250000))
    assert record_timecode("MOV01A.MOD", moi) == "19:22:05:07"
    assert record_timecode("MOV01A.MOD", moi, start_s=2.0) == "19:22:07:07"  # trimmed: the new first frame
    moi.rate = "30000/1001"  # NTSC camcorders: drop-frame, which keeps close to the clock all day
    assert record_timecode("MOV01A.MOD", moi).startswith("19:22:05;")
    late = MediaInfo(kind="video", rate="25/1", created=datetime(2007, 7, 14, 23, 59, 59, 900000))
    assert record_timecode("x.MOD", late, start_s=1.0) == "00:00:00:23"  # past midnight
    assert record_timecode("x.MOD", MediaInfo(kind="video", created=moi.created)) == ""  # no frame rate


def test_continuous_timecode_can_start_partway_into_the_tape():
    clip = MediaInfo(kind="video", rate="25/1")
    assert join.running_timecodes([(clip, 10.0), (clip, 5.0)], start=60.0) == ["00:01:00:00", "00:01:10:00"]


def test_rewrap_and_sound_keep_the_old_rule():
    """They can't show timecode (the choice is hidden), so a joined video runs on and separate files don't."""
    s = Settings(video_preset="rewrap", timecode_mode="record")
    assert timecode_mode(s) == "restart" and timecode_mode(s, joining=True) == "continuous"
    assert timecode_mode(Settings(timecode_mode="record")) == "record"
    assert timecode_mode(Settings(timecode_mode="record"), preset="audio") == "restart"  # a file's own format
    assert timecode_mode(Settings(timecode_mode="nonsense")) == "continuous"
    assert Settings.complete({})["timecode_mode"] == "continuous"  # old recipes: like a joined video was


def _clip(path: Path, rate: str = "25", secs: int = 1) -> Path:
    ff("-f", "lavfi", "-i", f"testsrc2=s=320x240:r={rate}:d={secs}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
       str(path))  # fmt: skip
    return path


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_match_record_time_is_burned_and_stored(tmp_path: Path):
    clip = camcorder_clip(tmp_path, "MOV01A", (2007, 7, 14, 19, 22, 5))
    info = probe(clip)
    s = Settings(video_preset="h264", burn_timecode=True, timecode_mode="record")
    r = Conversion(str(clip), info, s, capabilities(), set(), trim=(1.0, 1.8)).run()
    assert r.status == "done", (r.message, r.log)
    want = record_timecode(clip, info, 1.0)
    assert want.startswith("19:22:06;") and want in r.command
    assert probe(r.output).timecode == want  # an editing app reads the same time
    restart = Conversion(str(clip), info, Settings(video_preset="h264"), capabilities(), set()).run()
    assert not probe(restart.output).timecode  # without a place on a tape: nothing made up


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_preview_shows_the_continuous_timecode(monkeypatch):
    """The preview runs the clock on from where the clip's place on the tape starts."""
    from listo.core import video
    from listo.core.sample import sample_clip

    got = {}
    real = video.build

    def spy(*a, **k):
        got["tc"] = k.get("timecode", "")
        return real(*a, **k)

    monkeypatch.setattr(video, "build", spy)
    src = sample_clip()
    info = probe(src)
    s = Settings(video_preset="h264", burn_timecode=True)
    _, plan = video.preview_plan(src, info, s, capabilities(), 2.0, os.devnull, clock=(0.0, "00:10:00:00"))
    plan.cleanup()
    assert got["tc"] == tc_add("00:10:00:00", 2.0, info.rate)  # 2 s in


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_command_line_runs_the_timecode_on(tmp_path: Path):
    from listo import cli

    a, b = _clip(tmp_path / "a.mp4", secs=2), _clip(tmp_path / "b.mp4")
    out = tmp_path / "out"
    assert cli.main([str(a), str(b), "--video", "h264", "--out", str(out)]) == 0
    assert probe(out / "a.mp4").timecode == "00:00:00:00"
    assert probe(out / "b.mp4").timecode == "00:00:02:00"  # carries on after the first clip
    assert cli.main([str(b), "--video", "h264", "--out", str(out), "--timecode", "restart"]) == 0
    assert not probe(out / "b_1.mp4").timecode


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("mode", ["continuous", "restart", "record"])
def test_window_gives_separate_files_their_timecode(tmp_path: Path, monkeypatch, mode: str):
    """Separate files follow the same choice as a joined video, and the previews show what Convert gives."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    import listo.ui.window.main_window as mw

    given = []
    real = mw.Conversion

    def spy(*a, **k):
        given.append(k.get("timecode", ""))
        return real(*a, **k)

    monkeypatch.setattr(mw, "Conversion", spy)
    app = QApplication.instance() or QApplication([])
    src = tmp_path / "src"
    src.mkdir()
    clips = [_clip(src / f"{n}.mp4", secs=s) for n, s in (("a", 2), ("b", 1), ("c", 1))]
    w = mw.MainWindow()
    w.settings.video_preset, w.settings.timecode_mode = "h264", mode
    w.add_paths([str(c) for c in clips])
    end = time.monotonic() + 60
    while not all(it.state == "ready" for it in w.items.values()) and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    items = [w.items[i] for i in w.order]
    preview = w._clocks()
    w.start()
    end = time.monotonic() + 120
    while w.running and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    stored = [probe(it.result.output).timecode for it in items]
    if mode == "continuous":
        assert given == ["00:00:00:00", "00:00:02:00", "00:00:03:00"]  # one tape, list order
        assert [preview[it.id][1] for it in items] == given  # the preview knew
        assert stored == given
    elif mode == "restart":
        assert given == ["", "", ""] and preview == {}
        assert stored == ["", "", ""]
    else:
        assert given == ["", "", ""]  # each clip works out its own time of day
        assert stored == [record_timecode(it.path, it.info) for it in items] and all(stored)
    w.close()
    app.processEvents()
