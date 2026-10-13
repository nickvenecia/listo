"""The window's glass: a flat backdrop behind everything, floating rounded panels with a gentle shadow,
and the right panel that slides in and out.

In the spirit of Apple's Liquid Glass (macOS 26+): content sits on the window, tools float above it on
rounded, lightly see-through panels with a bright hairline edge. Qt can't blur what's behind a widget, so
the glass is a tinted, translucent fill over the backdrop; everything else (shape, edge, shadow) is the same.

Kept cheap so it stays smooth: the backdrop and each panel are drawn once into pictures and reused until the
window size or the look changes, and the right panel slides as one solid sheet over the content (the file list
makes room once, not on every frame of the slide).
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QRect, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from listo.ui.style import theme, tokens


def _look() -> tuple:
    """Everything the glass's colors depend on (a new look draws it again)."""
    return (
        tokens.WINDOW_TOP,
        tokens.WINDOW_BOTTOM,
        tokens.GLASS,
        tokens.GLASS_STROKE,
        tokens.GLASS_EDGE,
        tokens.GLASS_SHADOW,
    )


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


def paint_shadow(p: QPainter, r: QRectF) -> None:
    """A soft, wide, faint shadow all round a panel, so it floats (the Mac's, never a dark smudge)."""
    rad = tokens.GLASS_R
    base = theme.qcolor(tokens.GLASS_SHADOW)
    steps, spread = tokens.GLASS_SHADOW_STEPS, tokens.GLASS_SHADOW_SPREAD
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(steps, 0, -1):
        t = i / steps
        c = QColor(base)
        c.setAlphaF(base.alphaF() * (1 - t) ** 2 / steps * 3)
        grow = spread * t
        path = QPainterPath()
        path.addRoundedRect(  # even all round (Apple's shadows spread evenly), just a touch lower
            r.adjusted(-grow, -grow + tokens.GLASS_SHADOW_DROP, grow, grow + tokens.GLASS_SHADOW_DROP),
            rad + grow,
            rad + grow,
        )
        p.fillPath(path, c)


def paint_glass(p: QPainter, r: QRectF) -> None:
    """The panel itself, like Apple's glass: one even tone (no gradient) and a single hairline edge, a touch
    brighter along the top where the light catches it."""
    rad = tokens.GLASS_R
    path = QPainterPath()
    path.addRoundedRect(r, rad, rad)
    p.fillPath(path, theme.qcolor(tokens.GLASS))
    line = QPainterPath()
    line.addRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), rad - 0.5, rad - 0.5)
    pen = QLinearGradient(r.topLeft(), r.bottomLeft())
    pen.setColorAt(0, theme.qcolor(tokens.GLASS_EDGE))
    pen.setColorAt(min(1.0, tokens.GLASS_EDGE_FADE / max(1.0, r.height())), theme.qcolor(tokens.GLASS_STROKE))
    pen.setColorAt(1, theme.qcolor(tokens.GLASS_STROKE))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(pen, 1))
    p.drawPath(line)


def _shadow_margin() -> int:
    return tokens.GLASS_SHADOW_SPREAD + tokens.GLASS_SHADOW_DROP + 2


class GlassRoot(QWidget):
    """The window's backdrop: the backdrop color, the glass behind each floating panel, and the dock's shadow."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Root")
        self.panels: list[QWidget] = []
        self.dock: Dock | None = None
        self._pix: QPixmap | None = None
        self._pix_key = None
        self._shadow: QPixmap | None = None
        self._shadow_key = None

    def float(self, w: QWidget) -> None:
        """Paint glass behind `w` (it must be a descendant)."""
        self.panels.append(w)

    def _panel_rect(self, w: QWidget) -> QRectF | None:
        if not w.isVisible() or w.width() < 2:
            return None
        return QRectF(w.mapTo(self, QPoint(0, 0)), w.size()).adjusted(0.5, 0.5, -0.5, -0.5)

    def _backdrop(self) -> QPixmap:
        """The backdrop and the panels' glass, drawn once per size and look."""
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
                    paint_shadow(p, r)
                    paint_glass(p, r)
            p.end()
            self._pix, self._pix_key = pix, key
        return self._pix

    def dock_shadow(self) -> QPixmap:
        """The dock's shadow, drawn once per size and look (it's reused at every step of the slide)."""
        d = self.dock
        dpr = self.devicePixelRatioF()
        key = (d.size(), _look(), dpr)
        if self._shadow is None or key != self._shadow_key:
            m = _shadow_margin()
            pix = _canvas(d.width() + 2 * m, d.height() + 2 * m, dpr)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            paint_shadow(p, QRectF(m + 0.5, m + 0.5, d.width() - 1, d.height() - 1))
            p.end()
            self._shadow, self._shadow_key = pix, key
        return self._shadow

    def paintEvent(self, e):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._backdrop())
        d = self.dock
        if d is not None and d.isVisible():
            m = _shadow_margin()
            p.drawPixmap(d.x() - m, d.y() - m, self.dock_shadow())
        p.end()


class Dock(QWidget):
    """The right panel's glass sheet: slides in from the right when opened, out when closed. It floats over the
    window rather than sitting in the layout, so sliding it only moves a picture; the content beside it makes
    room by the window's right margin, step by step with the sheet. While it slides, the list beside it
    (`follower`) is shown as still pictures that move apart or together (a live list is too slow to redraw
    on every step)."""

    def __init__(self, content: QWidget, root: GlassRoot, top_of: QWidget, body):
        super().__init__(root)
        self.root = root
        self.top_of = top_of  # a panel in the same row (the sidebar): the dock lines up with it
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
        away = self.root.width() + _shadow_margin()  # just past the window's right edge
        x = round(away + (rest.x() - away) * self._t)
        old = self.geometry()
        self.setGeometry(x, rest.y(), rest.width(), rest.height())
        self.content.setGeometry(0, 0, rest.width(), rest.height())
        # the shadow moves with it: redraw just around the old and new spots
        m = _shadow_margin()
        if old.isValid():
            self.root.update(old.adjusted(-m, -m, m, m))
        self.root.update(self.geometry().adjusted(-m, -m, m, m))
        # the content beside it ends a gap before it
        gap = tokens.GLASS_GAP
        room = max(gap, self.root.width() - x + gap) if self.isVisible() or self.opened else gap
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
        """The glass sheet as it looks in place (with the window's backdrop and shadow at its corners),
        drawn once per size and look, then just copied at every step of the slide."""
        rest = self._rest()
        dpr = self.devicePixelRatioF()
        key = (rest, self.root.size(), _look(), dpr)
        if self._pix is None or key != self._pix_key:
            pix = _canvas(rest.width(), rest.height(), dpr)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.translate(-rest.x(), -rest.y())  # draw in window coordinates
            paint_backdrop(p, QRectF(rest), self.root.size())
            r = QRectF(rest).adjusted(0.5, 0.5, -0.5, -0.5)
            paint_shadow(p, r)
            paint_glass(p, r)
            p.end()
            self._pix, self._pix_key = pix, key
        return self._pix

    def paintEvent(self, _e):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._sheet())
        p.end()


def glass(w: QWidget) -> QWidget:
    """Style `w` as a floating glass panel."""
    w.setObjectName(w.objectName() or "Glass")
    w.setProperty("glass", True)  # the backdrop paints the glass behind it; the widget stays clear
    return w
