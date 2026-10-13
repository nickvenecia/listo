"""Hundreds of clips: list-wide refreshes are bundled, not repeated for every file (that took minutes)."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

from .helpers import HAS_FFMPEG, ff


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_reading_many_files_bundles_the_refreshes(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    import listo.ui.panels.convert as sb
    import listo.ui.window.main_window as mw

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    app = QApplication.instance() or QApplication([])
    one = tmp_path / "one.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=160x120:d=1", "-f", "lavfi", "-i", "sine=d=1", "-shortest",
       "-c:v", "libx264", "-c:a", "aac", str(one))  # fmt: skip
    files = []
    for i in range(60):
        f = tmp_path / f"C{i:03d}.mov"
        shutil.copy(one, f)
        files.append(str(f))
    import listo.ui.window.jobs as wk
    from tests import speech_standin

    monkeypatch.setattr(wk.TranscribeThread, "target", staticmethod(speech_standin.serve))
    w = mw.MainWindow()
    w.settings.captions = True
    t0 = time.monotonic()
    w.add_paths(files)
    end = time.monotonic() + 120
    while not all(it.state == "ready" for it in w.items.values()) and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    assert all(it.state == "ready" for it in w.items.values())
    elapsed = time.monotonic() - t0
    end = time.monotonic() + 120  # let the captions finish too (they arrive one by one)
    while (
        w.tx is not None or any(it.transcript is None for it in w.items.values())
    ) and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    for _ in range(50):
        app.processEvents()
        time.sleep(0.01)

    calls = {"sync": 0}
    real_sync = w._sync_captions
    monkeypatch.setattr(
        w, "_sync_captions", lambda: (calls.__setitem__("sync", calls["sync"] + 1), real_sync())[1]
    )
    for _ in range(100):  # a burst of changes (files read, captions done, progress)...
        w._refresh_soon(captions=True)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert calls["sync"] == 1  # ...becomes one refresh
    assert w.btn_check.isVisibleTo(w)  # and the result is still right
    assert elapsed < 60, elapsed
    w.close()
    app.processEvents()
