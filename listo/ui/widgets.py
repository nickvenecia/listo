"""Small reusable widgets."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)


def section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setObjectName("SectionLabel")
    return lbl


def hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Hint")
    lbl.setWordWrap(True)
    return lbl


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
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
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


class Option(QFrame):
    clicked = Signal(str)

    def __init__(self, key: str, title: str, subtitle: str = "", parent: QWidget | None = None,
                 right: str = "", tip: str = ""):
        super().__init__(parent)
        self.key = key
        self._tip = tip
        self.setObjectName("Option")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tip)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(11, 7, 11, 7)
        outer.setSpacing(8)
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.title = QLabel(title)
        self.title.setObjectName("OptionTitle")
        lay.addWidget(self.title)
        self.sub = QLabel(subtitle)
        self.sub.setObjectName("OptionSub")
        self.sub.setWordWrap(True)
        self.sub.setVisible(bool(subtitle))
        lay.addWidget(self.sub)
        outer.addLayout(lay, 1)
        self.right = QLabel(right)
        self.right.setObjectName("OptionSub")
        self.right.setVisible(bool(right))
        outer.addWidget(self.right, 0, Qt.AlignmentFlag.AlignVCenter)
        self._enabled = True

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", "true" if on else "false")
        repolish(self)

    def set_available(self, on: bool, why: str = "") -> None:
        self._enabled = on
        self.setProperty("enabled", "true" if on else "false")
        self.title.setStyleSheet("" if on else "color: #6E6A64;")
        self.sub.setStyleSheet("" if on else "color: #55524D;")
        self.right.setStyleSheet("" if on else "color: #55524D;")
        self.setToolTip(self._tip if on else why)
        self.setCursor(Qt.CursorShape.PointingHandCursor if on else Qt.CursorShape.ArrowCursor)
        repolish(self)

    def mousePressEvent(self, e):  # noqa: N802
        if self._enabled and e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)


class OptionList(QWidget):
    """Vertical list of selectable cards (title + subtitle)."""

    changed = Signal(str)

    def __init__(self, items: list[tuple], parent: QWidget | None = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.options: dict[str, Option] = {}
        for item in items:
            key, title, sub = item[0], item[1], item[2]
            right = item[3] if len(item) > 3 else ""
            tip = item[4] if len(item) > 4 else ""
            if key.startswith("#"):  # group header
                lbl = QLabel(title)
                lbl.setObjectName("GroupLabel")
                lay.addSpacing(4 if self.options else 0)
                lay.addWidget(lbl)
                continue
            o = Option(key, title, sub, right=right, tip=tip)
            o.clicked.connect(self._pick)
            lay.addWidget(o)
            self.options[key] = o
        self._value = ""

    def _pick(self, key: str) -> None:
        if key != self._value:
            self.set_value(key)
            self.changed.emit(key)

    def set_value(self, key: str) -> None:
        self._value = key
        for k, o in self.options.items():
            o.set_selected(k == key)

    def value(self) -> str:
        return self._value


class FlowLayout(QLayout):
    """Wraps children onto new lines (used for naming tokens)."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):  # noqa: N802
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, w):  # noqa: N802
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, r):  # noqa: N802
        super().setGeometry(r)
        self._do(r, False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
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
