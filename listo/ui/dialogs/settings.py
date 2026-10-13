"""Settings (⌘,): one window with a glass sidebar of sections, like the Mac's System Settings.

    General             Appearance, Accent Color, Updates
    Keyboard Shortcuts  every key, read from the menus
    Your Data           where Listo keeps its files, Storage & Cache, and the log for when something goes wrong

Everything is edited inside its section, so Settings never opens a window on top of itself (an alert asking
"Delete?" is the one exception). Things that aren't settings (Send Feedback, About) have their own windows.
How files convert is set in the window's right panel, not here.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QStackedWidget, QWidget

from listo import __version__
from listo.core import store
from listo.core.paths import data_dir
from listo.ui.components.glass import GlassRoot
from listo.ui.components.panels import LeftPanel
from listo.ui.components.widgets import (
    AccentPicker,
    ElidedLabel,
    FitScroll,
    Section,
    Segmented,
    ToggleRow,
    hbox,
    vbox,
)
from listo.ui.style import tokens

LOOKS = [("system", "Match System"), ("light", "Light"), ("dark", "Dark")]
PANES = [
    ("general", "General", "cog"),
    ("shortcuts", "Keyboard Shortcuts", "keyboard"),
    ("data", "Your Data", "box"),
]


class SettingsDialog(QDialog):
    def __init__(self, window, pane: str = "general", parent: QWidget | None = None):
        super().__init__(parent or window)
        self.win = window
        self.setWindowTitle("Settings")
        self.resize(*tokens.SETTINGS_SIZE)
        self.setMinimumSize(*tokens.SETTINGS_MIN)

        outer = vbox(self, 0, 0)
        root = GlassRoot()
        outer.addWidget(root)
        gap = tokens.GLASS_GAP
        body = hbox(root, gap, gap)
        self.side = side = LeftPanel(tokens.SETTINGS_SIDE_W)
        root.float(side)
        for key, label, icon in PANES:
            side.add_row(key, label, icon, foldable=False).clicked.connect(self.show_pane)
        side.lay.addStretch(1)
        self.rows = side.rows
        body.addWidget(side)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.panes: dict[str, QWidget] = {}
        for key, label, _icon in PANES:
            page = QWidget()
            lay = vbox(page, (tokens.SPACE_4, tokens.SPACE_4, tokens.SPACE_4, 0), tokens.SPACE_3)
            title = QLabel(label)
            title.setObjectName("PageTitle")
            lay.addWidget(title)
            holder = QWidget()
            vbox(holder, 0, 0)
            lay.addWidget(holder, 1)
            self.stack.addWidget(page)
            self.panes[key] = holder
        self._build_general()
        self._build_shortcuts()
        self._build_data()
        self.show_pane(pane if pane in self.panes else "general")

    # ------------------------------------------------------------------ moving around
    def show_pane(self, key: str) -> None:
        self.side.select(key)
        self.stack.setCurrentIndex([k for k, _l, _i in PANES].index(key))
        self.setWindowTitle(dict((k, label) for k, label, _i in PANES)[key])

    def _fill(self, key: str, w: QWidget, scroll: bool = True) -> None:
        """Put `w` in a section (replacing what was there)."""
        holder = self.panes[key]
        lay = holder.layout()
        while lay.count():
            old = lay.takeAt(0).widget()
            if old is not None:
                old.deleteLater()
        inner = w
        if scroll:
            area = FitScroll()
            area.setWidget(w)
            w = area
        lay.addWidget(w)
        inner.show()

    @staticmethod
    def _column() -> tuple[QWidget, object]:
        w = QWidget()
        lay = vbox(w, (0, 0, tokens.SPACE_3, tokens.SPACE_4), tokens.SPACE_3)
        return w, lay

    # ------------------------------------------------------------------ General
    def _build_general(self) -> None:
        w, lay = self._column()
        prefs = store.prefs()
        look = Section("Appearance")
        self.look = Segmented(LOOKS)
        self.look.set_value(str(prefs.get("appearance", "system")))
        self.look.changed.connect(self.win.set_look)
        look.add(self.look)
        lay.addWidget(look)
        accent = Section("Accent Color")
        self.accent = AccentPicker(str(prefs.get("accent", "")))
        self.accent.picked.connect(self.win.set_accent)
        accent.add(self.accent)
        lay.addWidget(accent)
        upd = Section("Updates")
        self.auto = ToggleRow("Check for Updates Automatically", self.win.auto_update())
        self.auto.toggled.connect(lambda on: store.save_pref("auto_update", on))
        upd.add(self.auto)
        version = ElidedLabel(f"Version {__version__}")
        version.setObjectName("Muted")
        upd.add(version)  # checking now is a command: the profile card's menu and Listo › Check for Updates…
        lay.addWidget(upd)
        lay.addStretch(1)
        self._fill("general", w)

    # ------------------------------------------------------------------ Shortcuts
    def _build_shortcuts(self) -> None:
        from listo.ui.dialogs.shortcuts import ShortcutsList

        self._fill("shortcuts", ShortcutsList(self.win.menuBar()))

    # ------------------------------------------------------------------ Your Data
    def _build_data(self) -> None:
        from listo.ui.dialogs.storage import StorageView

        w, lay = self._column()
        where = Section("Saved On This Computer")
        path = ElidedLabel(str(data_dir()), Qt.TextElideMode.ElideMiddle)
        path.setObjectName("Muted")
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        where.add(path)
        show = QPushButton("Show Folder")
        show.clicked.connect(self.win.open_data_folder)
        back = QPushButton("Back Up…")
        back.setToolTip("Your settings, recipes and checked captions, in one .zip")
        back.clicked.connect(self.win.back_up)
        row = hbox(spacing=tokens.SPACE_2)
        row.addWidget(show)
        row.addWidget(back)
        row.addStretch(1)
        where.add(row)
        lay.addWidget(where)
        space = Section("Storage & Cache")
        self.storage = StorageView(self.win._storage_busy, self.win._storage_cleared)
        space.add(self.storage)
        lay.addWidget(space)
        trouble = Section("When Something Goes Wrong")
        console = QPushButton("Open Debug Console")
        console.setToolTip("A terminal window that follows what Listo is doing, live")
        console.clicked.connect(self.win.open_console)
        logfile = QPushButton("Show the Log File")
        logfile.clicked.connect(self.win._show_log)
        row = hbox(spacing=tokens.SPACE_2)
        row.addWidget(console)
        row.addWidget(logfile)
        row.addStretch(1)
        trouble.add(row)
        lay.addWidget(trouble)
        lay.addStretch(1)
        self._fill("data", w)
