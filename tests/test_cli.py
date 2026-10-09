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


def test_main_window_builds_and_settings_round_trip(tmp_path: Path, monkeypatch):
    """Builds the whole window offscreen; catches UI wiring mistakes no other test reaches."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    import listo.ui.export_dialog
    import listo.ui.main_window
    import listo.ui.sidebar

    # Never touch the real Listo preferences on this computer.
    ini = str(tmp_path / "listo-test.ini")
    for mod in (listo.ui.main_window, listo.ui.sidebar, listo.ui.export_dialog):
        if hasattr(mod, "QSettings"):
            monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))

    from listo.ui.main_window import MainWindow

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
    sb.v_adv.set_open(True)
    assert sb.matte_row.isVisibleTo(sb)
    from listo.core.presets import Settings

    n = sum(1 for k in sb.VIDEO_ADVANCED if getattr(s, k) != getattr(Settings(), k))
    assert n >= 2 and f"{n} changed" in sb.v_adv.header.text()  # changed settings are never hidden silently
    w._fill_trash_menu()
    assert [a.text() for a in w.trash_menu.actions() if a.text()] == [
        "Remove selected",
        "Clear finished",
        "Clear all",
    ]
    w.close()
    app.processEvents()
