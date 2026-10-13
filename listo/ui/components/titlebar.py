"""The Mac title bar, drawn by Listo: the app's background (light or dark) with the "listo." wordmark centred.

Qt (6.9+) lets the window's content run up under the title bar (ExpandedClientAreaHint) with no
bar background (NoTitleBarBackgroundHint); the traffic-light buttons stay where they are, on top of
our bar. Qt would normally push the content below that area (the "safe area"), which left an empty,
undraggable strip above our bar: the window turns that off, so our bar IS the title bar. The Mac's
own title text is hidden with one call into AppKit (ctypes, no extra packages). Dragging the bar hands
the move to macOS (so Exposé, Spaces and snapping behave like any other app); double-clicking switches
between filling the screen and the smallest size.

Windows and Linux keep their system title bar, which follows the system's light / dark setting.
If any piece is missing (older Qt, the AppKit call fails), the normal title bar stays.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QWidget

from listo.ui.components.widgets import hbox
from listo.ui.style import theme
from listo.ui.style.tokens import TITLEBAR_H


def supported() -> bool:
    return sys.platform == "darwin" and hasattr(Qt.WindowType, "ExpandedClientAreaHint")


def install(window: QMainWindow) -> TitleBar | None:
    """Turn on Listo's own title bar for this window (Mac only). Returns the bar to put on top."""
    if not supported():
        return None
    window.setWindowFlag(Qt.WindowType.ExpandedClientAreaHint, True)
    if hasattr(Qt.WindowType, "NoTitleBarBackgroundHint"):
        window.setWindowFlag(Qt.WindowType.NoTitleBarBackgroundHint, True)
    ignore_safe_area(window)
    return TitleBar(window)


def ignore_safe_area(w: QWidget) -> None:
    """Lay out from the very top (our bar goes where the system bar was, not below an empty strip)."""
    if hasattr(Qt.WidgetAttribute, "WA_ContentsMarginsRespectsSafeArea"):
        w.setAttribute(Qt.WidgetAttribute.WA_ContentsMarginsRespectsSafeArea, False)


class TitleBar(QWidget):
    def __init__(self, window: QMainWindow):
        super().__init__()
        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._window = window
        self._drag: QPoint | None = None  # where in the window the drag grabbed it (if macOS can't move it)
        self._press = QPoint()
        self._was_at = QPoint()
        self.setFixedHeight(TITLEBAR_H)
        ignore_safe_area(self)
        lay = hbox(self, 0, 0)
        self.word = word = QLabel(theme.wordmark())
        word.setObjectName("TitleWordmark")
        word.setTextFormat(Qt.TextFormat.RichText)
        word.setAlignment(Qt.AlignmentFlag.AlignCenter)
        word.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(word, 1)

    def fit(self) -> None:
        """Match the real title bar height (it differs between macOS versions)."""
        handle = self._window.windowHandle()
        if handle is not None and hasattr(handle, "safeAreaMargins"):
            top = handle.safeAreaMargins().top()
            if 0 < top <= 2 * TITLEBAR_H:  # the real bar's height (a sane one)
                self.setFixedHeight(top)
        hide_mac_title(self._window)

    def mousePressEvent(self, e):
        e.accept()
        if e.button() != Qt.MouseButton.LeftButton or self._window.isFullScreen():
            return
        self._drag = e.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
        self._press = e.globalPosition().toPoint()
        self._was_at = self._window.pos()

    def mouseMoveEvent(self, e):
        e.accept()
        if self._drag is None or not e.buttons() & Qt.MouseButton.LeftButton:
            return
        if self._window.pos() != self._was_at:  # something else moved it (Exposé): not a drag
            self._drag = None
            return
        from PySide6.QtWidgets import QApplication

        if (e.globalPosition().toPoint() - self._press).manhattanLength() < QApplication.startDragDistance():
            return  # still a click, not a drag
        handle = self._window.windowHandle()
        if handle is not None and handle.startSystemMove():
            self._drag = None  # macOS moves it from here
            return
        self._window.move(e.globalPosition().toPoint() - self._drag)
        self._was_at = self._window.pos()

    def mouseReleaseEvent(self, e):
        self._drag = None
        e.accept()

    def mouseDoubleClickEvent(self, e):
        self._drag = None
        toggle_size(self._window)
        e.accept()


def toggle_size(window: QWidget) -> None:
    """Fill the screen, or (if it already does) go to the smallest size, centred. Animated on the Mac."""
    from PySide6.QtCore import QRect

    from listo.ui.style.tokens import WINDOW_MIN

    screen = window.screen()
    if screen is None:
        return
    area = screen.availableGeometry()
    g = window.frameGeometry()
    if g.width() >= area.width() - 4 and g.height() >= area.height() - 4:
        w, h = max(WINDOW_MIN[0], window.minimumWidth()), max(WINDOW_MIN[1], window.minimumHeight())
        to = QRect(area.x() + (area.width() - w) // 2, area.y() + (area.height() - h) // 2, w, h)
    else:
        to = area
    if not animate_to(window, to):
        window.setGeometry(to)


def fill_screen(window: QWidget) -> None:
    """Fill the screen's free area (everything but the menu bar and Dock)."""
    screen = window.screen()
    if screen is None:
        return
    window.setGeometry(screen.availableGeometry())


def _objc():
    """(objc library, objc_msgSend address, selector maker), or None off the Mac's real windows."""
    if sys.platform != "darwin":
        return None
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.platformName() != "cocoa":
        return None  # offscreen (tests, smoke test): winId() isn't an NSView, and asking it crashes
    import ctypes
    import ctypes.util

    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
    return objc, address, objc.sel_registerName


def _ns_window(window: QWidget, address, sel):
    import ctypes

    # objc_msgSend must be called with the exact signature on Apple silicon: one typed pointer each.
    get = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(address)
    return get(int(window.winId()), sel(b"window"))  # the window's NSView, then its NSWindow


def animate_to(window: QWidget, rect) -> bool:
    """[nsWindow setFrame:display:animate:YES]: the Mac's own smooth resize. False if it couldn't."""
    try:
        found = _objc()
        if found is None:
            return False
        import ctypes

        from PySide6.QtGui import QGuiApplication

        _objc_lib, address, sel = found
        ns_window = _ns_window(window, address, sel)
        if not ns_window:
            return False

        class NSRect(ctypes.Structure):
            _fields_ = [
                ("x", ctypes.c_double),
                ("y", ctypes.c_double),
                ("w", ctypes.c_double),
                ("h", ctypes.c_double),
            ]

        # the Mac counts up from the bottom of the main screen; Qt counts down from its top
        main = QGuiApplication.primaryScreen().geometry()
        frame = NSRect(rect.x(), main.height() - (rect.y() + rect.height()), rect.width(), rect.height())
        set_frame = ctypes.CFUNCTYPE(
            None, ctypes.c_void_p, ctypes.c_void_p, NSRect, ctypes.c_bool, ctypes.c_bool
        )(address)
        set_frame(ns_window, sel(b"setFrame:display:animate:"), frame, True, True)
        return True
    except Exception:
        return False


def hide_mac_title(window: QWidget) -> bool:
    """[window.nsWindow setTitleVisibility:NSWindowTitleHidden]. False if it couldn't (the title shows)."""
    try:
        found = _objc()
        if found is None:
            return False
        import ctypes

        _objc_lib, address, sel = found
        ns_window = _ns_window(window, address, sel)
        if not ns_window:
            return False
        set_long = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)(address)
        set_long(ns_window, sel(b"setTitleVisibility:"), 1)  # NSWindowTitleHidden
        return True
    except Exception:
        return False
