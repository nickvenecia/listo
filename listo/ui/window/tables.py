"""The file list in the middle: one row per file, painted (no widgets per row, so hundreds of clips stay quick).

A row shows a grip (drag it to change the order), the thumbnail, the name, what the file is, what it becomes
(its format chip, a trim, the new name), and on the right its status and progress. The row's buttons
(captions, trim, details, try again, show the new file) show while the pointer is over it or it's picked.
Right-click for the same commands and for taking files off the list.

The window talks to each row through a `Row` (it.card): set_state, set_progress and the rest, so the
converting code never deals with painting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QFont, QImage, QPainter, QPainterPath, QPixmap, QRegion
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QListView,
    QStyledItemDelegate,
    QToolTip,
    QWidget,
)

from listo.ui.style import theme, tokens
from listo.ui.window.lift import Lift

STATES = {
    "probing": "Reading…",
    "ready": "Ready",
    "waiting": "Waiting",
    "converting": "Converting",
    "paused": "Paused",
    "done": "Listo",
    "failed": "Failed",
    "skipped": "Skipped",
    "canceled": "Canceled",
    "unsupported": "Can't Convert",
    "warning": "Check This One",
    "transcribing": "Making Captions",
    "downloading": "Downloading",
}
TONES = {  # the status word's color (tokens), by state
    "probing": "FAINT",
    "converting": "ACCENT",
    "downloading": "ACCENT",
    "transcribing": "ACCENT",
    "paused": "WARN",
    "warning": "WARN",
    "done": "GOOD",
    "failed": "BAD",
    "unsupported": "BAD",
}
BUSY = ("converting", "paused", "downloading", "transcribing")
FINISHED_OK = ("done", "warning")
BUTTONS = (  # (key, icon, tip): left to right
    ("cc", "captions", ""),
    ("trim", "scissors", "Trim"),
    ("details", "info", "Details"),
    ("retry", "retry", "Try Again"),
    ("reveal", "reveal", "Show the New File"),
)
CC_TIPS = {
    "working": "Making captions in the background…",
    "failed": "Couldn't make captions. Click to try again",
    "review": "Captions ready. Click to check them",
    "reviewed": "Captions checked. Click to edit",
}


def rounded_thumb(data: bytes) -> QPixmap | None:
    """A file's thumbnail, filled into the 16:9 box with rounded corners (drawn once, kept)."""
    img = QImage.fromData(data) if data else QImage()
    if img.isNull():
        return None
    w, h, dpr = tokens.THUMB_W, tokens.THUMB_H, 2.0
    out = QPixmap(int(w * dpr), int(h * dpr))
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    scaled = QPixmap.fromImage(img).scaled(
        int(w * dpr),
        int(h * dpr),
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(dpr)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, tokens.RADIUS_SM, tokens.RADIUS_SM)
    p.setClipPath(path)
    p.drawPixmap(int(-(scaled.width() / dpr - w) / 2), int(-(scaled.height() / dpr - h) / 2), scaled)
    p.end()
    return out


