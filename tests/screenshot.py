"""Render the app offscreen and save screenshots (dev helper).

QT_QPA_PLATFORM=offscreen python tests/screenshot.py OUTDIR [SAMPLES_DIR]
LISTO_LOOK=light (or dark) picks the look; otherwise it follows the system like the app.
LISTO_ACCENT=blue (any of tokens.ACCENTS) shows another accent.
Runs on a throwaway data folder and settings file, never the real ones. The window is the standard's
normal size (tokens.WINDOW_SIZE).
"""

from __future__ import annotations

import os
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

    from listo.core import store
    from listo.core.paths import use_data_dir
    from listo.ui.style import tokens

    scratch = Path(tempfile.mkdtemp(prefix="listo-shots-"))  # never the real settings or recipes
    use_data_dir(scratch)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(scratch))
    if os.environ.get("LISTO_ACCENT"):
        store.save_pref("accent", os.environ["LISTO_ACCENT"])
    app = QApplication(sys.argv[:1])
    appmod.setup_app(app)
    from listo.ui.window.main_window import MainWindow

    w = MainWindow()
    w._restored = True
    app.aboutToQuit.connect(w.shutdown)
    w.resize(*tokens.WINDOW_SIZE)
    w.show()
    steps = []

    def shot(name: str, what=None):
        def go():
            (what() if what else w).grab().save(str(out / f"{name}.png"))
            print("saved", name)

        return go

    steps.append((600, shot("01-empty")))

    def settings(pane: str, name: str):
        def go():
            from listo.ui.dialogs.settings import SettingsDialog

            d = SettingsDialog(w, pane)
            d.show()
            QTimer.singleShot(
                300, lambda: (d.grab().save(str(out / f"{name}.png")), print("saved", name), d.close())
            )

        return go

    steps.append((100, settings("general", "07-settings-general")))
    steps.append((600, settings("data", "08-settings-data")))
    steps.append((600, lambda: None))
    if samples:
        files = sorted(str(p) for p in samples.iterdir() if p.is_file())
        steps.append((100, lambda: w.add_paths(files)))

        def override_one():
            for it in w.items.values():
                if it.path.endswith("IMG_0001.MOV"):
                    w._set_override(it.id, {"video_preset": "h264"})
                    w._select({it.id})

        steps.append((3000, override_one))
        steps.append((600, shot("02-list")))

        def groups_open():
            w.convert.open_groups(True)
            w.export_panel.styles.setCurrentIndex(w.export_panel.styles.findData("custom"))

        steps.append((100, groups_open))
        steps.append((500, shot("03-panel", lambda: w.panel)))

        def recipe():
            w.convert.open_groups(False)
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
            w.convert.reload()
            w.export_panel.reload()
            w.convert._store_recipe("Client review")
            w._settings_changed()

        steps.append((100, recipe))
        steps.append((500, shot("04-recipe")))
        steps.append((100, lambda: (setattr(w.settings, "parallel", True), w.start())))
        steps.append((1500, shot("05-converting")))
        steps.append((100, lambda: wait_done()))

    def wait_done():
        if w.running:
            QTimer.singleShot(500, wait_done)
            return
        shot("06-finished")()
        w.go("attention")
        QTimer.singleShot(300, lambda: (shot("06b-need-a-look")(), app.quit()))

    if not samples:
        steps.append((100, app.quit))

    t = 0
    for delay, fn in steps:
        t += delay
        QTimer.singleShot(t, fn)
    app.exec()


main()
