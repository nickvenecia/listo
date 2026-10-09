"""The Mac title bar, drawn by Listo: the app's dark background with the "listo." wordmark centred.

Qt (6.9+) lets the window's content run up under the title bar (ExpandedClientAreaHint) with no
bar background (NoTitleBarBackgroundHint); the traffic-light buttons stay where they are. The Mac's
own title text is hidden with one call into AppKit (ctypes, no extra packages). Dragging the bar
moves the window; double-clicking zooms it, like any Mac title bar.

Windows and Linux keep their system title bar (dark, via the app's colour scheme in app.py).
If any piece is missing (older Qt, the AppKit call fails), the normal title bar stays.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QWidget

from . import theme
from .tokens import TITLEBAR_H
from .widgets import hbox

log_name = __name__


def supported() -> bool:
    return sys.platform == "darwin" and hasattr(Qt.WindowType, "ExpandedClientAreaHint")


def install(window: QMainWindow) -> TitleBar | None:
    """Turn on Listo's own title bar for this window (Mac only). Returns the bar to put on top."""
    if not supported():
        return None
    window.setWindowFlag(Qt.WindowType.ExpandedClientAreaHint, True)
    if hasattr(Qt.WindowType, "NoTitleBarBackgroundHint"):
        window.setWindowFlag(Qt.WindowType.NoTitleBarBackgroundHint, True)
    return TitleBar(window)


class TitleBar(QWidget):
    def __init__(self, window: QMainWindow):
        super().__init__()
        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._window = window
        self.setFixedHeight(TITLEBAR_H)
        lay = hbox(self, 0, 0)
        word = QLabel(f'listo<span style="color:{theme.ACCENT}">.</span>')
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
            if top > 0:
                self.setFixedHeight(top)
        hide_mac_title(self._window)

    def mousePressEvent(self, e):
        handle = self._window.windowHandle()
        if e.button() == Qt.MouseButton.LeftButton and handle is not None:
            handle.startSystemMove()
        e.accept()

    def mouseDoubleClickEvent(self, e):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()
        e.accept()


def hide_mac_title(window: QWidget) -> bool:
    """[window.nsWindow setTitleVisibility:NSWindowTitleHidden]. False if it couldn't (the title shows)."""
    if sys.platform != "darwin":
        return False
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