@dataclass(eq=False)
class Row:
    """What one row shows. The window changes it through the setters; each change redraws just that row."""

    item_id: int
    name: str
    kind: str
    meta: str = "Reading…"
    output: str = ""
    fmt: tuple[str, bool, bool] = ("", False, False)  # (label, changed for this file, can change)
    trim: str = ""
    cc: tuple[str, str] = ("", "")  # ('' | working | failed | review | reviewed, detail)
    state: str = "probing"
    status: str = STATES["probing"]
    progress: float = 0.0
    thumb: QPixmap | None = None
    selected: bool = False
    owner: FileList | None = field(default=None, repr=False)

    def _changed(self) -> None:
        if self.owner is not None:
            self.owner.row_changed(self.item_id)

    def set_thumb(self, data: bytes) -> None:
        pm = rounded_thumb(data)
        if pm is not None:
            self.thumb = pm
            self._changed()

    def set_meta(self, text: str) -> None:
        if self.meta != text:
            self.meta = text
            self._changed()

    def set_output(self, text: str) -> None:
        if self.output != text:
            self.output = text
            self._changed()

    def set_format(self, label: str, overridden: bool, editable: bool) -> None:
        if self.fmt != (label, overridden, editable):
            self.fmt = (label, overridden, editable)
            self._changed()

    def set_trim(self, text: str) -> None:
        if self.trim != text:
            self.trim = text
            self._changed()

    def set_captions(self, status: str, detail: str = "") -> None:
        """'' = captions off for this clip; 'working' / 'failed' / 'review' / 'reviewed'."""
        if self.cc != (status, detail):
            self.cc = (status, detail)
            self._changed()

    def set_name(self, name: str) -> None:
        if self.name != name:
            self.name = name
            self._changed()

    def set_progress(self, frac: float) -> None:
        frac = max(0.0, min(1.0, frac))
        if abs(frac - self.progress) >= 0.001 or (frac in (0.0, 1.0) and frac != self.progress):
            self.progress = frac
            self._changed()

    def set_state(self, state: str, text: str = "") -> None:
        label = text or STATES.get(state, state)
        if (state, label) == (self.state, self.status):
            return
        if state in FINISHED_OK:
            self.progress = 1.0
        self.state, self.status = state, label
        self._changed()

    def set_selected(self, on: bool) -> None:
        if self.selected != on:
            self.selected = on
            self._changed()

    # what shows, by state
    def buttons(self) -> list[str]:
        s, k = self.state, self.kind
        shown = {
            "cc": bool(self.cc[0]) and s in ("ready", "waiting", "done", "warning"),
            "trim": s in ("ready", "waiting") and k in ("video", "audio"),
            "details": s in ("failed", "done", "skipped", "unsupported", "warning"),
            "retry": s in ("failed", "canceled", "skipped", "warning"),
            "reveal": s in FINISHED_OK,
        }
        return [key for key, _i, _t in BUTTONS if shown[key]]

    def bar_shown(self) -> bool:
        return self.state in BUSY or self.state in FINISHED_OK


