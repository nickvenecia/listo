"""Render the app offscreen and save screenshots (dev helper).

QT_QPA_PLATFORM=offscreen python tests/screenshot.py OUTDIR [SAMPLES_DIR]
LISTO_LOOK=light (or dark) picks the look; otherwise it follows the system like the app.
Runs on a throwaway data folder and settings file, never the real ones.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from listo import app as appmod

out = Path(sys.argv[1] if len(sys.argv) > 1 else "shots")
out.mkdir(parents=True, exist_ok=True)
samples = Path(sys.argv[2]) if len(sys.argv) > 2 else None


def main() -> None:
    import tempfile

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from listo.core.paths import use_data_dir

    scratch = Path(tempfile.mkdtemp(prefix="listo-shots-"))  # never the real settings or recipes
    use_data_dir(scratch)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(scratch))
    app = QApplication(sys.argv[:1])
    appmod.setup_app(app)
    from listo.ui.window.main_window import MainWindow

    w = MainWindow()
    app.aboutToQuit.connect(w.shutdown)
    w.resize(1120, 720)
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

        def override_one():
            for it in w.items.values():
                if it.path.endswith("IMG_0001.MOV"):
                    w._set_override(it.id, {"video_preset": "h264"})

        steps.append((2500, override_one))
        steps.append((300, shot("02-queue")))

        def save_shot():
            d = w.export_panel
            d.styles.setCurrentIndex(d.styles.findData("custom"))
            d.show()
            QTimer.singleShot(
                400, lambda: (d.grab().save(str(out / "03-export-panel.png")), print("saved 03"))
            )

        steps.append((100, save_shot))
        steps.append((800, lambda: None))

        def recipe():
            w.settings.apply(
                {
                    "video_preset": "h264",
                    "video_resize": "1080",
                    "burn_timecode": True,
                    "burn_filename": True,
                    "destination": "subfolder",
                    "subfolder_name": "Review",
                    "naming": "{name}_review",
                }
            )
            w.sidebar.reload()
            w.export_panel.reload()
            w.sidebar._store_recipe("Client review")
            w._settings_changed()

        steps.append((100, recipe))
        steps.append((400, shot("04-recipe")))
        steps.append((100, lambda: (setattr(w.settings, "parallel", True), w.start())))
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
