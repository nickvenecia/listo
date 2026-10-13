"""App entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractScrollArea,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QLabel,
    QMenu,
    QScrollBar,
    QWidget,
)

from listo import APP_NAME, __version__
from listo.core import store
from listo.core.log import get_logger, setup_logging
from listo.core.paths import ASSETS, data_dir, log_dir
from listo.ui.components.widgets import ComboItemDelegate, keep_words_whole
from listo.ui.style import theme, tokens

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


def place_menu(menu: QWidget, button: QWidget) -> None:
    """A button's menu opens just below it, with a little air between: lined up with its left edge, or, for a
    button on the right of the window, with its right edge (so it never runs off past the window)."""
    size = menu.size()
    top_left = button.mapToGlobal(QPoint(0, 0))
    win = button.window()
    on_right = button.mapTo(win, button.rect().center()).x() > win.width() / 2
    x = top_left.x() + button.width() - size.width() if on_right else top_left.x()
    y = top_left.y() + button.height() + tokens.MENU_GAP
    screen = button.screen().availableGeometry() if button.screen() else None
    if screen is not None:
        if y + size.height() > screen.bottom():  # no room below: above it instead
            y = top_left.y() - size.height() - tokens.MENU_GAP
        x = max(screen.left(), min(x, screen.right() - size.width()))
    menu.move(x, y)


class _RoundPopups(QObject):
    """Qt gives menus and dropdown lists square windows; make them see-through so the
    stylesheet's rounded corners are what you actually see. A button's menu opens just below it, with a
    little air (place_menu); so does a dropdown's list. Also: scrolling never changes a value
    (dropdowns and sliders pass the wheel on to the panel, which scrolls instead), text in a
    label is shown as typed (a file called "<b>clip.mov" keeps that name), and a dialog can't be made
    shorter than its words need (widgets.keep_words_whole)."""

    @staticmethod
    def _see_through(win: QWidget) -> None:
        if not win.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground):
            win.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            win.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
            win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def eventFilter(self, obj, ev):
        wheel_on_control = isinstance(obj, (QComboBox, QAbstractSlider, QAbstractSpinBox)) and not isinstance(
            obj, QScrollBar
        )
        if ev.type() == QEvent.Type.Wheel and wheel_on_control:
            area = obj.parent()
            while area is not None and not isinstance(area, QAbstractScrollArea):
                area = area.parent()
            if area is not None:
                QApplication.sendEvent(area.verticalScrollBar(), ev)
            return True
        if ev.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
            owner = obj.parentWidget()
            if isinstance(obj, QDialog):
                keep_words_whole(obj)
            elif (
                isinstance(obj, QMenu)
                and isinstance(owner, QAbstractButton)
                and getattr(owner, "menu", lambda: None)() is obj
            ):
                place_menu(obj, owner)
            elif obj.inherits("QComboBoxPrivateContainer") and isinstance(owner, QComboBox):
                below = owner.mapToGlobal(QPoint(0, owner.height()))
                if obj.y() >= below.y() - 1:  # opened below the box: leave the same air
                    obj.move(obj.x(), below.y() + tokens.MENU_GAP)
        if ev.type() == QEvent.Type.Polish and isinstance(obj, QWidget):
            if (
                isinstance(obj, QLabel)
                and obj.textFormat() == Qt.TextFormat.AutoText
                and not obj.inherits("QTipLabel")
                and not obj.objectName().startswith("qt_")
            ):  # names are shown as typed; a label meant to be formatted says RichText itself
                obj.setTextFormat(Qt.TextFormat.PlainText)
            if (isinstance(obj, QMenu) and obj.isWindow()) or obj.inherits("QTipLabel"):
                self._see_through(obj)
            elif isinstance(obj, QComboBox):
                if not isinstance(obj.itemDelegate(), ComboItemDelegate):
                    obj.setItemDelegate(ComboItemDelegate(obj))
                container = obj.view().window()
                if container is not obj.window():
                    self._see_through(container)  # its look is in theme.py (QComboBoxPrivateContainer)
        return False


def setup_app(app: QApplication) -> None:
    """Fonts, stylesheet and look (also used by the tests and screenshots)."""
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("Listo")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    icon_path = ASSETS / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    family = theme.load_fonts()
    f = QFont(family or app.font().family())
    f.setPixelSize(tokens.TEXT_MD)  # every size is in pixels (the stylesheet's too), so they match
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(f)
    from listo.ui.old_settings import bring_over

    try:
        bring_over()  # settings kept by older versions, copied into settings.json once
    except OSError:
        log.warning("couldn't copy the old settings into settings.json", exc_info=True)
    saved = store.prefs()
    appearance, accent = saved.get("appearance", "system"), saved.get("accent", "")
    set_appearance(
        app,
        appearance if isinstance(appearance, str) else "system",
        accent if isinstance(accent, str) else "",
    )
    if getattr(app, "_round", None) is not None:
        return  # set up once already (tests, screenshots): only the look was read again
    hints = app.styleHints()
    if hasattr(hints, "colorSchemeChanged"):
        hints.colorSchemeChanged.connect(lambda _s: _system_changed(app))
    app._round = _RoundPopups(app)
    app.installEventFilter(app._round)


def set_appearance(app: QApplication, appearance: str, accent: str | None = None) -> str:
    """Light, dark, or "system" (follow the computer), and the accent ("" = Listo's own; None keeps it).
    Redraws open windows."""
    app._appearance = appearance
    app._applying = True  # asking the system can itself report a change
    try:
        look = theme.apply(app, appearance, data_dir() / "ui", accent)
    finally:
        app._applying = False
    log.info("look: %s (%s), accent %s", look, appearance, tokens.ACCENT_KEY)
    for w in app.topLevelWidgets():
        if hasattr(w, "look_changed"):
            w.look_changed()
    return look


def _system_changed(app: QApplication) -> None:
    """The computer switched between light and dark (Auto appearance on a Mac): follow it, unless
    Settings picked one look."""
    if getattr(app, "_appearance", "system") == "system" and not getattr(app, "_applying", False):
        set_appearance(app, "system")


class ListoApp(QApplication):
    """Also receives files dropped on the Dock icon / opened with 'Open With' on macOS."""

    def __init__(self, argv: list[str]):
        super().__init__(argv)
        self.window = None
        self._pending: list[str] = []

    def event(self, e):
        if e.type() == QEvent.Type.FileOpen:
            path = e.file()
            if self.window is not None:
                self.window.add_paths([path])
            else:
                self._pending.append(path)
            return True
        return super().event(e)


_crash_file = None


def _log_uncaught() -> None:
    """Any unexpected Python error (also in background threads) goes to the log with its details,
    so the debug console shows it, instead of only printing where nobody looks."""
    import threading

    previous = sys.excepthook

    def hook(kind, value, tb):
        log.error("unexpected error", exc_info=(kind, value, tb))
        if previous is not None:
            previous(kind, value, tb)

    sys.excepthook = hook
    threading.excepthook = lambda a: log.error(
        "unexpected error in %s", a.thread.name if a.thread else "a thread",
        exc_info=(a.exc_type, a.exc_value, a.exc_traceback),
    )  # fmt: skip


def _crash_log() -> None:
    """If Listo ever crashes hard (a crash inside Qt or ffmpeg libraries, not a Python error), write
    where it was to crash.log next to listo.log, so it can be found and fixed."""
    global _crash_file
    import faulthandler

    try:
        log_dir().mkdir(parents=True, exist_ok=True)
        _crash_file = open(log_dir() / "crash.log", "a", encoding="utf-8")  # noqa: SIM115 — open for the app's life
        faulthandler.enable(_crash_file, all_threads=True)
    except OSError:
        log.debug("no crash log", exc_info=True)


def main() -> int:
    if sys.platform == "win32":
        try:  # own taskbar icon instead of python's
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Listo.Listo")
        except Exception:
            log.debug("couldn't set the Windows app id", exc_info=True)
    setup_logging()
    log.info("Listo %s starting (%s)", __version__, sys.platform)
    _crash_log()
    _log_uncaught()
    # Playback inside Listo decodes on the processor: Qt's player crashed on MPEG-2 camcorder clips when
    # the Mac's hardware decoder refused them ("," = no hardware decoders; see ui/player.py).
    os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", ",")
    app = ListoApp(sys.argv)
    smoke = "--smoke-test" in sys.argv
    launch_files = [
        str(Path(a).resolve()) for a in sys.argv[1:] if not a.startswith("-") and Path(a).exists()
    ]
    if not smoke and _hand_off(launch_files):
        return 0  # an open Listo window took the files
    if smoke:  # a throwaway data folder: the check never touches real settings
        import tempfile

        from listo.core.paths import use_data_dir

        use_data_dir(Path(tempfile.mkdtemp(prefix="listo-smoke-")))
    setup_app(app)  # light or dark like the computer (or as Settings says), in the saved accent

    from listo.ui.window.main_window import MainWindow

    w = MainWindow()
    app.window = w
    app.aboutToQuit.connect(w.shutdown)
    if not smoke:
        app._server = _listen(w)
    w.show()
    w.raise_()

    if smoke:  # used by the build pipeline: launch, check, quit
        from listo.core.tools import capabilities

        caps = capabilities()
        print("smoke:", caps.ffmpeg, caps.version, flush=True)
        from listo.core.captions_worker import ping
        from listo.ui.dialogs.captions import HAS_PLAYER

        status = ping()  # captions run in their own process: make sure the packaged app can start it
        print(f"captions process: {status or 'DID NOT START'}", flush=True)
        print(f"player: {'ready' if HAS_PLAYER else 'NOT available'}", flush=True)
        QTimer.singleShot(1500, app.quit)
        code = app.exec()
        if not caps.ok:
            return 3
        return code if status else 4

    pending = launch_files + app._pending
    if pending:
        QTimer.singleShot(0, lambda: w.add_paths(pending))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
