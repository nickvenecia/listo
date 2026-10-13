"""Small reusable widgets."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from listo.core.store import Prefs, loads
from listo.ui.style import theme, tokens


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


class ElidedLabel(QLabel):
    """A one-line label that cuts long text short with "…" instead of widening its panel (at the end, or
    `mode` ElideMiddle / ElideLeft for file names and paths)."""

    def __init__(
        self,
        text: str = "",
        mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._full = ""
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        if text == self._full and self.text():
            return
        self._full = text
        self.setToolTip("")
        self._elide()
        self.updateGeometry()  # its room in the layout follows the new text

    def _elide(self) -> None:
        shown = self.fontMetrics().elidedText(self._full, self._mode, max(1, self.width()))
        self.setText(shown)
        self.setToolTip(theme.plain_tip(self._full) if shown != self._full else "")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def sizeHint(self) -> QSize:  # as wide as the whole text, when there's room
        return QSize(self.fontMetrics().horizontalAdvance(self._full) + 2, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # …but it gives way to everything else first
        return QSize(0, super().minimumSizeHint().height())


class _FoldHeader(QPushButton):
    """The Disclosure's header: its text is cut short with "…" rather than widening the panel."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def set_full_text(self, text: str) -> None:
        self._full = text
        self._elide()

    def _elide(self) -> None:
        room = self.width() - self.iconSize().width() - tokens.SPACE_3
        self.setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, max(1, room)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()


