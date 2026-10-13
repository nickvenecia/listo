"""The app's two panel kinds, so every one of each looks and behaves the same:

LeftPanel   every list of places on the left (the main sidebar, Settings' sections): floating glass, rows
            (NavRow) inset NAV_INSET from its edges so their corners curve with the glass, an optional top
            (the wordmark), a list that scrolls, an optional foot (the profile card)
SidePanel   every panel on the right (Convert To): the same header everywhere (title, your own round buttons,
            then the round ✕ at the far right) and a body that scrolls

Subclass them; change what's inside, never the frame.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QToolButton, QWidget

from listo.ui.components.glass import glass
from listo.ui.components.widgets import (
    FitScroll,
    IconLabel,
    PanelHeader,
    circle_button,
    hbox,
    repolish,
    vbox,
)
from listo.ui.style import theme, tokens


class NavRow(QFrame):
    """One place in a LeftPanel: an icon, a name, a count; an arrow when rows fold under it."""

    clicked = Signal(str)
    fold_wanted = Signal(str)  # its arrow (rows with rows under them)
    menu_wanted = Signal(str, QPoint)

    def __init__(
        self, key: str, label: str, icon: str = "", parent: QWidget | None = None, foldable: bool = True
    ):
        """`foldable=False`: a plain list row (Settings) with no room kept for a fold arrow."""
        super().__init__(parent)
        self.key = key
        self.setObjectName("Nav")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(tokens.NAV_H)
        lay = hbox(
            self, (tokens.SPACE_1 if foldable else tokens.SPACE_2, 0, tokens.SPACE_2, 0), tokens.SPACE_1
        )
        self.arrow = QToolButton()  # shown on rows with rows under them; keeps its room on the others
        self.arrow.setObjectName("NavArrow")
        self.arrow.setFixedSize(tokens.ICON_SM + tokens.SPACE_1, tokens.ICON_SM + tokens.SPACE_1)
        self.arrow.setCursor(Qt.CursorShape.PointingHandCursor)
        self.arrow.clicked.connect(lambda: self.fold_wanted.emit(self.key))
        keep = self.arrow.sizePolicy()
        keep.setRetainSizeWhenHidden(True)
        self.arrow.setSizePolicy(keep)
        self.arrow.hide()
        self.folded = False
        if foldable:
            lay.addWidget(self.arrow)
        else:
            lay.setSpacing(tokens.SPACE_2)
        self.icon = IconLabel(icon, "MUTED", tokens.ICON)
        self.recolor()
        self.icon.setFixedWidth(tokens.ICON)
        self.label = QLabel(label)
        self.label.setObjectName("NavLabel")
        self.count = QLabel()
        self.count.setObjectName("NavCount")
        lay.addWidget(self.icon)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.count)

    def recolor(self) -> None:
        self.arrow.setIcon(
            theme.icon("chevron-right" if self.folded else "chevron", theme.FAINT, tokens.ICON_SM)
        )

    def set_folded(self, on: bool) -> None:
        self.folded = on
        self.recolor()

    def set_count(self, n: int | str, tone: str = "") -> None:
        text = str(n) if n not in (0, "") else ""
        if self.count.text() != text:
            self.count.setText(text)
        if self.count.property("tone") != tone:
            self.count.setProperty("tone", tone)
            repolish(self.count)

    def set_current(self, on: bool) -> None:
        self.setProperty("current", on)
        self.set_selected(on)

    def set_selected(self, on: bool) -> None:
        if bool(self.property("selected")) != on:
            self.setProperty("selected", on)
            repolish(self)
            repolish(self.label)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(e)

    def contextMenuEvent(self, e):
        self.menu_wanted.emit(self.key, e.globalPos())


class LeftPanel(QFrame):
    """A list of places on the left. `top_height`: room for a top (the wordmark); 0 for none."""

    def __init__(self, width: int, top_height: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        glass(self)
        self.setFixedWidth(width)
        self.rows: dict[str, NavRow] = {}
        outer = vbox(self, 0, 0)
        self.top = QWidget()
        self.top_lay = hbox(self.top, (tokens.SPACE_4, 0, tokens.SPACE_4, 0), 0)
        self.top.setFixedHeight(top_height)
        self.top.setVisible(top_height > 0)
        outer.addWidget(self.top)
        self.scroll = FitScroll()  # its scroll bar's room is the right-hand inset
        body = QWidget()
        inset = tokens.NAV_INSET
        self.lay = vbox(
            body, (inset, 0 if top_height else inset, inset - tokens.SCROLL_GUTTER, inset), tokens.NAV_GAP
        )
        self.scroll.setWidget(body)
        outer.addWidget(self.scroll, 1)
        self.foot = QFrame()
        self.foot.setObjectName("SidebarFoot")
        self.foot_lay = vbox(self.foot, inset, tokens.SPACE_2)
        self.foot.hide()
        outer.addWidget(self.foot)

    def add_row(self, key: str, label: str, icon: str = "", into=None, foldable: bool = True) -> NavRow:
        r = NavRow(key, label, icon, foldable=foldable)
        (into if into is not None else self.lay).addWidget(r)
        self.rows[key] = r
        return r

    def add_to_foot(self, w: QWidget) -> None:
        self.foot_lay.addWidget(w)
        self.foot.show()

    def select(self, key: str) -> None:
        for k, r in self.rows.items():
            r.set_current(k == key)

    def recolor(self) -> None:
        for r in self.rows.values():
            r.recolor()


class SidePanel(QFrame):
    """A panel on the right: the header, then a body that scrolls (`lay`)."""

    close_wanted = Signal()  # its round ✕

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Details")
        self.setFixedWidth(tokens.INSPECTOR_W)
        outer = vbox(self, 0, 0)
        self.header = PanelHeader(title)
        self.header.setFixedHeight(tokens.TOOLBAR_H)  # lines up with the list's toolbar
        self.close_btn = self.header.add_close()
        self.close_btn.clicked.connect(self.close_wanted.emit)
        outer.addWidget(self.header)
        body = QWidget()
        pad = tokens.SPACE_4
        self.lay = vbox(body, (pad, 0, pad - tokens.SCROLL_GUTTER, pad), tokens.SPACE_3)
        self.scroll = FitScroll()
        self.scroll.setWidget(body)
        outer.addWidget(self.scroll, 1)

    def header_icon(self, icon: str, tip: str) -> QToolButton:
        """A round button in the header, before the ✕."""
        b = circle_button(icon, tip)
        self.header.actions.insertWidget(0, b)
        return b
