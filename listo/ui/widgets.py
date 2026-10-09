"""Small reusable widgets."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
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
        self.header.setIcon(theme.icon("chevron" if on else "chevron-right", theme.MUTED))
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
    """A row of mutually exclusive buttons."""

    changed = Signal(str)

    def __init__(self, items: list[tuple[str, str]], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Seg")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(*(tokens.SEG_INSET,) * 4)
        lay.setSpacing(tokens.SEG_INSET)
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
    """Scroll area whose content always matches the visible width (no clipped edges)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

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
