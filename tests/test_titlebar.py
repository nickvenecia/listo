"""Listo's own Mac title bar: it sits at the very top (no empty strip above it) and dragging it moves the window."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


# The test pretends to be a Mac on the screenless "offscreen" display. On a real Mac machine that
# display reports a 20 px safe area of its own (a real Mac window doesn't), so the check is skipped
# there; it runs on Linux / Windows, and the real thing was checked by hand on a Mac.
@pytest.mark.skipif(sys.platform == "darwin", reason="the offscreen display on macOS fakes a safe area")
def test_title_bar_is_on_top_and_drags_the_window(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    import listo.ui.window.main_window as mw
    from listo.ui.components import titlebar

    monkeypatch.setattr(titlebar, "supported", lambda: True)  # as on a Mac
    app = QApplication.instance() or QApplication([])
    w = mw.MainWindow()
    w.resize(1200, 700)
    w.move(100, 100)
    w.show()
    app.processEvents()
    bar = w.titlebar
    assert bar is not None and bar.mapTo(w, QPoint(0, 0)).y() == 0

    def ev(kind, g, buttons):
        return QMouseEvent(
            kind, QPointF(bar.mapFromGlobal(g)), QPointF(g), Qt.MouseButton.LeftButton, buttons,
            Qt.KeyboardModifier.NoModifier,
        )  # fmt: skip

    start, g0 = w.pos(), bar.mapToGlobal(QPoint(300, 10))
    bar.mousePressEvent(ev(QEvent.Type.MouseButtonPress, g0, Qt.MouseButton.LeftButton))
    bar.mouseMoveEvent(ev(QEvent.Type.MouseMove, g0 + QPoint(150, 80), Qt.MouseButton.LeftButton))
    bar.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, g0 + QPoint(150, 80), Qt.MouseButton.NoButton))
    app.processEvents()
    assert w.pos() - start == QPoint(150, 80)
    w.close()
    app.processEvents()
