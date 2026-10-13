"""The players: a real-time clock, and previous / next clip arrows."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

from listo.ui.dialogs.trim import fmt_clock

from .helpers import HAS_FFMPEG, ff


def test_clock_reads_like_time():
    assert fmt_clock(18.5) == "00:18"
    assert fmt_clock(449.9) == "07:29"
    assert fmt_clock(3723) == "1:02:03"
    assert fmt_clock(5, longest=3723) == "0:00:05"  # same shape as the length beside it


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_arrows_step_through_the_clips(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    import listo.ui.dialogs.preview as pd
    import listo.ui.panels.convert as sb
    import listo.ui.window.main_window as mw

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    app = QApplication.instance() or QApplication([])
    one = tmp_path / "a.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=160x120:d=1", "-c:v", "libx264", str(one))
    for n in ("b", "c"):
        shutil.copy(one, tmp_path / f"{n}.mov")
    w = mw.MainWindow()
    w.add_paths([str(tmp_path / f"{n}.mov") for n in "abc"])
    end = time.monotonic() + 60
    while not all(it.state == "ready" for it in w.items.values()) and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    w._live_timer.stop()
    w._render_live()
    p = w.export_panel.player
    assert p.btn_next.isEnabled() and not p.btn_prev.isEnabled()  # on the first clip
    assert Path(w._live_clip().path).name == "a.mov"
    p.step.emit(1)  # the → arrow: the next clip, selected in the list too
    assert Path(w._live_clip().path).name == "b.mov" and len(w.selected) == 1
    p.step.emit(1)
    assert Path(w._live_clip().path).name == "c.mov"
    assert p.btn_prev.isEnabled() and not p.btn_next.isEnabled()

    clips = [(Path(it.path).name, it.path, it.info, w.eff(it), None) for it in w.items.values()]
    d = pd.PreviewDialog(clips, 0)
    assert not d.player.btn_prev.isEnabled() and d.player.btn_next.isEnabled()
    d.player.step.emit(1)
    assert d.pick.currentIndex() == 1 and d.player.path.endswith("b.mov")
    d.player.step.emit(-1)
    assert d.pick.currentIndex() == 0
    d.reject()
    w.close()
    app.processEvents()


def test_heavy_settings_start_off_each_launch(tmp_path: Path, monkeypatch):
    """Everything is remembered except captions and joining (heavy / surprising when forgotten)."""
    import json

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    import listo.ui.panels.convert as sb
    import listo.ui.window.main_window as mw
    from listo.core.presets import Settings

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    app = QApplication.instance() or QApplication([])
    last = Settings(video_preset="h264", captions=True, join=True, caption_model="best", burn_timecode=True)
    QSettings(ini, QSettings.Format.IniFormat).setValue("settings", json.dumps(last.to_dict()))
    w = mw.MainWindow()
    s = w.settings
    assert not s.captions and not s.join  # off on a fresh start
    assert s.video_preset == "h264" and s.caption_model == "best" and s.burn_timecode  # the rest remembered
    w.close()
    app.processEvents()


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_space_plays_and_pauses_even_with_a_dropdown_focused(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QShortcut
    from PySide6.QtWidgets import QApplication

    import listo.ui.dialogs.preview as pd
    from listo.core.presets import Settings
    from listo.core.probe import probe

    app = QApplication.instance() or QApplication([])
    a = tmp_path / "a.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=160x120:d=2", "-c:v", "libx264", str(a))
    d = pd.PreviewDialog([("a.mov", str(a), probe(a), Settings(), None)], 0)
    shortcuts = [sc for sc in d.findChildren(QShortcut) if sc.key().toString() == "Space"]
    assert len(shortcuts) == 1 and shortcuts[0].context() == Qt.ShortcutContext.WindowShortcut
    toggled = []
    d.player.toggle = lambda: toggled.append(True)  # (the real one needs Qt's player)
    shortcuts[0].activated.disconnect()
    shortcuts[0].activated.connect(d.player.toggle)
    shortcuts[0].activated.emit()
    assert toggled
    d.reject()
    app.processEvents()
