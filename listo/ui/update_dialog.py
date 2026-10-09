"""Updates window: what's new in the latest Listo, and Update Now (download, swap in, reopen).

core/update.py does the work; this window only shows it. MainWindow.check_updates() opens it.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QWidget,
)

from .. import __version__
from ..core import update
from ..core.log import get_logger
from .tokens import DIALOG_W, SPACE_2, SPACE_3, SPACE_5
from .widgets import hbox, hint, vbox

log = get_logger(__name__)


def open_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


class CheckThread(QThread):
    """Asks GitHub for the latest release (never on the window's thread)."""

    found = Signal(object)  # update.Release
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.found.emit(update.check())
        except Exception as e:  # no internet, GitHub busy, an odd answer
            log.info("update check failed: %s", e)
            self.failed.emit(str(e))


class DownloadThread(QThread):
    progress = Signal(float)
    ready = Signal(object)  # update.Plan
    failed = Signal(str)

    def __init__(self, release: update.Release, kind: str, parent=None):
        super().__init__(parent)
        self.release, self.kind = release, kind
        self.cancel = threading.Event()

    def run(self) -> None:
        work: Path | None = None
        try:
            name = update.asset_name(self.kind)
            asset = self.release.assets.get(name or "")
            if asset is None:
                raise ValueError(f"This release has no {name or 'file for this computer'}.")
            work = update.new_work_folder()
            f = update.download(asset, work, self.progress.emit, self.cancel)
            self.ready.emit(update.prepare(self.kind, f))
        except update.Canceled:
            self.failed.emit("")
        except Exception as e:
            log.warning("update download failed", exc_info=True)
            self.failed.emit(str(e) or "The update couldn't be downloaded.")


class UpdateDialog(QDialog):
    """Shows a release. `busy()` -> a reason not to restart now ('' if fine)."""

    def __init__(self, release: update.Release, busy=lambda: "", parent: QWidget | None = None):
        super().__init__(parent)
        self.release, self.busy = release, busy
        self.kind = update.install_kind()
        self.plan: update.Plan | None = None
        self.thread: DownloadThread | None = None
        self.setWindowTitle("Update Listo")
        self.setMinimumWidth(DIALOG_W + 2 * SPACE_5 * 3)
        lay = vbox(self, SPACE_5, SPACE_3)
        title = QLabel(f"Listo {release.version} is here")
        title.setObjectName("DialogTitle")
        lay.addWidget(title)
        lay.addWidget(hint(f"You have {__version__}. Your settings and recipes stay as they are."))
        notes = QTextBrowser()
        notes.setObjectName("Notes")
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(_whats_new(release.notes))
        notes.setMinimumHeight(220)
        lay.addWidget(notes, 1)
        self.status = hint("")
        self.status.hide()
        lay.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay.addWidget(self.bar)

        row = hbox(spacing=SPACE_2)
        page = QPushButton("See on GitHub")
        page.setObjectName("Ghost")
        page.clicked.connect(lambda: open_url(release.page))
        row.addWidget(page)
        row.addStretch(1)
        self.btn_later = QPushButton("Later")
        self.btn_later.clicked.connect(self._later)
        row.addWidget(self.btn_later)
        self.btn_go = QPushButton("Update Now")
        self.btn_go.setObjectName("Primary")
        self.btn_go.setDefault(True)
        self.btn_go.clicked.connect(self._go)
        row.addWidget(self.btn_go)
        lay.addLayout(row)

        why_not = update.can_update_here(self.kind)
        if why_not:
            self._say(why_not)
            self.btn_go.setText("Download")
            self.btn_go.clicked.disconnect()
            self.btn_go.clicked.connect(lambda: (open_url(release.page), self.accept()))
            if self.kind == "source":
                self.btn_go.hide()

    def _say(self, text: str) -> None:
        self.status.setText(text)
        self.status.show()

    def _go(self) -> None:
        if self.plan is not None:  # downloaded: restart into the new version
            reason = self.busy()
            if reason:
                self._say(reason)
                return
            self.accept()
            return
        self.btn_go.setEnabled(False)
        self.btn_go.setText("Downloading…")
        self.btn_later.setText("Cancel")
        self.bar.setValue(0)
        self.bar.show()
        self._say("Downloading the new version…")
        self.thread = DownloadThread(self.release, self.kind, self)
        self.thread.progress.connect(lambda v: self.bar.setValue(int(v * 1000)))
        self.thread.ready.connect(self._ready)
        self.thread.failed.connect(self._failed)
        self.thread.start()

    def _ready(self, plan: update.Plan) -> None:
        self.plan = plan
        self.bar.setValue(1000)
        self._say("Ready. Listo will close, update itself and open again in a few seconds.")
        self.btn_go.setText("Restart Listo")
        self.btn_go.setEnabled(True)
        self.btn_later.setText("Later")

    def _failed(self, msg: str) -> None:
        self.bar.hide()
        self.btn_go.setEnabled(True)
        self.btn_go.setText("Try Again")
        self.btn_later.setText("Later")
        self._say(msg or "Download stopped.")

    def _later(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.thread.cancel.set()
            self.thread.wait(5000)
            return
        self.reject()

    def done(self, r: int) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.thread.cancel.set()
            self.thread.wait(5000)
        super().done(r)


def _whats_new(body: str) -> str:
    """The release text without the download table (the app already knows which file it needs)."""
    keep = []
    skipping = False
    for line in body.splitlines():
        if line.strip().lower().startswith("## download"):
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            keep.append(line)
    text = "\n".join(keep).strip()
    return text or "Fixes and improvements."


def restart_into(plan: update.Plan) -> None:
    """Start the helper that swaps the new version in, then quit."""
    update.run(plan)
    app = QApplication.instance()
    if app is not None:
        app.closeAllWindows()
        app.quit()
