"""Render the app offscreen and save screenshots (dev helper).

    QT_QPA_PLATFORM=offscreen python tests/screenshot.py OUTDIR [SAMPLES_DIR]
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from listo import app as appmod  # noqa: E402
from listo.ui import theme  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "shots")
out.mkdir(parents=True, exist_ok=True)
samples = Path(sys.argv[2]) if len(sys.argv) > 2 else None


def main() -> None:
    app = appmod.ListoApp(sys.argv[:1])
    app.setStyle("Fusion")
    fam = theme.load_fonts()
    from PySide6.QtGui import QFont

    f = QFont(fam)
    f.setPointSizeF(10)
    app.setFont(f)
    app.setStyleSheet(theme.stylesheet(Path(tempfile.gettempdir()) / "listo-shot"))
    from listo.ui.main_window import MainWindow

    w = MainWindow()
    app.aboutToQuit.connect(w.shutdown)
    w.qs.clear()
    w.resize(1240, 800)
    w.show()
    steps = []

    def shot(name: str):
        def go():
            w.grab().save(str(out / f"{name}.png"))
            print("saved", name)
        return go

    steps.append((400, shot("01-empty")))
    if samples:
        files = sorted(str(p) for p in samples.iterdir() if p.is_file())
        steps.append((100, lambda: w.add_paths(files)))
        steps.append((2500, shot("02-queue")))
        steps.append((100, lambda: (w.sidebar.show_tab("save"))))
        steps.append((300, shot("03-save-tab")))
        steps.append((100, lambda: (w.sidebar.show_tab("photo"))))
        steps.append((300, shot("04-photo-tab")))
        steps.append((100, lambda: (w.sidebar.show_tab("video"), w.start())))
        steps.append((1500, shot("05-converting")))
        steps.append((100, lambda: wait_done()))
    def wait_done():
        if w.running:
            QTimer.singleShot(500, wait_done)
            return
        shot("06-finished")()
        app.quit()

    if not samples:
        steps.append((100, app.quit))

    t = 0
    for delay, fn in steps:
        t += delay
        QTimer.singleShot(t, fn)
    app.exec()


main()
