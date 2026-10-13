"""Storage & Cache: what Listo keeps on this computer, how much space it takes, and deleting it."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QMessageBox, QPushButton, QWidget

from listo.core import storage
from listo.core.fileutil import reveal
from listo.core.paths import data_dir
from listo.ui.components.widgets import hbox, hint, vbox
from listo.ui.style.tokens import DIALOG_W, SPACE_1, SPACE_2, SPACE_3, SPACE_5


class StorageDialog(QDialog):
    """busy(key) -> a reason that kind can't be deleted right now ('' if it can).
    cleared(key) is called after a kind was deleted (the window forgets what it held)."""

    def __init__(
        self,
        busy: Callable[[str], str] = lambda _k: "",
        cleared: Callable[[str], None] = lambda _k: None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Storage & Cache")
        self.setMinimumWidth(DIALOG_W + 2 * SPACE_5 * 3)
        self.busy, self.cleared = busy, cleared
        lay = vbox(self, SPACE_5, SPACE_3)
        title = QLabel("Storage & Cache")
        title.setObjectName("DialogTitle")
        lay.addWidget(title)
        lay.addWidget(
            hint(
                "Everything here is downloaded or made again when it's needed. Your settings, recipes "
                "and converted files are never touched. Listo sends nothing anywhere."
            )
        )
        self.rows: dict[str, tuple[QLabel, QPushButton]] = {}
        for k in storage.kinds():
            card = QFrame()
            card.setObjectName("Example")
            cl = vbox(card, (SPACE_3, SPACE_2, SPACE_3, SPACE_2), SPACE_1)
            top = hbox(spacing=SPACE_2)
            name = QLabel(k.title)
            name.setObjectName("ExTo")
            size = QLabel()
            size.setObjectName("Muted")
            delete = QPushButton("Delete")
            delete.setCursor(Qt.CursorShape.PointingHandCursor)
            delete.clicked.connect(lambda _=False, key=k.key: self._delete([key]))
            top.addWidget(name)
            top.addStretch(1)
            top.addWidget(size)
            top.addWidget(delete)
            cl.addLayout(top)
            cl.addWidget(hint(k.note))
            lay.addWidget(card)
            self.rows[k.key] = (size, delete)

        bottom = hbox(margins=(0, SPACE_1, 0, 0), spacing=SPACE_2)
        self.total = QLabel()
        self.total.setObjectName("Muted")
        bottom.addWidget(self.total)
        bottom.addStretch(1)
        folder = QPushButton("Show Folder")
        folder.setCursor(Qt.CursorShape.PointingHandCursor)
        folder.clicked.connect(self._show_folder)
        bottom.addWidget(folder)
        self.btn_all = QPushButton("Delete All")
        self.btn_all.setObjectName("Danger")
        self.btn_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_all.clicked.connect(lambda: self._delete([k.key for k in storage.kinds()]))
        bottom.addWidget(self.btn_all)
        done = QPushButton("Done")
        done.setObjectName("Primary")
        done.setDefault(True)
        done.setCursor(Qt.CursorShape.PointingHandCursor)
        done.clicked.connect(self.accept)
        bottom.addWidget(done)
        lay.addLayout(bottom)
        self.refresh()

    def refresh(self) -> None:
        total = 0
        for k in storage.kinds():
            n = storage.kind_size(k)
            total += n
            size, delete = self.rows[k.key]
            size.setText(storage.human(n) if n else "Empty")
            reason = self.busy(k.key)
            delete.setEnabled(n > 0 and not reason)
            delete.setToolTip(reason)
        self.total.setText(f"Listo is using {storage.human(total)}")
        self.btn_all.setEnabled(total > 0)

    def _delete(self, keys: list[str]) -> None:
        keys = [k for k in keys if storage.kind_size(next(x for x in storage.kinds() if x.key == k)) > 0]
        blocked = [k for k in keys if self.busy(k)]
        keys = [k for k in keys if k not in blocked]
        if not keys:
            if blocked:
                QMessageBox.information(self, "Not Right Now", self.busy(blocked[0]))
            return
        titles = {k.key: k.title for k in storage.kinds()}
        names = ", ".join(titles[k] for k in keys)
        extra = ""
        if "captions" in keys:
            extra = "\n\nCaptions you checked or fixed will be gone; clips are listened to again if you need captions."
        ans = QMessageBox.question(self, "Delete?", f"Delete {names}?{extra}")
        if ans != QMessageBox.StandardButton.Yes:
            return
        for k in keys:
            storage.clear(k)
            self.cleared(k)
        self.refresh()
        if blocked:
            QMessageBox.information(self, "Some Kept", self.busy(blocked[0]))

    def _show_folder(self) -> None:
        d = data_dir()
        d.mkdir(parents=True, exist_ok=True)
        reveal(d)
