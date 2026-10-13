"""The Mac title bar, drawn by Listo: the app's background (light or dark) with the "listo." wordmark centred.

Qt (6.9+) lets the window's content run up under the title bar (ExpandedClientAreaHint) with no
bar background (NoTitleBarBackgroundHint); the traffic-light buttons stay where they are, on top of
our bar. Qt would normally push the content below that area (the "safe area"), which left an empty,
undraggable strip above our bar: the window turns that off, so our bar IS the title bar. The Mac's
own title text is hidden with one call into AppKit (ctypes, no extra packages). Dragging the bar
moves the window (Listo moves it itself); double-clicking zooms it, like any Mac title bar.

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
        self._drag: QPoint | None = None  # where in the window the drag grabbed it
        self.setFixedHeight(TITLEBAR_H)
        ignore_safe_area(self)
        lay = hbox(self, 0, 0)
        word = QLabel(theme.wordmark())
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
        if e.button() == Qt.MouseButton.LeftButton and not self._window.isFullScreen():
            self._drag = e.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
        e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            if self._window.isMaximized():  # pulling a zoomed window off: restore it under the pointer
                self._window.showNormal()
                self._drag = QPoint(self._window.width() // 2, self.height() // 2)
            self._window.move(e.globalPosition().toPoint() - self._drag)
        e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None
        e.accept()

    def mouseDoubleClickEvent(self, e):
        self._drag = None
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()
        e.accept()


def hide_mac_title(window: QWidget) -> bool:
    """[window.nsWindow setTitleVisibility:NSWindowTitleHidden]. False if it couldn't (the title shows)."""
    if sys.platform != "darwin":
        return False
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.platformName() != "cocoa":
        return False  # offscreen (tests, smoke test): winId() isn't an NSView, and asking it crashes
    try:
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
        # objc_msgSend must be called with the exact signature on Apple silicon: one typed pointer each.
        get = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(address)
        set_long = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)(address)
        view = int(window.winId())  # the window's NSView
        ns_window = get(view, objc.sel_registerName(b"window"))
        if not ns_window:
            return False
        set_long(ns_window, objc.sel_registerName(b"setTitleVisibility:"), 1)  # NSWindowTitleHidden
        return True
    except Exception:
        return False
