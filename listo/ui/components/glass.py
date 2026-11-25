"""The window's frame: one flat backdrop (the frame's material) behind everything, the columns on it (the
right panel that slides in and out, Settings' sections), and soft shadows for things lifted off the page.

The look is FeatureSoup's: the columns sit flush with the window's edges, in the frame's own material, with
no edge and no shadow; what sets the work area apart is its own fill and the curve of its top corners
(`#Work` in the stylesheet), not a floating panel.

Kept cheap so it stays smooth: the backdrop and each column are drawn once into pictures and reused until the
window size or the look changes, and the right panel slides as one solid sheet over the content (the file list
makes room once, not on every frame of the slide).
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QRect, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

from listo.ui.style import theme, tokens


def _look() -> tuple:
    """Everything the glass's colors depend on (a new look draws it again)."""
    return (tokens.WINDOW_TOP, tokens.WINDOW_BOTTOM, tokens.GLASS)


def _canvas(w: int, h: int, dpr: float) -> QPixmap:
    pix = QPixmap(max(1, round(w * dpr)), max(1, round(h * dpr)))
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.GlobalColor.transparent)
    return pix


def paint_backdrop(p: QPainter, rect: QRectF, size) -> None:
    """The window's backdrop, for a window of `size` (in window coordinates)."""
    g = QLinearGradient(0, 0, size.width() * 0.4, size.height())
    g.setColorAt(0, theme.qcolor(tokens.WINDOW_TOP))
    g.setColorAt(1, theme.qcolor(tokens.WINDOW_BOTTOM))
    p.fillRect(rect, g)


def paint_shadow(p: QPainter, r: QRectF, rad: float, color: str = "") -> None:
    """A soft, wide, faint shadow all round something lifted off the page (a toast), never a dark smudge.
    `rad`: its corners; `color`: a deeper shadow (a toast's)."""
    base = theme.qcolor(color or tokens.SHADOW)
    steps, spread = tokens.SHADOW_STEPS, tokens.SHADOW_SPREAD
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(steps, 0, -1):
        t = i / steps
        c = QColor(base)
        c.setAlphaF(base.alphaF() * (1 - t) ** 2 / steps * 3)
        grow = spread * t
        path = QPainterPath()
        path.addRoundedRect(  # even all round (Apple's shadows spread evenly), just a touch lower
            r.adjusted(-grow, -grow + tokens.SHADOW_DROP, grow, grow + tokens.SHADOW_DROP),
            rad + grow,
            rad + grow,
        )
        p.fillPath(path, c)


def paint_glass(p: QPainter, r: QRectF) -> None:
    """A column itself: the frame's material, square, flush with what's beside it (no edge, no shadow)."""
    p.fillRect(r, theme.qcolor(tokens.GLASS))


def shadow_margin() -> int:
    """The room a lifted thing's shadow needs around it."""
    return tokens.SHADOW_SPREAD + tokens.SHADOW_DROP + 2


