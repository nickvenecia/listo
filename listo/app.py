"""App entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QComboBox, QMenu, QWidget

from . import APP_NAME, __version__
from .core.log import get_logger, setup_logging
from .core.paths import data_dir
from .ui import theme

log = get_logger(__name__)


def _server_name() -> str:
    import getpass

    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return f"listo-{user}"


def _hand_off(paths: list[str]) -> bool:
    """If Listo is already open, send it these files and return True."""
    from PySide6.QtNetwork import QLocalSocket

    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if not sock.waitForConnected(1500):
        return False
    payload = b"\n".join(os.fsencode(p) for p in paths) + b"\n\x04"
    ok = sock.write(payload) == len(payload)
    sock.flush()
    while ok and sock.bytesToWrite() > 0:  # (returns False when everything is already sent)
        ok = sock.waitForBytesWritten(3000)
    sock.disconnectFromServer()
    return ok


_MAX_HANDOFF = 4 * 1024 * 1024


def _listen(window) -> object:
    """Accept files from 'Open With' / 'Send to' launches while we're running."""
    from PySide6.QtNetwork import QLocalServer

    name = _server_name()
    QLocalServer.removeServer(name)  # clear a stale socket from a crash
    server = QLocalServer(window)
    # Only this user's account may send files to the open window.
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(name):
        return None

    def on_conn() -> None:
        sock = server.nextPendingConnection()
        buf = bytearray()

        def read() -> None:
            buf.extend(bytes(sock.readAll()))
            if len(buf) > _MAX_HANDOFF:  # a list of file paths is never this big
                sock.abort()
                return
            if buf.endswith(b"\x04"):
                raw = bytes(buf[:-1]).split(b"\n")
                paths = [os.fsdecode(p) for p in raw if p]
                paths = [p for p in paths if Path(p).exists()]
                if paths:
                    window.add_paths(paths)
                if window.isMinimized():
                    window.showNormal()
                window.raise_()
                window.activateWindow()
                sock.disconnectFromServer()

        sock.readyRead.connect(read)
        sock.disconnected.connect(sock.deleteLater)

    server.newConnection.connect(on_conn)
    return server


class _RoundPopups(QObject):
    """Qt gives menus and dropdown lists square windows; make them see-through so the
    stylesheet's rounded corners are what you actually see."""

    @staticmethod
    def _see_through(win: QWidget) -> None:
        if not win.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground):
            win.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            win.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
            win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Polish and isinstance(obj, QWidget):
            if isinstance(obj, QMenu) and obj.isWindow():
                self._see_through(obj)
            elif isinstance(obj, QComboBox):
                container = obj.view().window()
                if container is not obj.window():
                    self._see_through(container)
                    container.setStyleSheet(
                        "QComboBoxPrivateContainer { background: transparent; border: none; }"
                    )
        return False


class ListoApp(QApplication):
    """Also receives files dropped on the Dock icon / opened with 'Open With' on macOS."""

    def __init__(self, argv: list[str]):
        super().__init__(argv)
        self.window = None
        self._pending: list[str] = []
        self._round = _RoundPopups(self)
        self.installEventFilter(self._round)

    def event(self, e):
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
        except Exception:
            log.debug("couldn't set the Windows app id", exc_info=True)
    setup_logging()
    log.info("Listo %s starting (%s)", __version__, sys.platform)
    app = ListoApp(sys.argv)
    smoke = "--smoke-test" in sys.argv
    launch_files = [
        str(Path(a).resolve()) for a in sys.argv[1:] if not a.startswith("-") and Path(a).exists()
    ]
    if not smoke and _hand_off(launch_files):
        return 0  # an open Listo window took the files
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
    app.setStyleSheet(theme.stylesheet(data_dir() / "ui"))

    from .ui.main_window import MainWindow

    w = MainWindow()
    app.window = w
    app.aboutToQuit.connect(w.shutdown)
    if not smoke:
        app._server = _listen(w)
    w.show()
    w.raise_()

    if smoke:  # used by the build pipeline: launch, check, quit
        from .core.tools import capabilities

        caps = capabilities()
        print("smoke:", caps.ffmpeg, caps.version, flush=True)
        QTimer.singleShot(1500, app.quit)
        code = app.exec()
        return code if caps.ok else 3

    pending = launch_files + app._pending
    if pending:
        QTimer.singleShot(0, lambda: w.add_paths(pending))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
