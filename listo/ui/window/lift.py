"""Reordering files by dragging a row's grip, drawn live: the file lifts and follows the pointer, and the other
rows slide apart to open a gap where it will land (like the Finder or Reminders). List order is the order a
joined video plays in and the order Continuous Timecode runs in, so it's worth being able to change.

While a file is lifted the list shows a drawing of itself (every row drawn once into a picture, then just
moved), so the slide stays smooth on a long list. Letting go turns the gap into the new order.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QListView, QStyleOptionViewItem

from listo.ui.style import theme, tokens


class Lift(QObject):
    def __init__(self, view: QListView, shown: list[int], moving: list[int], grab: int, press_y: float):
        super().__init__(view)
        self.v = view
        off = view.verticalOffset()
        self.h = tokens.TABLE_ROW_H
        self.ids = [i for i in shown if i in set(moving)]  # in list order
        self.rest = [i for i in shown if i not in set(moving)]
        self.gap = self.h * len(self.ids)
        self.base = [n * self.h for n in range(len(self.rest))]  # where each other row sits without them
        self.end_y = len(self.rest) * self.h
        row_of = {i: n for n, i in enumerate(shown)}
        self.cur = {i: float(row_of[i] * self.h) for i in self.rest}  # where each is drawn now
        self.grab_dy = press_y + off - row_of[grab] * self.h
        self.mouse_y = press_y
        self.start_k = sum(1 for i in self.rest if row_of[i] < row_of[grab])
        self.k = self.start_k
        self.slot_y = float(self._slot(self.k))
        self._pix: dict[int, QPixmap] = {}
        self.timer = QTimer(self, interval=tokens.LIFT_STEP_MS, timeout=self._step)
        self.timer.start()

    # ------------------------------------------------------------------ where it lands
    def _slot(self, k: int) -> float:
        return self.base[k] if k < len(self.rest) else self.end_y

    def _target_k(self) -> int:
        card_top = self.mouse_y + self.v.verticalOffset() - self.grab_dy
        center = card_top + self.h / 2
        return sum(1 for y in self.base if y + self.h / 2 < center)

    def move_to(self, y: float) -> None:
        self.mouse_y = y

    def result(self) -> list[int] | None:
        """The new order of the rows shown, or None (it didn't move)."""
        if self.k == self.start_k:
            return None
        return self.rest[: self.k] + self.ids + self.rest[self.k :]

    # ------------------------------------------------------------------ each step
    def _step(self) -> None:
        vp = self.v.viewport()
        edge = self.h
        bar = self.v.verticalScrollBar()
        if self.mouse_y < edge:  # near the top or bottom: scroll
            bar.setValue(bar.value() - int((edge - self.mouse_y) / 2) - 1)
        elif self.mouse_y > vp.height() - edge:
            bar.setValue(bar.value() + int((self.mouse_y - vp.height() + edge) / 2) + 1)
        self.k = self._target_k()
        for n, i in enumerate(self.rest):  # each row eases towards where it should be
            target = self.base[n] + (self.gap if n >= self.k else 0)
            y = self.cur[i]
            self.cur[i] = y + (target - y) * tokens.LIFT_EASE if abs(target - y) > 0.5 else float(target)
        slot = self._slot(self.k)
        if abs(slot - self.slot_y) > 0.5:
            self.slot_y += (slot - self.slot_y) * tokens.LIFT_EASE
        else:
            self.slot_y = float(slot)
        vp.update()  # the card follows the pointer every step

    def stop(self) -> None:
        self.timer.stop()

    # ------------------------------------------------------------------ drawing
    def _picture(self, iid: int) -> QPixmap:
        """One row, drawn by the list's own painter (once, then reused while it slides)."""
        got = self._pix.get(iid)
        if got is not None:
            return got
        vp = self.v.viewport()
        dpr = vp.devicePixelRatioF()
        pix = QPixmap(max(1, round(vp.width() * dpr)), max(1, round(self.h * dpr)))
        pix.setDevicePixelRatio(dpr)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        opt = QStyleOptionViewItem()
        opt.rect = QRect(0, 0, vp.width(), self.h)
        model = self.v.model()
        self.v.itemDelegate().paint(p, opt, model.index(model.row_of(iid), 0))
        p.end()
        self._pix[iid] = pix
        return pix

    def paint(self) -> None:
        vp = self.v.viewport()
        off = self.v.verticalOffset()
        p = QPainter(vp)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, vh = vp.width(), vp.height()
        inset = tokens.ROW_INSET
        slot = QRectF(inset, self.slot_y - off + inset, w - 2 * inset, self.gap - 2 * inset)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor(tokens.CHIP))
        p.drawRoundedRect(slot, tokens.ROW_R, tokens.ROW_R)
        for i in self.rest:
            y = self.cur[i] - off
            if y + self.h < 0 or y > vh:
                continue
            p.drawPixmap(QPointF(0, y), self._picture(i))
        self._paint_card(p, self.mouse_y - self.grab_dy, w)
        p.end()

    def _paint_card(self, p: QPainter, y: float, w: float) -> None:
        """The lifted file(s): a raised card with a soft shadow, following the pointer."""
        shown = self.ids[: tokens.LIFT_ROWS_SHOWN]
        card = QRectF(tokens.ROW_INSET, y, w - 2 * tokens.ROW_INSET, self.h * len(shown))
        shadow = theme.qcolor(tokens.GLASS_SHADOW)
        for i in range(tokens.LIFT_SHADOW_STEPS, 0, -1):  # a soft shadow: rings fading outwards
            c = QColor(shadow)
            c.setAlphaF(shadow.alphaF() * 0.5 / i)
            grow = i * 1.5
            ring = QPainterPath()
            ring.addRoundedRect(
                card.adjusted(-grow, -grow + 2, grow, grow + 3), tokens.ROW_R + grow, tokens.ROW_R + grow
            )
            p.fillPath(ring, c)
        path = QPainterPath()
        path.addRoundedRect(card, tokens.ROW_R, tokens.ROW_R)
        p.fillPath(path, theme.qcolor(tokens.RAISED))
        p.setPen(theme.qcolor(tokens.ACCENT_EDGE))
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        top = y
        for i in shown:
            p.drawPixmap(QPointF(0, top), self._picture(i))
            top += self.h
        p.restore()
        if len(self.ids) > 1:  # how many are moving, in an accent badge at the top right
            label = str(len(self.ids))
            fm = p.fontMetrics()
            bw = max(tokens.SMALL_H, fm.horizontalAdvance(label) + 2 * tokens.SPACE_2)
            badge = QRectF(
                card.right() - bw / 2 - tokens.SPACE_2, card.top() - tokens.SMALL_H / 2, bw, tokens.SMALL_H
            )
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor(tokens.ACCENT))
            p.drawRoundedRect(badge, tokens.SMALL_H / 2, tokens.SMALL_H / 2)
            p.setPen(theme.qcolor(tokens.ON_ACCENT))
            p.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), label)