class GlassRoot(QWidget):
    """The window's backdrop: the frame's color and the column behind each panel."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Root")
        self.panels: list[QWidget] = []
        self.dock: Dock | None = None
        self._pix: QPixmap | None = None
        self._pix_key = None

    def float(self, w: QWidget) -> None:
        """Paint a column behind `w` (it must be a descendant)."""
        self.panels.append(w)

    def _panel_rect(self, w: QWidget) -> QRectF | None:
        if not w.isVisible() or w.width() < 2:
            return None
        return QRectF(w.mapTo(self, QPoint(0, 0)), w.size())

    def _backdrop(self) -> QPixmap:
        """The backdrop and the columns, drawn once per size and look."""
        rects = [self._panel_rect(w) for w in self.panels]
        dpr = self.devicePixelRatioF()
        key = (self.size(), tuple((r.getRect() if r else None) for r in rects), _look(), dpr)
        if self._pix is None or key != self._pix_key:
            pix = _canvas(self.width(), self.height(), dpr)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            paint_backdrop(p, QRectF(self.rect()), self.size())
            for r in rects:
                if r is not None:
                    paint_glass(p, r)
            p.end()
            self._pix, self._pix_key = pix, key
        return self._pix

    def paintEvent(self, e):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._backdrop())
        p.end()


class Dock(QWidget):
    """The right panel's column: slides in from the right when opened, out when closed. It floats over the
    window rather than sitting in the layout, so sliding it only moves a picture; the content beside it makes
    room by the window's right margin, step by step with the sheet. While it slides, the list beside it
    (`follower`) is shown as still pictures that move apart or together (a live list is too slow to redraw
    on every step)."""

    def __init__(self, content: QWidget, root: GlassRoot, top_of: QWidget, body):
        super().__init__(root)
        self.root = root
        self.top_of = top_of  # a widget in the same row (the list's column): the dock lines up with its top
        self.body = body  # the row's layout: its right margin is the room the dock takes
        self.follower = None  # () -> the widget beside it, if it can slide as pictures (freeze / thaw)
        root.dock = self
        self.content = content
        content.setParent(self)
        self.target = tokens.INSPECTOR_W
        self.opened = False
        self._t = 0.0  # 0 = out of sight, 1 = in place
        self._frozen = None
        self._pix: QPixmap | None = None
        self._pix_key = None
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)  # nothing behind it needs drawing
        self.hide()
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(tokens.DOCK_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._step)
        self._anim.finished.connect(self._done)
        root.installEventFilter(self)

    # ------------------------------------------------------------------ where it goes
    def _rest(self) -> QRect:
        """Where it sits when open."""
        gap = tokens.GLASS_GAP
        top = self.top_of.y() if self.top_of.isVisible() else gap
        r = self.root.rect()
        return QRect(r.width() - gap - self.target, top, self.target, max(1, r.height() - top - gap))

    def _place(self) -> None:
        rest = self._rest()
        away = self.root.width()  # just past the window's right edge
        x = round(away + (rest.x() - away) * self._t)
        self.setGeometry(x, rest.y(), rest.width(), rest.height())
        self.content.setGeometry(0, 0, rest.width(), rest.height())
        # the content beside it ends where it starts; with it closed, the frame shows a WORK_INSET there
        inset = tokens.WORK_INSET
        room = max(inset, self.root.width() - x) if self.isVisible() or self.opened else inset
        mg = self.body.contentsMargins()
        if mg.right() != room:
            self.body.setContentsMargins(mg.left(), mg.top(), room, mg.bottom())
            if self.root.layout() is not None:
                self.root.layout().activate()  # now, so this step draws at its new size

    def _at(self, t: float) -> None:
        self._t = t
        self._place()

    def eventFilter(self, obj, e):
        if obj is self.root and e.type() == QEvent.Type.Resize:
            self._place()
        return False

    def set_target(self, width: int) -> None:
        """The open width (narrower on a smaller window)."""
        self.target = width
        self._place()

    # ------------------------------------------------------------------ opening and closing
    def set_open(self, on: bool, animate: bool = True) -> None:
        if on == self.opened:
            return
        self.opened = on
        self._anim.stop()
        self._thaw()
        if on:
            self.show()
            self.raise_()
        start, end = self._t, (1.0 if on else 0.0)
        if not animate or not self.root.isVisible():
            self._at(end)
            self._done()
            return
        f = self.follower() if self.follower else None
        if f is not None and f.isVisible() and hasattr(f, "freeze"):
            f.freeze(lambda: self._at(end), lambda: self._at(start))
            self._frozen = f
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()

    def _step(self, t) -> None:
        self._at(float(t))

    def _thaw(self) -> None:
        if self._frozen is not None:
            self._frozen.thaw()
            self._frozen = None

    def _done(self) -> None:
        self._thaw()
        if not self.opened:
            self.hide()
            self._place()
            self.root.update()

    # ------------------------------------------------------------------ drawing
    def _sheet(self) -> QPixmap:
        """The column as it looks in place, drawn once per size and look, then just copied at every step of
        the slide."""
        rest = self._rest()
        dpr = self.devicePixelRatioF()
        key = (rest, self.root.size(), _look(), dpr)
        if self._pix is None or key != self._pix_key:
            pix = _canvas(rest.width(), rest.height(), dpr)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.translate(-rest.x(), -rest.y())  # draw in window coordinates
            paint_backdrop(p, QRectF(rest), self.root.size())
            paint_glass(p, QRectF(rest))
            p.end()
            self._pix, self._pix_key = pix, key
        return self._pix

    def paintEvent(self, _e):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._sheet())
        p.end()


def glass(w: QWidget) -> QWidget:
    """Style `w` as a column on the frame."""
    w.setObjectName(w.objectName() or "Glass")
    w.setProperty("glass", True)  # the backdrop paints the column behind it; the widget stays clear
    return w