class Card(QFrame):
    """A titled group in the right panel: a soft tinted card (the look every panel's groups share)."""

    def __init__(self, title: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.outer = vbox(self, tokens.SPACE_3, tokens.SPACE_2)
        self.head = hbox(spacing=tokens.SPACE_2)
        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        self.title.setVisible(bool(title))
        self.head.addWidget(self.title, 1)
        self.outer.addLayout(self.head)
        self.lay = vbox(spacing=tokens.SPACE_3)
        self.outer.addLayout(self.lay)

    def add(self, item: QWidget | QHBoxLayout | QVBoxLayout) -> None:
        if isinstance(item, QWidget):
            self.lay.addWidget(item)
        else:
            self.lay.addLayout(item)


class Disclosure(QFrame):
    """A fold-away group (Image, Burn-In, Encoding): a card whose header opens and closes the controls under it.

    Folded, the header says what's changed inside ("Burn-In · 2 changed"), so a changed setting is never
    hidden silently."""

    toggled = Signal(bool)

    def __init__(self, title: str, is_open: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._title = title
        self._summary = ""
        self.setObjectName("Card")  # looks like every other group in a panel
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = vbox(self, tokens.SPACE_3, tokens.SPACE_2)
        self.header = _FoldHeader()
        self.header.setObjectName("Disclosure")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.clicked.connect(lambda: self.set_open(not self.body.isVisibleTo(self), emit=True))
        outer.addWidget(self.header)
        self.body = QWidget()
        self.lay = vbox(self.body, 0, tokens.SPACE_3)
        outer.addWidget(self.body)
        self.set_open(is_open)

    def add(self, item: QWidget | QHBoxLayout | QVBoxLayout) -> None:
        if isinstance(item, QWidget):
            self.lay.addWidget(item)
        else:
            self.lay.addLayout(item)

    def is_open(self) -> bool:
        return self.body.isVisibleTo(self)

    def set_open(self, on: bool, emit: bool = False) -> None:
        self.body.setVisible(on)
        self.header.setIcon(theme.icon("chevron" if on else "chevron-right", theme.MUTED))
        self.header.setToolTip("Hide" if on else "Show")
        self._show_title()
        if emit:
            self.toggled.emit(on)

    def set_summary(self, text: str) -> None:
        self._summary = text.replace("&", "&&")  # a lone & would underline the next letter instead
        self._show_title()

    def _show_title(self) -> None:
        self.header.set_full_text(f" {self._title}" + (f"  ·  {self._summary}" if self._summary else ""))


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


class AccentPicker(QWidget):
    """A row of color circles (tokens.ACCENTS), the chosen one ringed. Click, or the arrow keys."""

    picked = Signal(str)

    def __init__(self, current: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.keys = list(tokens.ACCENTS)
        self.current = current if current in tokens.ACCENTS else tokens.APP_ACCENT
        self._hover = ""
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(tokens.CONTROL_H)
        self.setMinimumWidth(self._pitch() * len(self.keys))

    @staticmethod
    def _pitch() -> int:
        return tokens.SWATCH + 2 * tokens.SWATCH_RING * 2 + tokens.SPACE_1

    def _rect(self, i: int) -> QRectF:
        outer = tokens.SWATCH + 4 * tokens.SWATCH_RING
        y = (self.height() - outer) / 2
        return QRectF(i * self._pitch(), y, outer, outer)

    def _key_at(self, pos) -> str:
        for i, k in enumerate(self.keys):
            if self._rect(i).contains(pos):
                return k
        return ""

    def set_value(self, key: str) -> None:
        self.current = key if key in tokens.ACCENTS else tokens.APP_ACCENT
        self.update()

    def _pick(self, key: str) -> None:
        if key and key != self.current:
            self.current = key
            self.update()
            self.picked.emit(key)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = tokens.SWATCH_RING
        for i, k in enumerate(self.keys):
            r = self._rect(i)
            dot = r.adjusted(2 * ring, 2 * ring, -2 * ring, -2 * ring)
            if k == self.current or k == self._hover:
                pen = QPen(theme.qcolor(tokens.TEXT if k == self.current else tokens.BORDER_HOVER))
                pen.setWidthF(ring)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(r.adjusted(ring / 2, ring / 2, -ring / 2, -ring / 2))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor(tokens.accent_of(k)))
            p.drawEllipse(dot)
        if self.hasFocus():
            pen = QPen(theme.qcolor(tokens.ACCENT_EDGE))
            pen.setWidthF(1)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(self._rect(self.keys.index(self.current)))

    def mouseMoveEvent(self, e) -> None:
        k = self._key_at(e.position())
        if k != self._hover:
            self._hover = k
            self.update()
        name = tokens.ACCENTS[k][0] if k else ""
        if k == tokens.APP_ACCENT:
            name += " (Listo's own)"
        self.setToolTip(name)

    def leaveEvent(self, _e) -> None:
        self._hover = ""
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._pick(self._key_at(e.position()))

    def keyPressEvent(self, e) -> None:
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}.get(e.key())
        if step is None:
            super().keyPressEvent(e)
            return
        i = (self.keys.index(self.current) + step) % len(self.keys)
        self._pick(self.keys[i])


class Segmented(QFrame):
    """A row of mutually exclusive buttons (Video / Photo / Audio, Converted / Original)."""

    changed = Signal(str)

    def __init__(self, items: list[tuple[str, str]], compact: bool = False, parent: QWidget | None = None):
        """`compact`: each button as wide as its word, instead of sharing the full width."""
        super().__init__(parent)
        self.setObjectName("Seg")
        self.setFixedHeight(tokens.CONTROL_H)
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
            b.setSizePolicy(
                QSizePolicy.Policy.Preferred if compact else QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
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

    def show_message(self, text: str, ms: int = tokens.TOAST_MS) -> None:
        self.setText(text)
        self.setMaximumWidth(min(tokens.TOAST_MAX_W, self.parentWidget().width() - 2 * tokens.SPACE_5))
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - tokens.SPACE_5)
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
        qs: Prefs,
        store: str,
        fixed: list[tuple[str, str, str]],
        choose: str,
        ask: Callable[[str], str],
        folders: bool = False,
    ):
        """store: the settings.json key of the remembered paths. ask(start) shows the system picker
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
        data = loads(self.qs.value(self.store, []), [])
        there = Path.is_dir if self.folders else Path.is_file
        return [p for p in data if isinstance(p, str) and p and there(Path(p))]

    def remember(self, path: str) -> None:
        paths = [path] + [p for p in self.recent() if p != path]
        self.qs.setValue(self.store, paths[:RECENT_PATHS])

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

    ROW_H = tokens.LIST_ROW_H + tokens.LIST_GAP
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


class SearchField(QLineEdit):
    """The toolbar's search: asks for SEARCH_W, gives way down to SEARCH_MIN on a narrow window."""

    def sizeHint(self) -> QSize:
        return QSize(tokens.SEARCH_W, super().sizeHint().height())


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


