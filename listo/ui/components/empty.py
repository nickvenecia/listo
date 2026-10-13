"""What shows where the list would be before any files are in: the ways to start, as tiles (files, a folder,
a link). Files dragged anywhere on the window light the files tile."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QWidget

from listo.ui.components.widgets import IconLabel, hbox, repolish, vbox
from listo.ui.style import theme, tokens


class StartTile(QFrame):
    """One way to start: an icon, what it is, a few words. A click, Space or Return picks it."""

    clicked = Signal()

    def __init__(self, icon: str, title: str, detail: str, tip: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("StartTile")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(tokens.START_TILE_W)
        if tip:
            self.setToolTip(theme.plain_tip(tip))
        lay = vbox(self, (tokens.SPACE_4, tokens.SPACE_5, tokens.SPACE_4, tokens.SPACE_5), tokens.SPACE_1)
        badge = QFrame()  # the icon, in a circle of the accent's tint
        badge.setObjectName("StartBadge")
        badge.setFixedSize(tokens.START_BADGE, tokens.START_BADGE)
        bl = vbox(badge)
        bl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(IconLabel(icon, "ACCENT", tokens.ICON_LG))
        lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(tokens.SPACE_2)
        name = QLabel(title)
        name.setObjectName("StartTitle")
        sub = QLabel(detail)
        sub.setObjectName("StartDetail")
        for w in (name, sub):
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            w.setWordWrap(True)  # the tile is a fixed width: longer words take another line
            lay.addWidget(w)
        lay.addStretch(1)  # a tile made taller by its neighbour keeps its words on top, level with theirs

    def set_hot(self, on: bool) -> None:
        """Lit while files are dragged over the window."""
        if self.property("hot") is not on:
            self.setProperty("hot", on)
            repolish(self)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            e.accept()  # the release comes back here
        else:
            super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
            return
        super().keyPressEvent(e)


class EmptyPage(QWidget):
    """The empty list: a row of start tiles, centred a little above the middle. The first tile is the one that
    lights up while files are dragged in (`set_hot`)."""

    def __init__(self, tiles: tuple[tuple[str, str, str, str, Callable], ...], parent: QWidget | None = None):
        super().__init__(parent)
        self.tiles: list[StartTile] = []
        lay = vbox(self, tokens.SPACE_5, 0)
        lay.addStretch(2)
        row = hbox(spacing=tokens.SPACE_3)
        row.addStretch(1)
        for icon, title, detail, tip, slot in tiles:
            tile = StartTile(icon, title, detail, tip)
            tile.clicked.connect(slot)
            row.addWidget(tile)
            self.tiles.append(tile)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(3)

    def set_hot(self, on: bool) -> None:
        if self.tiles:
            self.tiles[0].set_hot(on)
