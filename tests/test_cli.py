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

    from listo.ui.window import jobs as workers

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.png"
        Image.new("RGB", (300, 200), (10, 20, 30)).save(p)
        data = workers.photo_thumb(str(p))
    assert data and Image.open(io.BytesIO(data)).size[0] > 0


def test_main_window_builds_and_settings_round_trip(tmp_path: Path, monkeypatch):
    """Builds the whole window offscreen; catches UI wiring mistakes no other test reaches."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    import listo.ui.panels.convert
    import listo.ui.panels.export
    import listo.ui.window.main_window

    # Never touch the real Listo preferences on this computer.
    ini = str(tmp_path / "listo-test.ini")
    for mod in (listo.ui.window.main_window, listo.ui.panels.convert, listo.ui.panels.export):
        if hasattr(mod, "QSettings"):
            monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))

    from listo.ui.window.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    sb = w.sidebar
    sb.v_aspect.setCurrentIndex(sb.v_aspect.findData("2.35:1"))
    sb.v_fit.setCurrentIndex(sb.v_fit.findData("matte"))
    sb.matte_q.setValue(60)
    sb.burn_dt.setChecked(True)
    sb.burn_style.setCurrentIndex(sb.burn_style.findData("vhs"))
    s = w.settings
    assert (s.aspect, s.aspect_fit, s.matte_opacity, s.burn_datetime, s.burn_style) == (
        "2.35:1",
        "matte",
        60,
        True,
        "vhs",
    )
    sb.g_picture.set_open(True)
    assert sb.matte_row.isVisibleTo(sb)
    from listo.core.presets import Settings
    from listo.ui.panels.convert import GROUPS

    for group, key in ((sb.g_picture, "picture"), (sb.g_text, "text")):
        n = sum(1 for k in GROUPS[key] if getattr(s, k) != getattr(Settings(), k))
        assert n >= 1 and f"{n} changed" in group.header.text()  # changed settings never hide silently
    sb.g_text.set_open(True)
    sb.cc_on.setChecked(True)
    assert s.captions and sb.cc_box.isVisibleTo(sb)
    assert sb.burn_badge.isVisibleTo(sb)  # VHS style + a burn-in on
    assert sb.sec_tape.isVisibleTo(sb)  # the VHS Tape section comes with the VHS look
    for box in (sb.burn_badge, sb.burn_end, sb.tape_screen, sb.tape_glitches):
        assert box.isVisibleTo(sb)  # four dropdowns, nothing hidden behind switches
    sb.burn_end.setCurrentIndex(sb.burn_end.findData("stop"))
    assert s.burn_stop
    sb.tape_screen.setCurrentIndex(sb.tape_screen.findData("bars"))
    sb._screen_picked(sb.tape_screen.currentIndex())
    assert s.tape_blue and s.tape_screen == "bars"
    sb.tape_screen.setCurrentIndex(sb.tape_screen.findData("none"))
    sb._screen_picked(sb.tape_screen.currentIndex())
    assert not s.tape_blue
    sb.tape_glitches.setCurrentIndex(sb.tape_glitches.findData("cuts"))
    assert s.tape_glitches == "cuts"
    sb.burn_style.setCurrentIndex(sb.burn_style.findData("clean"))
    assert not sb.sec_tape.isVisibleTo(sb)  # VHS only
    sb.burn_style.setCurrentIndex(sb.burn_style.findData("vhs"))
    w._fill_trash_menu()
    assert [a.text() for a in w.trash_menu.actions() if a.text()] == [
        "Remove Selected",
        "Clear Finished",
        "Clear All",
    ]
    w.close()
    app.processEvents()


def test_scrolling_over_a_dropdown_never_changes_it():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QComboBox, QScrollArea, QVBoxLayout, QWidget

    from listo.app import _RoundPopups

    app = QApplication.instance() or QApplication([])
    guard = _RoundPopups(app)
    app.installEventFilter(guard)
    area = QScrollArea()
    inner = QWidget()
    inner.setMinimumHeight(2000)
    lay = QVBoxLayout(inner)
    c = QComboBox()
    c.addItems(["a", "b", "c"])
    lay.addWidget(c)
    area.setWidget(inner)
    area.resize(200, 200)
    area.show()
    ev = QWheelEvent(
        QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False,
    )  # fmt: skip
    QApplication.sendEvent(c, ev)
    assert c.currentIndex() == 0
    assert area.verticalScrollBar().value() > 0
    app.removeEventFilter(guard)


def test_camera_sidecar_files_are_not_listed(tmp_path: Path, monkeypatch):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    import listo.ui.panels.convert
    import listo.ui.window.main_window

    ini = str(tmp_path / "listo-test.ini")
    for mod in (listo.ui.window.main_window, listo.ui.panels.convert):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    from listo.ui.window.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    folder = tmp_path / "SD_VIDEO"
    folder.mkdir()
    for name in ("MOV01A.MOD", "MOV01A.MOI", "MOV01A.THM", "notes.txt"):
        (folder / name).write_bytes(b"x")
    w = MainWindow()
    w.add_paths([str(folder)])
    names = sorted(Path(it.path).name for it in w.items.values())
    assert names == ["MOV01A.MOD"]
    assert "skipped 1 file that isn't" in w.toast.text().lower()  # only notes.txt counts as skipped
    w.add_paths([str(folder / "MOV01A.MOI")])  # dropped on its own: still not listed
    assert len(w.items) == 1
    second = tmp_path / "PRG002"
    second.mkdir()
    (second / "MOV01A.MOD").write_bytes(b"x")
    w.add_paths([str(second / "MOV01A.MOD")])
    assert sorted(it.card.name.text() for it in w.items.values()) == [
        "PRG002 / MOV01A.MOD",
        "SD_VIDEO / MOV01A.MOD",
    ]
    w.close()
    app.processEvents()


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_preview_window_opens_for_clips_and_for_an_empty_list(tmp_path: Path, monkeypatch):
    import os
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    import listo.ui.dialogs.preview as pd
    import listo.ui.panels.convert as sb
    import listo.ui.window.main_window as mw
    from listo.core import sample

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    monkeypatch.setattr(sample, "data_dir", lambda: tmp_path / "data")
    shown = []
    monkeypatch.setattr(pd.PreviewDialog, "exec", lambda self: shown.append([c[0] for c in self.clips]) or 0)
    app = QApplication.instance() or QApplication([])
    w = mw.MainWindow()
    w.settings.captions = True  # sample captions in the preview
    w.open_preview()  # empty list: the sample picture
    clip = tmp_path / "a.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip))
    w.add_paths([str(clip)])
    end = time.monotonic() + 30
    while not all(it.state == "ready" for it in w.items.values()) and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    w.open_preview()
    assert shown == [["Sample picture"], ["a.mov"]]
    w.close()
    app.processEvents()
