"""Small reusable widgets."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from . import theme, tokens


def section_label(text: str) -> QLabel:
    """The small Title Case label above a group of controls."""
    lbl = QLabel(text)
    lbl.setObjectName("SectionLabel")
    return lbl


def hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Hint")
    lbl.setWordWrap(True)
    return lbl


def vbox(
    widget: QWidget | None = None, margins: int | tuple[int, int, int, int] = 0, spacing: int = tokens.SPACE_2
) -> QVBoxLayout:
    """A vertical layout using the spacing tokens (never type raw numbers in layouts)."""
    lay = QVBoxLayout(widget) if widget is not None else QVBoxLayout()
    m = (margins,) * 4 if isinstance(margins, int) else margins
    lay.setContentsMargins(*m)
    lay.setSpacing(spacing)
    return lay


def hbox(
    widget: QWidget | None = None, margins: int | tuple[int, int, int, int] = 0, spacing: int = tokens.SPACE_2
) -> QHBoxLayout:
    """A horizontal layout using the spacing tokens."""
    lay = QHBoxLayout(widget) if widget is not None else QHBoxLayout()
    m = (margins,) * 4 if isinstance(margins, int) else margins
    lay.setContentsMargins(*m)
    lay.setSpacing(spacing)
    return lay


class Section(QWidget):
    """A labelled group: a small Title Case label, then its controls SPACE_1 below it.

    Put Sections in a layout with spacing SPACE_3 and every panel lines up the same way.
    Hiding a Section hides its label and controls together (and the gap collapses).
    """

    def __init__(self, title: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.lay = vbox(self, 0, tokens.SPACE_1)
        self.label = section_label(title)
        self.label.setVisible(bool(title))
        self.lay.addWidget(self.label)

    def add(self, item: QWidget | QHBoxLayout | QVBoxLayout) -> None:
        if isinstance(item, QWidget):
            self.lay.addWidget(item)
        else:
            self.lay.addLayout(item)

    def set_title(self, title: str) -> None:
        self.label.setText(title)
        self.label.setVisible(bool(title))


class Disclosure(QWidget):
    """A fold-away group ("Advanced options"): a header row that opens and closes the controls under it.

    The header can show a short summary (e.g. "2 on") so changed settings are never hidden silently."""

    toggled = Signal(bool)

    def __init__(self, title: str, is_open: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._title = title
        self._summary = ""
        outer = vbox(self, 0, tokens.SPACE_3)
        self.header = QPushButton()
        self.header.setObjectName("Disclosure")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.clicked.connect(lambda: self.set_open(not self.body.isVisibleTo(self), emit=True))
        outer.addWidget(self.header)
        self.body = QWidget()
        self.lay = vbox(self.body, 0, tokens.SPACE_3)
        outer.addWidget(self.body)
        self.set_open(is_open)

    def add(self, w: QWidget) -> None:
        self.lay.addWidget(w)

    def is_open(self) -> bool:
        return self.body.isVisibleTo(self)

    def set_open(self, on: bool, emit: bool = False) -> None:
        self.body.setVisible(on)
        self.header.setIcon(theme.icon("chevron" if on else "chevron-right", "MUTED"))
        self.header.setToolTip("Hide" if on else "Show more settings")
        if emit:
            self.toggled.emit(on)

    def set_summary(self, text: str) -> None:
        self._summary = text
        self.header.setText(f" {self._title}" + (f"  ·  {text}" if text else ""))


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


class Segmented(QFrame):
    """Tabs: a row of mutually exclusive buttons that switch which page you see (styled as tabs in
    theme.py, so they never look like a setting)."""

    changed = Signal(str)

    def __init__(self, items: list[tuple[str, str]], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Seg")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for key, label in items:
            b = QPushButton(label)
            b.setObjectName("SegBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(b)
            lay.addWidget(b)
            self.buttons[key] = b

    def set_value(self, key: str) -> None:
        if key in self.buttons:
            self.buttons[key].setChecked(True)

    def value(self) -> str:
        for k, b in self.buttons.items():
            if b.isChecked():
                return k
        return ""


class FlowLayout(QLayout):
    """Wraps children onto new lines (used for naming tokens)."""

    def __init__(self, parent: QWidget | None = None, spacing: int = tokens.SPACE_2):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, r):
        super().setGeometry(r)
        self._do(r, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _do(self, r: QRect, test: bool) -> int:
        x, y, line_h = r.x(), r.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            nx = x + hint.width() + self._spacing
            if nx - self._spacing > r.right() and line_h > 0:
                x, y = r.x(), y + line_h + self._spacing
                nx, line_h = x + hint.width() + self._spacing, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x, line_h = nx, max(line_h, hint.height())
        return y + line_h - r.y()


class Toast(QLabel):
    """A short message that floats at the bottom of its parent and fades away."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setWordWrap(True)
        self.hide()
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.timeout.connect(self.hide)

    def show_message(self, text: str, ms: int = 3500) -> None:
        self.setText(text)
        self.setMaximumWidth(min(520, self.parentWidget().width() - 40))
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 20)
        self.raise_()
        self.show()
        self._t.start(ms)


