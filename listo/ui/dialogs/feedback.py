"""Send Feedback: an idea or a problem, for the people who make Listo. See services/feedback.py."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QDialog, QLabel, QLineEdit, QPushButton, QWidget

from listo.services import feedback
from listo.ui.components.widgets import Section, Segmented, TextBox, button_row, hint, vbox
from listo.ui.style import tokens


class FeedbackDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Send Feedback")
        self.setMinimumWidth(tokens.DIALOG_W_WIDE)
        self.sent_now = False
        lay = vbox(self, tokens.SPACE_5, tokens.SPACE_3)
        t = QLabel("Send Feedback")
        t.setObjectName("DialogTitle")
        lay.addWidget(t)
        lay.addWidget(hint("An idea, something that went wrong, anything. It's read by a person."))

        self.kind = Segmented([(k, label) for k, label in feedback.KINDS])
        self.kind.set_value("idea")
        lay.addWidget(self.kind)
        self.message = TextBox("What's on your mind?", tokens.TEXT_BOX_TALL)
        self.message.edited.connect(self._can_send)
        lay.addWidget(self.message)
        sec = Section("Your Email (optional, for a reply)")
        self.email = QLineEdit()
        sec.add(self.email)
        lay.addWidget(sec)
        self.details = QCheckBox("Include Listo's version and the kind of computer")
        self.details.setChecked(True)
        lay.addWidget(self.details)
        if not feedback.ADDRESS and not feedback.sender().connected:
            lay.addWidget(
                hint("Sending isn't switched on yet: your message waits on this computer until it is.")
            )

        row = button_row()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.send = QPushButton("Send")
        self.send.setObjectName("Primary")
        self.send.setDefault(True)
        self.send.clicked.connect(self._send)
        row.addWidget(cancel)
        row.addWidget(self.send)
        lay.addLayout(row)
        self._can_send()

    def _can_send(self) -> None:
        self.send.setEnabled(bool(self.message.text().strip()))

    def _send(self) -> None:
        try:
            fb = feedback.make(
                self.kind.value(), self.message.text(), self.email.text(), self.details.isChecked()
            )
        except OSError:
            return
        link = feedback.mail_link(fb)
        if link:  # a support address: your email app opens with it written
            QDesktopServices.openUrl(QUrl(link))
            self.sent_now = True
        else:
            self.sent_now = feedback.send(fb)
        self.accept()
