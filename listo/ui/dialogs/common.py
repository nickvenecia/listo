"""Small dialogs: alerts (confirm, notice), asking for a name, and the About box."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QLabel, QLineEdit, QPushButton, QWidget

from listo.ui.components.widgets import button_row, hbox, hint, vbox
from listo.ui.style import tokens
from listo.ui.style.tokens import DIALOG_W, SPACE_3, SPACE_5


class Alert(QDialog):
    """A Mac-style alert: the app's icon, a bold question, a line of detail, two buttons side by side.
    Return does the action, Esc cancels. A rounded card floating over the window, with no title bar."""

    def __init__(
        self, parent: QWidget | None, title: str, text: str, action: str, cancel: str = "", danger=False
    ):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle(title)
        outer = vbox(self, 0, 0)
        card = QFrame()
        card.setObjectName("Alert")
        card.setFixedWidth(tokens.ALERT_W)
        outer.addWidget(card)
        lay = vbox(card, (tokens.SPACE_5, tokens.SPACE_5, tokens.SPACE_5, tokens.SPACE_4), tokens.SPACE_2)
        icon = QLabel()
        app_icon = QApplication.windowIcon()
        if not app_icon.isNull():
            icon.setPixmap(app_icon.pixmap(tokens.ALERT_ICON, tokens.ALERT_ICON))
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(icon)
            lay.addSpacing(tokens.SPACE_1)
        t = QLabel(title)
        t.setObjectName("AlertTitle")
        t.setWordWrap(True)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        if text:
            body = hint(text)
            body.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(body)
        lay.addSpacing(tokens.SPACE_3)
        row = hbox(spacing=tokens.SPACE_2)
        if cancel:
            no = QPushButton(cancel)
            no.setAutoDefault(False)
            no.clicked.connect(self.reject)
            row.addWidget(no, 1)
        go = QPushButton(action)
        go.setObjectName("DangerFill" if danger else "Primary")
        go.setDefault(True)  # Return
        go.setAutoDefault(True)
        go.clicked.connect(self.accept)
        row.addWidget(go, 1)
        lay.addLayout(row)
        self.go = go

    def showEvent(self, e):
        super().showEvent(e)
        self.go.setFocus()
        win = self.parentWidget().window() if self.parentWidget() is not None else None
        if win is not None:  # over the middle of the window, a little above centre, like a Mac alert
            g = win.frameGeometry()
            self.move(g.center().x() - self.width() // 2, g.top() + g.height() // 3 - self.height() // 2)


def confirm(parent: QWidget, title: str, text: str, action: str, danger: bool = True) -> bool:
    """Ask before doing something big. Return says yes; Esc says no."""
    return Alert(parent, title, text, action, "Cancel", danger).exec() == QDialog.DialogCode.Accepted


def notice(parent: QWidget, title: str, text: str) -> None:
    """Something went wrong and it needs more than a toast to say why."""
    Alert(parent, title, text, "OK").exec()


def ask_name(parent: QWidget, title: str, action: str, text: str = "", placeholder: str = "") -> str | None:
    """One name, typed (a new recipe). None if cancelled or left blank."""
    d = QDialog(parent)
    d.setWindowTitle(title)
    d.setMinimumWidth(DIALOG_W)
    lay = vbox(d, SPACE_5, SPACE_3)
    t = QLabel(title)
    t.setObjectName("DialogTitle")
    lay.addWidget(t)
    field = QLineEdit(text)
    field.setPlaceholderText(placeholder)
    field.selectAll()
    lay.addWidget(field)
    row = button_row()
    cancel = QPushButton("Cancel")
    cancel.clicked.connect(d.reject)
    go = QPushButton(action)
    go.setObjectName("Primary")
    go.setDefault(True)
    go.clicked.connect(d.accept)
    go.setEnabled(bool(text.strip()))
    field.textChanged.connect(lambda t: go.setEnabled(bool(t.strip())))
    row.addWidget(cancel)
    row.addWidget(go)
    lay.addLayout(row)
    if d.exec() != QDialog.DialogCode.Accepted:
        return None
    return field.text().strip() or None


def about(parent: QWidget, version: str, ffmpeg: str, data_folder: str) -> None:
    d = QDialog(parent)
    d.setWindowTitle("About Listo")
    d.setMinimumWidth(DIALOG_W)
    lay = vbox(d, SPACE_5, SPACE_3)
    from listo.ui.style import theme

    word = QLabel(theme.wordmark())
    word.setObjectName("Wordmark")
    word.setTextFormat(Qt.TextFormat.RichText)
    lay.addWidget(word)
    lay.addWidget(hint(f"Version {version}. Drop it in. Get it back edit-ready."))
    lay.addWidget(hint(f"Video conversion by FFmpeg ({ffmpeg or 'not found'})."))
    lay.addWidget(hint(f"Your settings, captions and tools are kept on this computer only, in {data_folder}"))
    lay.addWidget(hint("Open source. Fonts under the SIL Open Font License; see Third-Party Notices."))
    row = button_row()
    ok = QPushButton("Done")
    ok.setObjectName("Primary")
    ok.clicked.connect(d.accept)
    row.addWidget(ok)
    lay.addLayout(row)
    d.exec()