class PanelHeader(QFrame):
    """The top of each panel, the same height everywhere so the panels line up.

    It says what the panel holds ("Convert To"); `.actions` takes round buttons before the ✕."""

    def __init__(self, title: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PanelHeader")
        self.setFixedHeight(tokens.TOOLBAR_H)  # level with the list's toolbar
        lay = hbox(self, (tokens.SPACE_4, 0, tokens.SPACE_4, 0), tokens.SPACE_2)
        self.title = ElidedLabel(title)
        self.title.setObjectName("PanelTitle")
        self.title.setVisible(bool(title))
        lay.addWidget(self.title, 1)
        self.actions = hbox(spacing=tokens.SPACE_2)
        lay.addLayout(self.actions)

    def add_close(self, tip: str = "Close") -> QToolButton:
        """The round ✕, at the far right (after any other buttons)."""
        b = circle_button("x", tip)
        self.layout().addWidget(b)
        return b


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
            fill = tokens.BORDER_HOVER if self._hover and enabled else tokens.BORDER_STRONG
        if not enabled:
            fill = tokens.ACCENT_OFF if on else tokens.BORDER
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(fill))
        p.drawRoundedRect(track, th / 2, th / 2)
        knob = th - 2 * tokens.TOGGLE_INSET
        x = track.right() - tokens.TOGGLE_INSET - knob if on else track.left() + tokens.TOGGLE_INSET
        p.setBrush(QColor(tokens.ON_ACCENT if on else tokens.TEXT) if enabled else QColor(tokens.FAINT))
        p.drawEllipse(QRectF(x, track.top() + tokens.TOGGLE_INSET, knob, knob))
        p.end()


class TextBox(QPlainTextEdit):
    """A multi-line text field that looks like the one-line fields.
    `edited` fires on typing only, never when the window fills it in with set_text()."""

    edited = Signal()

    def __init__(self, placeholder: str = "", height: int = tokens.TEXT_BOX_H, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Field")
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(height)
        self.setTabChangesFocus(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._quiet = False
        self.textChanged.connect(self._changed)

    def _changed(self) -> None:
        if not self._quiet:
            self.edited.emit()

    def text(self) -> str:
        return self.toPlainText()


def button_row() -> QHBoxLayout:
    """The row of buttons at the bottom of a dialog: right-aligned (add the main one last), SPACE_4 below
    the content in every dialog (dialogs lay out with SPACE_3 between rows)."""
    row = hbox(spacing=tokens.SPACE_2)
    row.setContentsMargins(0, tokens.SPACE_4 - tokens.SPACE_3, 0, 0)
    row.addStretch(1)
    return row


class IconLabel(QLabel):
    """A small icon that isn't a button. `tone` names a theme color ("MUTED", "ACCENT", "BAD"…); it redraws
    itself when the look changes between light and dark."""

    def __init__(
        self,
        name: str = "",
        tone: str = "MUTED",
        size: int = tokens.ICON_SM,
        stroke: float = tokens.ICON_STROKE,
        parent=None,
    ):
        super().__init__(parent)
        self._name, self._tone, self._size, self._stroke = name, tone, size, stroke
        self.setFixedSize(size, size)
        self._draw()

    def set_icon(self, name: str, tone: str = "") -> None:
        if name != self._name or (tone and tone != self._tone):
            self._name, self._tone = name, tone or self._tone
            self._draw()

    def _draw(self) -> None:
        if self._name:
            self.setPixmap(theme.pixmap(self._name, self._size, getattr(tokens, self._tone), self._stroke))
        else:
            self.clear()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.StyleChange:  # the app's stylesheet changed: light, dark or the accent
            self._draw()


def circle_button(name: str, tip: str, color: str = "") -> QToolButton:
    """The standard icon button: a round, raised button the height of every control (toolbars, panel
    headers, ‹ › arrows). Always has a tooltip."""
    b = QToolButton()
    b.setObjectName("Circle")
    b.setIcon(theme.icon(name, color or theme.MUTED))
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def icon_button(name: str, tip: str, color: str = "", size: int = tokens.ICON_SM) -> QToolButton:
    """A small icon button (the player's play and ‹ ›): round, no frame until you point at it.
    Always has a tooltip. Without a `color` it's the muted grey of the look in use; "" = set the icon later."""
    b = QToolButton()
    b.setObjectName("IconBtn")
    if name:
        b.setIcon(theme.icon(name, color or theme.MUTED, size))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class FlowLayout(QLayout):
    """Lays widgets out left to right and wraps to the next line when the row is full (naming tokens)."""

    def __init__(self, parent: QWidget | None = None, spacing: int = tokens.SPACE_2):
        super().__init__(parent)
        self._items: list = []
        self._space = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._lay(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._lay(rect, apply=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        return size

    def _lay(self, rect, apply: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        for it in self._items:
            if it.widget() is not None and not it.widget().isVisibleTo(it.widget().parentWidget()):
                continue
            hint = it.sizeHint()
            if x + hint.width() > rect.right() + 1 and line > 0:
                x, y, line = rect.x(), y + line + self._space, 0
            if apply:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._space
            line = max(line, hint.height())
        return y + line - rect.y()
