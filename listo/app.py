"""App entry point."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from . import APP_NAME, __version__
from .ui import theme


class ListoApp(QApplication):
    """Also receives files dropped on the Dock icon / opened with 'Open With' on macOS."""

    def __init__(self, argv: list[str]):
        super().__init__(argv)
        self.window = None
        self._pending: list[str] = []

    def event(self, e):  # noqa: D401
        if e.type() == QEvent.Type.FileOpen:
            path = e.file()
            if self.window is not None:
                self.window.add_paths([path])
            else:
                self._pending.append(path)
            return True
        return super().event(e)


def main() -> int:
    if sys.platform == "win32":
        try:  # own taskbar icon instead of python's
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Listo.Listo")
        except Exception:  # noqa: BLE001
            pass
    app = ListoApp(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("Listo")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    icon_path = theme.ASSETS / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    family = theme.load_fonts()
    f = QFont(family or app.font().family())
    f.setPointSizeF(13 if sys.platform == "darwin" else 10)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(f)
    app.setStyleSheet(theme.stylesheet(Path(tempfile.gettempdir()) / f"listo-ui-{os.getpid()}"))

    from .ui.main_window import MainWindow

    w = MainWindow()
    app.window = w
    app.aboutToQuit.connect(w.shutdown)
    w.show()
    w.raise_()

    if "--smoke-test" in sys.argv:  # used by the build pipeline: launch, check, quit
        from .tools import capabilities

        caps = capabilities()
        print("smoke:", caps.ffmpeg, caps.version, flush=True)
        QTimer.singleShot(1500, app.quit)
        code = app.exec()
        return code if caps.ok else 3

    args = [a for a in sys.argv[1:] if not a.startswith("-") and Path(a).exists()]
    pending = args + app._pending
    if pending:
        QTimer.singleShot(0, lambda: w.add_paths(pending))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
