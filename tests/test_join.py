"""Join: several clips -> one long video (core/join.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from listo.core import join
from listo.core.captions import Cue
from listo.core.engine import Conversion
from listo.core.presets import Settings
from listo.core.probe import probe
from listo.core.tools import capabilities

from .helpers import HAS_FFMPEG, camcorder_clip, ff

pytestmark = pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")


def _clip(path: Path, size: str, rate: str, secs: int, sound: bool = True, ar: int = 48000) -> Path:
    args = ["-f", "lavfi", "-i", f"testsrc2=s={size}:r={rate}:d={secs}"]
    if sound:
        args += ["-f", "lavfi", "-i", f"sine=d={secs}:r={ar}", "-shortest", "-c:a", "aac"]
    ff(*args, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))
    return path


def _convert_parts(clips, s, folder, trims=None):
    caps = capabilities()
    first = probe(clips[0])
    conform = join.conform_for(first, s)
    parts = []
    for n, c in enumerate(clips, 1):
        target = join.part_path(folder, n, s)
        folder.mkdir(exist_ok=True)
        part_s = s.copy()
        part_s.caption_srt = False
        r = Conversion(
            str(c),
            probe(c),
            part_s,
            caps,
            set(),
            n,
            trim=(trims or {}).get(n),
            target=target,
            conform=conform,
        ).run()
        assert r.status == "done", r.message
        parts.append(target)
    return parts


@pytest.mark.parametrize("preset", ["prores", "h264"])
def test_clips_of_different_shapes_join_into_one_video(tmp_path: Path, preset: str):
    a = _clip(tmp_path / "a.mp4", "640x360", "30000/1001", 2)
    b = _clip(tmp_path / "b.mp4", "480x480", "25", 2, sound=False)  # square, other rate, silent
    c = _clip(tmp_path / "c.mp4", "1280x720", "30000/1001", 3, ar=44100)
    s = Settings(video_preset=preset, join=True, captions=True, caption_srt=True)
    folder = join.parts_folder(str(a), s)
    parts = _convert_parts([a, b, c], s, folder, trims={3: (1.0, 3.0)})
    cues = [[Cue(0.2, 1.0, "First clip.")], None, [Cue(0.5, 1.5, "Third clip.")]]
    r = join.Join(parts, str(a), probe(a), s, capabilities(), set(), cues, last_src=str(c)).run()
    assert r.status == "done", (r.message, r.log)
    assert not r.warning, r.warning
    assert r.output.name == f"a-c.{'mov' if preset == 'prores' else 'mp4'}"
    got = probe(r.output)
    assert (got.width, got.height) == (640, 360)
    assert abs(got.duration - 6.0) < 0.3  # 2 + 2 + the trimmed 2
    assert got.audio  # the silent clip got a silent track, so sound runs the whole way
    assert not folder.exists()  # the parts are cleaned up
    srt = r.output.with_suffix(".srt").read_text()
    assert "First clip." in srt and "Third clip." in srt
    assert "00:00:04,5" in srt  # shifted past the first two clips (each ends on a whole frame)


def test_joined_video_carries_the_first_clips_recording_time(tmp_path: Path):
    from datetime import datetime

    a = camcorder_clip(tmp_path, "MOV001", (2007, 7, 14, 19, 22, 5))
    b = camcorder_clip(tmp_path, "MOV002", (2007, 7, 15, 9, 0, 0))
    s = Settings(video_preset="h264", join=True)
    folder = join.parts_folder(str(a), s)
    parts = _convert_parts([a, b], s, folder, trims={1: (1.0, 2.0)})
    r = join.Join(parts, str(a), probe(a), s, capabilities(), set(), last_src=str(b)).run()
    assert r.status == "done", (r.message, r.log)
    got = probe(r.output)
    assert got.created.replace(tzinfo=None) == datetime(2007, 7, 14, 19, 22, 6)  # first clip, from its trim
    assert got.creation_time == got.created


def test_rewrap_only_joins_clips_that_already_match(tmp_path: Path):
    a = _clip(tmp_path / "a.mov", "640x360", "25", 1)
    b = _clip(tmp_path / "b.mov", "640x360", "25", 1)
    c = _clip(tmp_path / "c.mov", "320x240", "25", 1)
    s = Settings(video_preset="rewrap", join=True)
    folder = join.parts_folder(str(a), s)
    ok = join.Join(_convert_parts([a, b], s, folder), str(a), probe(a), s, capabilities(), set()).run()
    assert ok.status == "done", ok.message
    assert abs(probe(ok.output).duration - 2.0) < 0.2
    folder2 = join.parts_folder(str(a), s)
    bad = join.Join(_convert_parts([a, c], s, folder2), str(a), probe(a), s, capabilities(), set()).run()
    assert bad.status == "failed"
    assert "same picture size" in bad.message and "Rewrap" in bad.message
    assert not folder2.exists()


def test_gif_never_joins():
    assert not join.can_join(Settings(video_preset="gif"))
    assert join.joins(Settings(video_preset="h264", join=True), "video")
    assert not join.joins(Settings(video_preset="h264", join=True), "photo")


def test_burn_ins_and_a_silent_clip_join(tmp_path: Path):
    """Burn-in images and the silent sound track are both extra inputs: their numbers must not clash."""
    a = _clip(tmp_path / "a.mp4", "640x360", "25", 1)
    b = _clip(tmp_path / "b.mp4", "320x240", "25", 1, sound=False)
    s = Settings(video_preset="h264", join=True, burn_filename=True, burn_style="vhs", burn_datetime=True)
    folder = join.parts_folder(str(a), s)
    r = join.Join(_convert_parts([a, b], s, folder), str(a), probe(a), s, capabilities(), set()).run()
    assert r.status == "done", r.message
    got = probe(r.output)
    assert (got.width, got.height) == (640, 360) and got.audio and abs(got.duration - 2.0) < 0.2


def test_window_joins_the_list_into_one_video(tmp_path: Path, monkeypatch):
    import os
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    import listo.ui.panels.convert as sb
    import listo.ui.panels.export as ep
    import listo.ui.window.main_window as mw

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb, ep):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    app = QApplication.instance() or QApplication([])
    src = tmp_path / "src"
    src.mkdir()
    a = _clip(src / "a.mp4", "640x360", "25", 1)
    b = _clip(src / "b.mp4", "320x240", "25", 2)
    w = mw.MainWindow()
    w.settings.video_preset = "h264"

    def wait(cond, timeout=60):
        end = time.monotonic() + timeout
        while not cond() and time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)
        return cond()

    w.add_paths([str(a), str(b)])
    assert wait(lambda: all(it.state == "ready" for it in w.items.values()))
    assert w.export_panel.videos_sec.isVisibleTo(w.export_panel)  # 2 videos: the choice appears
    ep.set_combo(w.export_panel.join_pick, "join")
    w.export_panel._set("join", True)
    assert w.btn_start.text() == "Convert && Join 2 Files"
    w.start()
    ok = wait(lambda: not w.running and all(it.state == "done" for it in w.items.values()))
    assert ok, [(it.state, it.message) for it in w.items.values()]
    outs = sorted(p.name for p in src.iterdir() if p.suffix == ".mp4" and p.stem not in ("a", "b"))
    assert outs == ["a-b.mp4"], outs
    assert not any(p.name.startswith(".listo-join-") for p in src.iterdir())
    assert abs(probe(src / "a-b.mp4").duration - 3.0) < 0.2
    assert all(it.result.output == src / "a-b.mp4" for it in w.items.values())
    w.close()
    app.processEvents()


def test_joined_name_covers_first_to_last():
    s = Settings(video_preset="prores")
    assert join.joined_name("/f/MOV001.MOD", None, s, "/f/MOV014.MOD") == "MOV001-MOV014.mov"
    s.naming = "{name}_{preset}"
    assert join.joined_name("/f/A.mov", None, s, "/f/B.mov") == "A-B_prores422.mov"
    # PRG001/MOV01A + PRG002/MOV01A: same name twice -> no "MOV01A-MOV01A"
    assert join.joined_name("/a/PRG001/MOV01A.MOD", None, Settings(), "/a/PRG002/MOV01A.MOD").startswith(
        "MOV01A_joined"
    )


def test_joined_clips_without_timecode_count_on_like_a_tape():
    """One Convert = one tape: clips without timecode (camcorder .MOD, phones) continue the counter
    from clip to clip through the whole joined video, across days too. Real timecode is kept."""
    from datetime import datetime

    from listo.core.probe import MediaInfo

    def clip(day: int, tc: str = "") -> MediaInfo:
        return MediaInfo(kind="video", rate="30000/1001", fps=29.97, timecode=tc,
                         created=datetime(2024, 5, day, 12, 0))  # fmt: skip

    tcs = join.running_timecodes(
        [
            (clip(26), 60.0),
            (clip(26), 30.0),
            (clip(27), 10.0),
            (clip(27, "10:00:00;00"), 5.0),
            (clip(27), 5.0),
        ]
    )
    assert tcs[0] == "00:00:00;00"
    assert tcs[1] == "00:00:59;29"  # one real minute later (29.97 drop-frame keeps to the clock)
    assert tcs[2] == "00:01:30;00"  # the next day carries on (same event, same tape)
    assert tcs[3] == ""  # a clip with real timecode keeps its own
    assert tcs[4] == "00:01:44;29"  # and the counter ran on through it


def test_running_timecode_is_burned_and_stored(tmp_path: Path):
    a = _clip(tmp_path / "a.mp4", "320x240", "30000/1001", 1)
    s = Settings(video_preset="h264", burn_timecode=True)
    r = Conversion(str(a), probe(a), s, capabilities(), set(), timecode="00:01:00;02").run()
    assert r.status == "done", r.message
    assert "00:01:00;02" in r.command  # the file's own timecode track starts there too


def test_play_badge_only_starts_the_joined_video(tmp_path: Path, monkeypatch):
    import os
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    import listo.ui.panels.convert as sb
    import listo.ui.panels.export as ep
    import listo.ui.window.main_window as mw

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb, ep):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    badges, tcs = [], []
    real = mw.Conversion

    def spy(*a, **k):
        badges.append(a[2].burn_badge)
        tcs.append(k.get("timecode", ""))
        return real(*a, **k)

    monkeypatch.setattr(mw, "Conversion", spy)
    app = QApplication.instance() or QApplication([])
    src = tmp_path / "src"
    src.mkdir()
    clips = [_clip(src / f"{n}.mp4", "320x240", "30000/1001", 1) for n in "abc"]
    w = mw.MainWindow()
    s = w.settings
    s.video_preset, s.burn_timecode, s.burn_style, s.burn_badge, s.join = "h264", True, "vhs", "play", True
    w.add_paths([str(c) for c in clips])
    end = time.monotonic() + 60
    while not all(it.state == "ready" for it in w.items.values()) and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    w.start()
    end = time.monotonic() + 120
    while w.running and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    assert badges == ["play", "none", "none"]  # PLAY blinks once, at the start
    assert tcs[0] == "00:00:00;00" and tcs[1] and tcs[2] > tcs[1]  # one tape, the counter runs on
    w.close()
    app.processEvents()
