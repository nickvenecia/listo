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

from .helpers import HAS_FFMPEG, ff

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
    r = join.Join(parts, str(a), probe(a), s, capabilities(), set(), cues).run()
    assert r.status == "done", (r.message, r.log)
    assert not r.warning, r.warning
    assert r.output.name == f"a_joined.{'mov' if preset == 'prores' else 'mp4'}"
    got = probe(r.output)
    assert (got.width, got.height) == (640, 360)
    assert abs(got.duration - 6.0) < 0.3  # 2 + 2 + the trimmed 2
    assert got.audio  # the silent clip got a silent track, so sound runs the whole way
    assert not folder.exists()  # the parts are cleaned up
    srt = r.output.with_suffix(".srt").read_text()
    assert "First clip." in srt and "Third clip." in srt
    assert "00:00:04,5" in srt  # shifted past the first two clips (each ends on a whole frame)


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

    import listo.ui.export_panel as ep
    import listo.ui.main_window as mw
    import listo.ui.sidebar as sb

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
    assert outs == ["a_joined.mp4"], outs
    assert not any(p.name.startswith(".listo-join-") for p in src.iterdir())
    assert abs(probe(src / "a_joined.mp4").duration - 3.0) < 0.2
    assert all(it.result.output == src / "a_joined.mp4" for it in w.items.values())
    w.close()
    app.processEvents()
