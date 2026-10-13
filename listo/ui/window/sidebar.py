"""The sidebar: where you are in the list. Files (All Files, Videos, Photos, Audio) and Progress (To Convert,
Done, Need a Look), each with its count. Click a heading to fold its section; the + beside Files adds files,
a folder or a link. At the bottom: an update when there is one, and the profile card (Settings, feedback,
updates).
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSettings,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QLabel, QPushButton, QToolButton, QWidget

from listo.ui.components.panels import LeftPanel
from listo.ui.components.widgets import ElidedLabel, IconLabel, hbox, section_label, vbox
from listo.ui.style import theme, tokens

PLACES = {  # key -> (name, icon, section)
    "all": ("All Files", "file", "files"),
    "video": ("Videos", "film", "files"),
    "photo": ("Photos", "image", "files"),
    "audio": ("Audio", "audio", "files"),
    "todo": ("To Convert", "clock", "progress"),
    "done": ("Done", "check", "progress"),
    "attention": ("Need a Look", "alert", "progress"),
}
TODO = ("probing", "ready", "waiting", "converting", "paused", "downloading", "transcribing")
ATTENTION = ("failed", "warning", "unsupported", "canceled", "skipped")


def in_place(place: str, kind: str, state: str) -> bool:
    """Whether a file of this kind and state shows in this place."""
    if place in ("video", "photo", "audio"):
        return kind == place
    if place == "todo":
        return state in TODO
    if place == "done":
        return state == "done"
    if place == "attention":
        return state in ATTENTION
    return True


class SectionHead(QFrame):
    """A heading over a list in the sidebar. Click it to fold the list away (or bring it back)."""

    toggled = Signal(bool)  # folded

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("NavHead")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folded = False
        self.lay = hbox(
            self, (tokens.SPACE_2, tokens.SPACE_1, tokens.SPACE_1, tokens.SPACE_1), tokens.SPACE_1
        )
        self.label = section_label(text)
        self.chevron = IconLabel("chevron", "FAINT")
        self.lay.addWidget(self.label)
        self.lay.addWidget(self.chevron)
        self.lay.addStretch(1)
        self.setFixedHeight(tokens.NAV_H)
        self._draw()

    def _draw(self) -> None:
        self.chevron.set_icon("chevron-right" if self.folded else "chevron")

    def set_folded(self, on: bool) -> None:
        self.folded = on
        self._draw()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.set_folded(not self.folded)
            self.toggled.emit(self.folded)
        super().mousePressEvent(e)


class ProfileCard(QFrame):
    """The bottom of the sidebar: who's using this computer (their initials, their name). Click for Send
    Feedback, Check for Updates and Settings."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ProfileCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(tokens.PROFILE_CARD_H)
        lay = hbox(self, (tokens.SPACE_2, 0, tokens.SPACE_2, 0), tokens.SPACE_2)
        self.avatar = QLabel()
        self.avatar.setObjectName("Avatar")
        self.avatar.setFixedSize(tokens.AVATAR, tokens.AVATAR)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.avatar)
        texts = vbox(spacing=0)
        self.name = ElidedLabel()
        self.name.setObjectName("ProfileName")
        texts.addStretch(1)
        texts.addWidget(self.name)
        texts.addStretch(1)
        lay.addLayout(texts, 1)
        self.updown = IconLabel("updown", "FAINT")
        lay.addWidget(self.updown)
        self.setToolTip("Settings, Feedback and Updates")

    def show_who(self, name: str) -> None:
        words = [w for w in name.replace("&", " ").split() if w[:1].isalnum()]
        self.avatar.setText("".join(w[0] for w in words[:2]).upper() or "L")
        self.name.set_full_text(name)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


def computer_user() -> str:
    """The name of whoever is signed in to this computer ("Your Computer" if it can't tell)."""
    import getpass
    import sys

    try:
        user = getpass.getuser()
    except Exception:
        return "Your Computer"
    if sys.platform != "win32":
        try:
            import pwd

            full = pwd.getpwnam(user).pw_gecos.split(",")[0].strip()
            if full:
                return full
        except (KeyError, ImportError, OSError):
            pass  # no full name on file: the account name will do
    return user or "Your Computer"