# ------------------------------------------------------------------ dropdowns
def combo(items: list[tuple[str, str, str]], current: str) -> QComboBox:
    """The standard dropdown. items: (key, label, tooltip); the key is the item's data."""
    c = QComboBox()
    for key, label, tip in items:
        c.addItem(label, key)
        if tip:
            c.setItemData(c.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
    c.setCurrentIndex(max(0, c.findData(current)))
    c.setCursor(Qt.CursorShape.PointingHandCursor)
    return c


CHOOSE = "__choose__"  # data of the "Choose …" item at the bottom of a PathCombo
RECENT_PATHS = 8  # how many picked files / folders a PathCombo remembers


class PathCombo(QComboBox):
    """The one way Listo picks a file or folder (DESIGN.md §6, like the LUT dropdown): the fixed
    choices first, then the files / folders picked before (most recent first; the name, with the
    full path in the tip; ones that are gone drop off), then "Choose …", which opens the system
    picker. `picked` gives the fixed key or the path, only when the choice changes."""

    picked = Signal(str)

    def __init__(
        self,
        qs: QSettings,
        store: str,
        fixed: list[tuple[str, str, str]],
        choose: str,
        ask: Callable[[str], str],
        folders: bool = False,
    ):
        """store: the QSettings key of the remembered paths. ask(start) shows the system picker
        and returns the path (or "" when cancelled)."""
        super().__init__()
        self.qs, self.store, self.fixed, self.choose, self.ask, self.folders = (
            qs,
            store,
            fixed,
            choose,
            ask,
            folders,
        )
        self.value = fixed[0][0] if fixed else ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.activated.connect(self._activated)
        self.set_value(self.value)

    def recent(self) -> list[str]:
        try:
            data = json.loads(self.qs.value(self.store, "[]") or "[]")
        except (ValueError, TypeError):
            data = []
        there = Path.is_dir if self.folders else Path.is_file
        return [p for p in data if isinstance(p, str) and p and there(Path(p))]

    def remember(self, path: str) -> None:
        paths = [path] + [p for p in self.recent() if p != path]
        self.qs.setValue(self.store, json.dumps(paths[:RECENT_PATHS]))

    def _name(self, path: str) -> str:
        p = Path(path)
        return (p.name if self.folders else p.stem) or path

    def set_value(self, value: str) -> None:
        """Show this fixed key or path as the choice (a path not in the list yet is added to it)."""
        self.value = value
        paths = self.recent()
        if value and value not in paths and all(value != k for k, _, _ in self.fixed):
            paths.insert(0, value)  # e.g. a folder on a drive that isn't plugged in: still the setting
        names = [self._name(p) for p in paths]
        self.blockSignals(True)
        self.clear()
        for key, label, tip in self.fixed:
            self.addItem(label, key)
            if tip:
                self.setItemData(self.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        if paths:
            self.insertSeparator(self.count())
        for p, name in zip(paths, names, strict=True):
            if names.count(name) > 1:
                name = f"{name} ({Path(p).parent.name})"  # two with the same name: say where each is
            self.addItem(name, p)
            self.setItemData(self.count() - 1, p, Qt.ItemDataRole.ToolTipRole)
        self.insertSeparator(self.count())
        self.addItem(self.choose, CHOOSE)
        self.setCurrentIndex(max(0, self.findData(value)))
        self.blockSignals(False)

    def _activated(self, index: int) -> None:
        data = self.itemData(index)
        if data == CHOOSE:
            start = self.value if self.value and Path(self.value).exists() else str(Path.home())
            if Path(start).is_file():
                start = str(Path(start).parent)
            data = self.ask(start)
            if not data:
                self.set_value(self.value)  # cancelled: back to what it was
                return
        if data is None:
            return
        if data and all(data != k for k, _, _ in self.fixed):
            self.remember(data)
        changed = data != self.value
        self.set_value(data)
        if changed:
            self.picked.emit(data)


def set_combo(c: QComboBox, key: str) -> None:
    """Select the item with this key without firing change signals."""
    c.blockSignals(True)
    c.setCurrentIndex(max(0, c.findData(key)))
    c.blockSignals(False)


def disable_item(c: QComboBox, key: str, why: str) -> None:
    """Grey out one item and say why in its tooltip."""
    i = c.findData(key)
    item = c.model().item(i) if i >= 0 and hasattr(c.model(), "item") else None
    if item is not None:
        item.setEnabled(False)
        item.setToolTip(why)


class ComboItemDelegate(QStyledItemDelegate):
    """Draws dropdown rows: rounded highlight from the stylesheet, standard row height,
    and a thin line for separators (Qt's default painter ignores the stylesheet on macOS)."""

    ROW_H = tokens.CONTROL_H - tokens.SPACE_2
    SEP_H = tokens.SPACE_2 + 1

    @staticmethod
    def _is_separator(index) -> bool:
        return index.data(Qt.ItemDataRole.AccessibleDescriptionRole) == "separator"

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(self.SEP_H if self._is_separator(index) else max(size.height(), self.ROW_H))
        return size

    def paint(self, painter, option, index):
        if self._is_separator(index):
            y = option.rect.center().y()
            painter.save()
            painter.setPen(QColor(tokens.BORDER_STRONG))
            painter.drawLine(option.rect.left() + tokens.SPACE_2, y, option.rect.right() - tokens.SPACE_2, y)
            painter.restore()
            return
        super().paint(painter, option, index)


class FitScroll(QScrollArea):
    """Scroll area whose content always matches the visible width (no clipped edges).

    The scroll bar's space is always reserved (it's invisible while there's nothing to scroll), so
    content never shifts or squeezes when a group opens. Put SCROLL_GUTTER less margin on the
    right of the content so both sides look the same."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        bar = self.verticalScrollBar()
        bar.setEnabled(False)
        bar.rangeChanged.connect(lambda lo, hi: bar.setEnabled(hi > lo))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.widget():
            self.widget().setFixedWidth(self.viewport().width())


class ClickLabel(QLabel):
    """A label you can click (the live preview)."""

    clicked = Signal()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class StepHeader(QFrame):
    """The top of each panel: a numbered step and its name ("1 Files", "2 Convert To", "3 Export").
    All three are the same height so the panels line up; `.actions` takes buttons on the right."""

    def __init__(self, number: int, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("StepHeader")
        self.setFixedHeight(tokens.HEADER_H)
        lay = hbox(self, (tokens.SPACE_4, 0, tokens.SPACE_4, 0), tokens.SPACE_2)
        badge = QLabel(str(number))
        badge.setObjectName("StepBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(tokens.STEP_BADGE, tokens.STEP_BADGE)
        name = QLabel(title)
        name.setObjectName("StepTitle")
        lay.addWidget(badge)
        lay.addWidget(name)
        lay.addStretch(1)
        self.actions = hbox(spacing=tokens.SPACE_2)
        lay.addLayout(self.actions)


class ToggleRow(QAbstractButton):
    """An on/off setting: the label on the left, a switch on the right, the whole row clickable.
    Works like a QCheckBox (setChecked, isChecked, toggled, text)."""

    def __init__(self, text: str, checked: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(tokens.TOGGLE_ROW_H)
        self._hover = False

    def sizeHint(self) -> QSize:
        w = self.fontMetrics().horizontalAdvance(self.text()) + tokens.SPACE_3 + tokens.TOGGLE_W
        return QSize(w, tokens.TOGGLE_ROW_H)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on, enabled = self.isChecked(), self.isEnabled()
        r = self.rect()
        # label
        p.setPen(QColor(tokens.TEXT if enabled else tokens.FAINT))
        text_rect = r.adjusted(0, 0, -(tokens.TOGGLE_W + tokens.SPACE_3), 0)
        label = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, text_rect.width())
        p.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), label)
        # switch
        tw, th = tokens.TOGGLE_W, tokens.TOGGLE_H
        track = QRectF(r.right() - tw + 1, r.center().y() - th / 2 + 1, tw - 1, th - 1)
        if on:
            fill = tokens.ACCENT_HOVER if self._hover and enabled else tokens.ACCENT
        else:
            fill = tokens.TRACK_HOVER if self._hover and enabled else tokens.TRACK
        if not enabled:
            fill = tokens.ACCENT_OFF if on else tokens.BORDER
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(fill))
        p.drawRoundedRect(track, th / 2, th / 2)
        knob = th - 2 * tokens.TOGGLE_INSET
        x = track.right() - tokens.TOGGLE_INSET - knob if on else track.left() + tokens.TOGGLE_INSET
        p.setBrush(QColor(tokens.ON_ACCENT if on else tokens.KNOB) if enabled else QColor(tokens.FAINT))
        p.drawEllipse(QRectF(x, track.top() + tokens.TOGGLE_INSET, knob, knob))
        p.end()