class FileModel(QAbstractListModel):
    """The rows the list shows right now (in list order, after the place and search filters)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ids: list[int] = []
        self.rows: dict[int, Row] = {}
        self._pos: dict[int, int] = {}

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.ids)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.UserRole:
            return None
        return self.rows.get(self.ids[index.row()])

    def row_of(self, iid: int) -> int:
        return self._pos.get(iid, -1)

    def set_ids(self, ids: list[int]) -> None:
        if ids == self.ids:
            return
        self.beginResetModel()
        self.ids = list(ids)
        self._pos = {i: n for n, i in enumerate(self.ids)}
        self.endResetModel()

    def append(self, iid: int) -> None:
        n = len(self.ids)
        self.beginInsertRows(QModelIndex(), n, n)
        self.ids.append(iid)
        self._pos[iid] = n
        self.endInsertRows()

    def remove(self, iid: int) -> None:
        n = self._pos.get(iid, -1)
        if n < 0:
            return
        self.beginRemoveRows(QModelIndex(), n, n)
        del self.ids[n]
        self._pos = {i: k for k, i in enumerate(self.ids)}
        self.endRemoveRows()


def _font(size: int, weight: int) -> QFont:
    return theme.font(size, weight)


class _Parts:
    """Where everything sits in one row (painting and clicking use the same numbers)."""

    def __init__(self, rect: QRect, row: Row, show_buttons: bool):
        i = tokens.ROW_INSET
        self.shape = QRectF(rect.adjusted(1, i, -1, -i))
        inner = rect.adjusted(tokens.SPACE_1, i, -tokens.SPACE_2, -i)
        self.grip = QRect(inner.left(), inner.top(), tokens.GRIP_W, inner.height())
        th_y = inner.top() + (inner.height() - tokens.THUMB_H) // 2
        self.thumb = QRect(self.grip.right() + 1, th_y, tokens.THUMB_W, tokens.THUMB_H)
        right = inner.right() - tokens.STATUS_W
        self.status_area = QRect(right + 1, inner.top(), tokens.STATUS_W, inner.height())
        x0 = self.thumb.right() + 1 + tokens.SPACE_3
        self.text = QRect(x0, inner.top(), max(1, right - tokens.SPACE_3 - x0), inner.height())
        # the right column: [buttons…] status, and the progress bar under them
        mid = inner.top() + inner.height() // 2
        bar = row.bar_shown()
        top_y = (mid - tokens.SMALL_H + tokens.SPACE_1 // 2) if bar else (mid - tokens.SMALL_H // 2)
        self.top_row = QRect(self.status_area.left(), top_y, tokens.STATUS_W, tokens.SMALL_H)
        self.bar = QRect(self.status_area.left(), mid + tokens.SPACE_1, tokens.STATUS_W, tokens.BAR_H)
        self.buttons: dict[str, QRect] = {}
        self.status_w = 0
        self.show_buttons = show_buttons
        self._row = row

    def place_buttons(self, status_w: int) -> None:
        """Buttons go left of the status word, right to left."""
        self.status_w = status_w
        x = self.top_row.right() - status_w - tokens.SPACE_2
        keys = self._row.buttons()
        shown = keys if self.show_buttons else [k for k in keys if k == "cc"]
        for key in reversed(shown):
            x -= tokens.SMALL_H
            self.buttons[key] = QRect(x + 1, self.top_row.top(), tokens.SMALL_H, tokens.SMALL_H)
            x -= tokens.SPACE_1 // 2


class RowPainter(QStyledItemDelegate):
    """Paints one file: its highlight (hover, picked), thumbnail, words, chip, status, bar and buttons."""

    def __init__(self, view: FileList):
        super().__init__(view)
        self.view = view

    def sizeHint(self, option, index) -> QSize:
        return QSize(0, tokens.TABLE_ROW_H)

    def parts(self, rect: QRect, row: Row) -> _Parts:
        show = row.selected or self.view.hover_id == row.item_id
        pt = _Parts(rect, row, show)
        f = _font(tokens.TEXT_SM, tokens.WEIGHT_SEMIBOLD)
        from PySide6.QtGui import QFontMetrics

        status_w = min(pt.top_row.width() // 2, QFontMetrics(f).horizontalAdvance(row.status) + 1)
        pt.place_buttons(status_w)
        return pt

    def chip_rect(self, rect: QRect, row: Row) -> QRect:
        """The format chip's spot (clicking it changes this one file's format)."""
        pt = self.parts(rect, row)
        return self._lines(pt, row)[2]

    def _lines(self, pt: _Parts, row: Row) -> tuple[QRect, QRect, QRect, int]:
        from PySide6.QtGui import QFontMetrics

        name_h = QFontMetrics(_font(tokens.TEXT_MD, tokens.WEIGHT_SEMIBOLD)).height()
        meta_h = QFontMetrics(_font(tokens.TEXT_SM, tokens.WEIGHT_REGULAR)).height()
        third = tokens.CHIP_SM_H if (row.fmt[0] or row.trim or row.output) else 0
        gap = tokens.SPACE_1 // 2
        total = name_h + gap + meta_h + ((gap + third) if third else 0)
        y = pt.text.top() + (pt.text.height() - total) // 2
        name = QRect(pt.text.left(), y, pt.text.width(), name_h)
        meta = QRect(pt.text.left(), name.bottom() + 1 + gap, pt.text.width(), meta_h)
        chip = QRect()
        if row.fmt[0]:
            fm = QFontMetrics(_font(tokens.TEXT_XS, tokens.WEIGHT_SEMIBOLD))
            label = row.fmt[0] + ("  ▾" if row.fmt[2] else "")
            w = fm.horizontalAdvance(label) + 2 * tokens.SPACE_2
            chip = QRect(pt.text.left(), meta.bottom() + 1 + gap, w, tokens.CHIP_SM_H)
        return name, meta, chip, meta.bottom() + 1 + gap

    def paint(self, painter: QPainter, option, index) -> None:
        row: Row | None = index.data(Qt.ItemDataRole.UserRole)
        if row is None:
            return
        p = painter
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pt = self.parts(option.rect, row)
        hover = self.view.hover_id == row.item_id
        fill = tokens.CARD_SELECTED if row.selected else (tokens.ROW_HOVER if hover else "")
        if fill:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor(fill))
            p.drawRoundedRect(pt.shape, tokens.ROW_R, tokens.ROW_R)

        # the grip you drag it by
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor(tokens.FAINT))
        c = QPointF(pt.grip.center())
        gap = tokens.GRIP_GAP
        for dx in (-gap / 2, gap / 2):
            for dy in (-gap, 0, gap):
                p.drawEllipse(QPointF(c.x() + dx, c.y() + dy), tokens.GRIP_DOT, tokens.GRIP_DOT)

        # the picture: always on black (a monitor), the kind's icon until a thumbnail arrives
        path = QPainterPath()
        path.addRoundedRect(QRectF(pt.thumb), tokens.RADIUS_SM, tokens.RADIUS_SM)
        p.fillPath(path, theme.qcolor(tokens.SCREEN))
        if row.thumb is not None:
            p.drawPixmap(pt.thumb.topLeft(), row.thumb)
        else:
            icon = {"video": "film", "photo": "image", "audio": "audio", "link": "link"}.get(row.kind, "file")
            pm = theme.pixmap(icon, tokens.ICON_LG, tokens.SCREEN_FAINT, 1.6)
            s = tokens.ICON_LG
            p.drawPixmap(pt.thumb.center().x() - s // 2 + 1, pt.thumb.center().y() - s // 2 + 1, pm)

        name_r, meta_r, chip_r, third_y = self._lines(pt, row)
        p.setFont(_font(tokens.TEXT_MD, tokens.WEIGHT_SEMIBOLD))
        p.setPen(theme.qcolor(tokens.TEXT))
        p.drawText(
            name_r,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            p.fontMetrics().elidedText(row.name, Qt.TextElideMode.ElideMiddle, name_r.width()),
        )
        p.setFont(_font(tokens.TEXT_SM, tokens.WEIGHT_REGULAR))
        p.setPen(theme.qcolor(tokens.MUTED))
        p.drawText(
            meta_r,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            p.fontMetrics().elidedText(row.meta, Qt.TextElideMode.ElideRight, meta_r.width()),
        )
        # third line: the format chip, a trim, then the new name
        x = pt.text.left()
        if not chip_r.isNull():
            custom = row.fmt[1]
            p.setPen(theme.qcolor(tokens.ACCENT_EDGE if custom else tokens.BORDER_STRONG))
            p.setBrush(theme.qcolor(tokens.ACCENT_TINT) if custom else Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(
                QRectF(chip_r).adjusted(0.5, 0.5, -0.5, -0.5), tokens.RADIUS_SM, tokens.RADIUS_SM
            )
            p.setFont(_font(tokens.TEXT_XS, tokens.WEIGHT_SEMIBOLD))
            p.setPen(theme.qcolor(tokens.ACCENT if custom else tokens.MUTED))
            p.drawText(chip_r, int(Qt.AlignmentFlag.AlignCenter), row.fmt[0] + ("  ▾" if row.fmt[2] else ""))
            x = chip_r.right() + 1 + tokens.SPACE_2
        line = QRect(x, third_y, max(1, pt.text.right() - x), tokens.CHIP_SM_H)
        words = "  ".join(w for w in (row.trim, row.output) if w)
        if words:
            p.setFont(_font(tokens.TEXT_SM, tokens.WEIGHT_REGULAR))
            p.setPen(theme.qcolor(tokens.FAINT))
            p.drawText(
                line,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                p.fontMetrics().elidedText(words, Qt.TextElideMode.ElideMiddle, line.width()),
            )

        # the right column: status word, buttons, bar
        p.setFont(_font(tokens.TEXT_SM, tokens.WEIGHT_SEMIBOLD))
        p.setPen(theme.qcolor(getattr(tokens, TONES.get(row.state, "MUTED"))))
        p.drawText(
            pt.top_row,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            p.fontMetrics().elidedText(row.status, Qt.TextElideMode.ElideRight, pt.status_w),
        )
        for key, rect in pt.buttons.items():
            hot = self.view.hover_id == row.item_id and self.view.hover_part == key
            if hot:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.qcolor(tokens.RAISED))
                p.drawEllipse(QRectF(rect))
            icon = dict((k, i) for k, i, _t in BUTTONS)[key]
            color = tokens.MUTED
            if key == "cc":
                color = {"review": tokens.ACCENT, "reviewed": tokens.GOOD, "failed": tokens.BAD}.get(
                    row.cc[0], tokens.FAINT
                )
            s = tokens.ICON_SM
            p.drawPixmap(
                rect.center().x() - s // 2 + 1, rect.center().y() - s // 2 + 1, theme.pixmap(icon, s, color)
            )
        if row.bar_shown():
            r = QRectF(pt.bar)
            rad = tokens.BAR_H / 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor(tokens.FILL))
            p.drawRoundedRect(r, rad, rad)
            done = r.width() * (1.0 if row.state in FINISHED_OK else row.progress)
            if done > 0:
                tone = {"done": tokens.GOOD, "warning": tokens.WARN}.get(row.state, tokens.ACCENT)
                p.setBrush(theme.qcolor(tone))
                p.drawRoundedRect(QRectF(r.left(), r.top(), max(tokens.BAR_H, done), r.height()), rad, rad)
        p.restore()


class FileList(QListView):
    """The files, painted. Click picks (Shift / ⌘ add to it), double-click plays, the row buttons act."""

    pressed = Signal(int, object)  # item id, keyboard modifiers (for picking)
    opened = Signal(int)  # double-click: play it
    retry = Signal(int)
    reveal = Signal(int)
    details = Signal(int)
    trim_clicked = Signal(int)
    captions_clicked = Signal(int)
    format_clicked = Signal(int, QPoint)  # item id, where its menu opens (screen)
    reordered = Signal(list)  # the rows shown, in their new order (dragged by a grip)
    menu_wanted = Signal(int, QPoint)  # right-click on a row (0: on empty space)
    blank_clicked = Signal()  # a click on empty space: nothing picked
    step = Signal(int, object)  # ↑ / ↓: pick the row above / below (direction, modifiers)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("FileList")
        self.model_ = FileModel(self)
        self.setModel(self.model_)
        self.painter_ = RowPainter(self)
        self.setItemDelegate(self.painter_)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)  # the window keeps the picks
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QListView.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setAcceptDrops(False)  # files dropped anywhere are the window's
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hover_id = 0
        self.hover_part = ""
        self.can_reorder = True  # the window turns it off while converting
        self._press: tuple[QPoint, int] | None = None  # a grip was pressed, until it moves far enough to lift
        self._lift: Lift | None = None
        self._show_later: list[int] | None = None  # rows asked for while one was lifted

    # ------------------------------------------------------------------ rows
    def add_row(self, row: Row, shown: bool = True) -> None:
        row.owner = self
        self.model_.rows[row.item_id] = row
        if shown:
            self.model_.append(row.item_id)

    def drop_row(self, iid: int) -> None:
        self.model_.remove(iid)
        row = self.model_.rows.pop(iid, None)
        if row is not None:
            row.owner = None
        if self.hover_id == iid:
            self.hover_id = 0

    def show_ids(self, ids: list[int]) -> None:
        """Show these rows, in this order (the place and search filters decide which)."""
        if self._lift is not None:  # never refill under a row being dragged: after it lands
            self._show_later = list(ids)
            return
        self.model_.set_ids([i for i in ids if i in self.model_.rows])

    def shown_ids(self) -> list[int]:
        return list(self.model_.ids)

    def row_changed(self, iid: int) -> None:
        n = self.model_.row_of(iid)
        if n >= 0:
            self.viewport().update(self.visualRect(self.model_.index(n)))

    def scroll_to(self, iid: int) -> None:
        n = self.model_.row_of(iid)
        if n >= 0:
            self.scrollTo(self.model_.index(n), QAbstractItemView.ScrollHint.EnsureVisible)

    # ------------------------------------------------------------------ pointing
    def _hit(self, pos: QPoint) -> tuple[int, str, QRect]:
        """(item id, part, its rect) under `pos`: part is a button key, "chip", "row" or "" (empty space)."""
        index = self.indexAt(pos)
        row: Row | None = index.data(Qt.ItemDataRole.UserRole) if index.isValid() else None
        if row is None:
            return 0, "", QRect()
        rect = self.visualRect(index)
        pt = self.painter_.parts(rect, row)
        if pt.grip.contains(pos):
            return row.item_id, "grip", pt.grip
        for key, r in pt.buttons.items():
            if r.contains(pos):
                return row.item_id, key, r
        chip = self.painter_.chip_rect(rect, row)
        if not chip.isNull() and chip.contains(pos) and row.fmt[2]:
            return row.item_id, "chip", chip
        return row.item_id, "row", rect

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._lift is not None:
            self._lift.move_to(pos.y())
            return
        if self._press is not None and e.buttons() & Qt.MouseButton.LeftButton:
            if (pos - self._press[0]).manhattanLength() >= QApplication.startDragDistance():
                self.start_lift(self._press[1], self._press[0].y())
                if self._lift is not None:
                    self._lift.move_to(pos.y())
            return
        iid, part, _r = self._hit(e.position().toPoint())
        if (iid, part) != (self.hover_id, self.hover_part):
            old = self.hover_id
            self.hover_id, self.hover_part = iid, part
            for i in {old, iid} - {0}:
                self.row_changed(i)
            shape = Qt.CursorShape.ArrowCursor
            if part == "grip" and self.can_reorder:
                shape = Qt.CursorShape.OpenHandCursor
            elif part not in ("", "row", "grip"):
                shape = Qt.CursorShape.PointingHandCursor
            self.viewport().setCursor(shape)
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        old, self.hover_id, self.hover_part = self.hover_id, 0, ""
        if old:
            self.row_changed(old)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return
        self.setFocus()
        iid, part, rect = self._hit(e.position().toPoint())
        if not iid:
            if e.button() == Qt.MouseButton.LeftButton:
                self.blank_clicked.emit()
            return
        if e.button() == Qt.MouseButton.RightButton:
            return  # the context menu
        if part == "chip":
            self.format_clicked.emit(iid, self.viewport().mapToGlobal(rect.bottomLeft()))
            return
        if part == "grip" and not e.modifiers():
            row = self.model_.rows.get(iid)
            if row is not None and not row.selected:
                self.pressed.emit(iid, e.modifiers())
            self._press = (e.position().toPoint(), iid)
            return
        signal = {
            "cc": self.captions_clicked,
            "trim": self.trim_clicked,
            "details": self.details,
            "retry": self.retry,
            "reveal": self.reveal,
        }.get(part)
        if signal is not None:
            signal.emit(iid)
            return
        self.pressed.emit(iid, e.modifiers())

    def mouseDoubleClickEvent(self, e):
        iid, part, _r = self._hit(e.position().toPoint())
        if iid and part == "row" and e.button() == Qt.MouseButton.LeftButton:
            self.opened.emit(iid)

    def mouseReleaseEvent(self, e):
        if self._lift is not None:
            self.end_lift(drop=True)
        self._press = None
        e.accept()

    # ------------------------------------------------------------------ dragging to reorder
    def start_lift(self, iid: int, y: float) -> None:
        """Lift the pressed row (and the others picked with it) to drag it into place."""
        self._press = None
        if not self.can_reorder:
            return
        shown = self.shown_ids()
        picked = [i for i in shown if self.model_.rows[i].selected]
        moving = picked if iid in picked else [iid]
        self._lift = Lift(self, shown, moving, iid, y)
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def lifting(self) -> bool:
        return self._lift is not None

    def end_lift(self, drop: bool = True) -> None:
        lift, self._lift = self._lift, None
        if lift is None:
            return
        lift.stop()
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        got = lift.result() if drop else None
        later, self._show_later = self._show_later, None
        if later is not None:
            self.show_ids(later)
        self.viewport().update()
        if got is not None:
            QTimer.singleShot(0, lambda: self.reordered.emit(got))

    def contextMenuEvent(self, e):
        iid, _part, _r = self._hit(e.pos())
        self.menu_wanted.emit(iid, e.globalPos())

    def wheelEvent(self, e):
        """A trackpad swipe moves the list exactly as far as the fingers did. Qt's steps are a whole row, so
        a small swipe flew past several clips (the right panel already follows the fingers). A mouse wheel
        keeps its steps."""
        px = e.pixelDelta()
        if e.phase() != Qt.ScrollPhase.NoScrollPhase and abs(px.y()) > abs(px.x()):
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() - px.y())
            e.accept()
            return
        super().wheelEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self._lift is not None:
            self.end_lift(drop=False)  # put it back
            return
        step = {Qt.Key.Key_Up: -1, Qt.Key.Key_Down: 1}.get(e.key())
        if step is not None:
            self.step.emit(step, e.modifiers())
            return
        e.ignore()  # Delete, Space, Esc… are the window's

    def viewportEvent(self, e):
        if e.type() == QEvent.Type.ToolTip:
            iid, part, _r = self._hit(e.pos())
            row = self.model_.rows.get(iid)
            tip = ""
            if row is not None:
                if part == "cc":
                    tip = (f"{row.cc[1]}. " if row.cc[1] else "") + CC_TIPS.get(row.cc[0], "")
                elif part == "chip":
                    tip = "Change the format for just this file"
                elif part == "grip":
                    tip = "Drag to change the order (joined videos and timecode follow it)"
                elif part in dict((k, t) for k, _i, t in BUTTONS):
                    tip = dict((k, t) for k, _i, t in BUTTONS)[part]
                elif part == "row":
                    tip = theme.plain_tip("\n".join(w for w in (row.name, row.meta, row.output) if w))
            if tip:
                QToolTip.showText(e.globalPos(), tip, self.viewport())
            else:
                QToolTip.hideText()
            return True
        return super().viewportEvent(e)

    # ------------------------------------------------------------------ sliding with the right panel
    # Redrawing every row on every step of the panel's slide is too slow, so while it slides the list is two
    # still pictures (before and after) split where the status column starts: the status column moves with
    # the edge, the names are covered or uncovered. The real list comes back when it stops.
    _slide = None

    def _shot(self) -> QPixmap:
        vp = self.viewport()
        dpr = vp.devicePixelRatioF()
        pix = QPixmap(max(1, round(vp.width() * dpr)), max(1, round(vp.height() * dpr)))
        pix.setDevicePixelRatio(dpr)
        pix.fill(Qt.GlobalColor.transparent)
        vp.render(pix, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
        return pix

    def _seam(self) -> int:
        return max(0, self.viewport().width() - tokens.STATUS_W - tokens.SPACE_3)

    def freeze(self, to_end, to_start) -> None:
        """Take the before and after pictures (`to_end` / `to_start` resize the list), then show them."""
        before, seam_before, w_before = self._shot(), self._seam(), self.viewport().width()
        to_end()
        after, seam_after, w_after = self._shot(), self._seam(), self.viewport().width()
        to_start()
        wide = (before, seam_before) if w_before >= w_after else (after, seam_after)
        self._slide = (wide[0], wide[1], after, seam_after, w_after - seam_after)
        self.viewport().update()

    def thaw(self) -> None:
        self._slide = None
        self.viewport().update()

    def paintEvent(self, e):
        if self._lift is not None:
            self._lift.paint()
            return None
        if self._slide is None:
            return super().paintEvent(e)
        left, left_seam, right, right_seam, right_w = self._slide
        vp = self.viewport()
        h = vp.height()
        cut = vp.width() - right_w
        p = QPainter(vp)
        lw = max(0, min(cut, left_seam))
        if lw:
            d = left.devicePixelRatio()
            p.drawPixmap(QRectF(0, 0, lw, h), left, QRectF(0, 0, lw * d, h * d))
        if right_w > 0:
            d = right.devicePixelRatio()
            p.drawPixmap(QRectF(cut, 0, right_w, h), right, QRectF(right_seam * d, 0, right_w * d, h * d))
        p.end()