class Sidebar(LeftPanel):
    picked = Signal(str)  # a key of PLACES

    def __init__(self, parent: QWidget | None = None):
        super().__init__(tokens.SIDEBAR_W, tokens.TOOLBAR_H, parent)
        self.qs = QSettings("Listo", "Listo")
        self.current = "all"
        self.word = word = QLabel(theme.wordmark())
        word.setObjectName("Wordmark")
        word.setTextFormat(Qt.TextFormat.RichText)
        word.setToolTip("Drop it in. Get it back edit-ready.")
        self.top_lay.addWidget(word)

        self.heads: dict[str, SectionHead] = {}
        self.boxes: dict[str, QWidget] = {}
        self.btn_add = self._plus("Add Files, a Folder or a Link")
        files = self._section("files", "Files", self.btn_add)
        progress = self._section("progress", "Progress")
        for key, (label, icon, section) in PLACES.items():
            r = self.add_row(key, label, icon, files if section == "files" else progress, foldable=False)
            r.clicked.connect(self.pick)
        self.lay.addStretch(1)
        folded = self.qs.value("sidebar_folded", "", type=str) or ""
        for key in [k for k in folded.split(",") if k in self.heads]:
            self._show_fold(key, True)

        self.btn_update = QPushButton()
        self.btn_update.setObjectName("Ghost")
        self.btn_update.setIcon(theme.icon("arrow-down", theme.ACCENT))
        self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update.setToolTip("A newer Listo is out. See what's new and update")
        self.add_to_foot(self.btn_update)
        self.btn_update.hide()
        self.profile_card = ProfileCard()
        self.profile_card.show_who(computer_user())
        self.add_to_foot(self.profile_card)
        self.select("all")

    # ------------------------------------------------------------------ the section's +
    def _plus(self, tip: str) -> QToolButton:
        """A section's add button, as on the Mac: a small plain gray +, faded in while the pointer is over its
        own section (heading or rows) and faded out when it leaves. Always there for the layout, so nothing shifts."""
        b = QToolButton()
        b.setObjectName("SectionAdd")
        b.setIcon(theme.icon("plus", theme.MUTED, tokens.ICON_SM))
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # the same commands are in the menus, with keys
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        fx = QGraphicsOpacityEffect(b)
        fx.setOpacity(0.0)
        b.setGraphicsEffect(fx)
        anim = QPropertyAnimation(fx, b"opacity", b)
        anim.setDuration(tokens.FADE_MS)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        b._fade = anim
        return b

    @staticmethod
    def _fade(b: QToolButton, on: bool) -> None:
        fx, anim = b.graphicsEffect(), b._fade
        target = 1.0 if on else 0.0
        if anim.endValue() == target and anim.state() == QPropertyAnimation.State.Running:
            return
        if abs(fx.opacity() - target) < 0.01:
            return
        anim.stop()
        anim.setStartValue(fx.opacity())
        anim.setEndValue(target)
        anim.start()

    def _hover_check(self) -> None:
        """Show the + of the section under the pointer, and only that one."""
        at = QCursor.pos()
        for key, plus in getattr(self, "_section_plus", {}).items():
            head, box = self.heads[key], self.boxes[key]
            area = QRect(head.mapToGlobal(QPoint(0, 0)), head.size())
            if box.isVisible():
                area = area.united(QRect(box.mapToGlobal(QPoint(0, 0)), box.size()))
            menu_open = plus.menu() is not None and plus.menu().isVisible()
            self._fade(plus, (self.underMouse() and area.contains(at)) or menu_open)

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.HoverMove):
            QTimer.singleShot(0, self._hover_check)
        return super().eventFilter(obj, e)

    def leaveEvent(self, e):
        for plus in getattr(self, "_section_plus", {}).values():
            if plus.menu() is None or not plus.menu().isVisible():
                self._fade(plus, False)
        super().leaveEvent(e)

    # ------------------------------------------------------------------ sections
    def _section(self, key: str, text: str, extra: QWidget | None = None):
        """A heading and the list under it; returns the list's layout."""
        head = SectionHead(text)
        if extra is not None:
            head.lay.addWidget(extra)
        box = QWidget()
        if isinstance(extra, QToolButton) and extra.objectName() == "SectionAdd":
            self._section_plus = {**getattr(self, "_section_plus", {}), key: extra}
            for w in (head, box):
                w.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
                w.installEventFilter(self)
        lay = vbox(box, (0, 0, 0, tokens.SPACE_3), tokens.NAV_GAP)
        head.toggled.connect(lambda folded, k=key: self._fold(k, folded))
        self.lay.addWidget(head)
        self.lay.addWidget(box)
        self.heads[key], self.boxes[key] = head, box
        return lay

    def _show_fold(self, key: str, folded: bool) -> None:
        self.boxes[key].setVisible(not folded)
        self.heads[key].set_folded(folded)

    def _fold(self, key: str, folded: bool) -> None:
        self._show_fold(key, folded)
        self.qs.setValue("sidebar_folded", ",".join(k for k, h in self.heads.items() if h.folded))

    # ------------------------------------------------------------------ where you are
    def pick(self, key: str) -> None:
        self.select(key)
        self.picked.emit(key)

    def select(self, key: str) -> None:
        self.current = key if key in PLACES else "all"
        super().select(self.current)

    def set_counts(self, counts: dict[str, int], converting: bool, problems: bool) -> None:
        for key, row in self.rows.items():
            tone = ""
            if key == "todo" and converting:
                tone = "converting"
            elif key == "attention" and problems:
                tone = "failed"
            row.set_count(counts.get(key, 0), tone)

    def recolor(self) -> None:
        """The look changed: redraw what holds its own colors."""
        self.word.setText(theme.wordmark())
        for h in self.heads.values():
            h._draw()
        for r in self.rows.values():
            r.recolor()
        self.btn_add.setIcon(theme.icon("plus", theme.MUTED, tokens.ICON_SM))
