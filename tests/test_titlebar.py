"""Listo's own Mac title bar: it sits at the very top (no empty strip above it) and dragging it moves the window."""

from __future__ import annotations

import os
from pathlib import Path


def test_title_bar_is_on_top_and_drags_the_window(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    import listo.ui.main_window as mw
    import listo.ui.sidebar as sb
    from listo.ui import titlebar

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
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
