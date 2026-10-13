"""The window, full screen: the sidebar (where you are) | the files, with the progress under them | Convert To.

Drop files in (or + them), pick how they convert on the right, press Convert. The sidebar shows the files by
kind and by how far along they are; the right panel slides away with its ✕ or Esc and comes back when you
click a file (or View › Convert Settings).
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QByteArray, QPoint, QSize, Qt, QThread, QThreadPool, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QDragEnterEvent,
    QDropEvent,
    QGuiApplication,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from listo import APP_NAME, __version__
from listo.core import captions, console, join, naming, store, tape, update
from listo.core.captions import sample_cues
from listo.core.engine import Conversion, Result
from listo.core.fileutil import reveal
from listo.core.links import is_link
from listo.core.log import get_logger
from listo.core.paths import data_dir
from listo.core.presets import (
    AUDIO_FORMATS,
    OVERRIDE_KEYS,
    PHOTO_FORMATS,
    SESSION_ONLY,
    VIDEO_PRESETS,
    Settings,
    format_label,
    timecode_mode,
)
from listo.core.probe import (
    KNOWN_EXTS,
    SIDECAR_EXTS,
    UNSUPPORTED_HINTS,
    MediaInfo,
    ext_of,
    fmt_duration,
    kind_from_ext,
    probe,
)
from listo.core.progress import BatchClock, time_left
from listo.core.sample import sample_clip, sample_clip_if_made
from listo.core.tools import capabilities
from listo.ui.components import titlebar
from listo.ui.components.empty import EmptyPage
from listo.ui.components.glass import Dock, GlassRoot, glass
from listo.ui.components.player import space_plays
from listo.ui.components.widgets import (
    ElidedLabel,
    SearchField,
    Toast,
    circle_button,
    hbox,
    hint,
    vbox,
)
from listo.ui.dialogs.captions import CaptionEditor
from listo.ui.dialogs.common import about, confirm, notice
from listo.ui.dialogs.preview import PreviewDialog
from listo.ui.dialogs.trim import TrimDialog, fmt_time
from listo.ui.dialogs.update import CheckThread, UpdateDialog, restart_into
from listo.ui.panels.convert_to import ConvertPanel
from listo.ui.style import theme, tokens
from listo.ui.window.history import History, Step
from listo.ui.window.jobs import (
    ConvertThread,
    DownloadThread,
    HardwareSignals,
    HardwareTask,
    JoinThread,
    PreviewSignals,
    PreviewTask,
    ProbeSignals,
    ProbeTask,
    TranscribeThread,
)
from listo.ui.window.sidebar import PLACES, Sidebar, in_place
from listo.ui.window.tables import FileList, Row

log = get_logger(__name__)

_ORPHANS: list = []
SOON_MS = 60  # how long list-wide refreshes wait to gather changes
FINAL = ("done", "warning", "failed", "skipped", "canceled", "unsupported")


@dataclass
class JoinJob:
    """One batch whose videos become one long video (core/join.py)."""

    ids: list[int]  # the clips, in list order
    settings: Settings  # the same for every part (per-file format changes don't apply)
    conform: object  # video.Conform: what every part must match
    folder: Path  # hidden parts folder
    timecodes: dict[int, str] = field(default_factory=dict)  # item id -> where its timecode starts
    parts: dict[int, Path] = field(default_factory=dict)  # item id -> converted part
    cues: dict[int, list] = field(default_factory=dict)  # item id -> its captions in the part
    thread: object | None = None  # JoinThread once gluing starts
    done_s: float = 0.0
    total_s: float = 0.0


@dataclass
class Item:
    id: int
    path: str
    kind: str
    info: MediaInfo | None = None
    state: str = "probing"
    processed: float = 0.0
    result: Result | None = None
    card: Row | None = None  # its row in the list (tables.Row)
    message: str = ""
    notes: list[str] = field(default_factory=list)
    override: dict = field(default_factory=dict)  # per-file format choice
    base: Settings | None = None  # settings captured when this file joined a batch
    started: float = 0.0
    speed: float = 0.0
    url: str = ""  # set for things added from a link
    trim: tuple[float, float] | None = None
    transcript: object | None = None  # captions.Transcript once speech has been turned into text
    clock: str | None = None  # Continuous Timecode: its place on the tape (None = not given yet)

    @property
    def length(self) -> float:
        if self.trim:
            return max(0.1, self.trim[1] - self.trim[0])
        return self.info.duration if self.info else 0.0

    @property
    def weight(self) -> float:
        """How much of the batch this file is, in 'seconds of media'."""
        if self.length and self.kind in ("video", "audio"):
            return max(self.length, 1.0)
        return 2.0

    @property
    def frac(self) -> float:
        if self.state in ("done", "warning"):
            return 1.0
        if self.state in ("converting", "paused") and self.length:
            return min(1.0, self.processed / self.length)
        return 0.0


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        self.resize(*tokens.WINDOW_SIZE)
        self.setMinimumSize(QSize(*tokens.WINDOW_MIN))
        self.qs = store.Prefs()  # settings.json in Listo's data folder
        try:
            self.settings = Settings.from_dict(store.loads(self.qs.value("settings", {}), {}))
        except Exception:
            log.warning("couldn't read the saved settings; starting fresh", exc_info=True)
            self.settings = Settings()
        for key in SESSION_ONLY:  # captions / join start off each launch (presets.SESSION_ONLY)
            setattr(self.settings, key, getattr(Settings(), key))
        self._caption_choice = (self.settings.caption_model, self.settings.caption_language)

        self.items: dict[int, Item] = {}
        self.order: list[int] = []
        self._next_id = 1
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max(2, min(4, (os.cpu_count() or 4) // 2)))
        self.probe_signals = ProbeSignals()
        self.probe_signals.done.connect(self._probed)
        self.hw_signals = HardwareSignals()
        self.hw_signals.done.connect(self._hardware_found)

        self.running = False
        self.paused = False
        self.batch: list[int] = []
        self.reserved: set[str] = set()
        self.counter = 0
        self._tape_s = 0.0  # Continuous Timecode: how much of this Convert's "tape" is used
        self._clock = BatchClock(time.monotonic())  # the batch's time left (started again by each Convert)
        self.active: dict[int, ConvertThread] = {}
        self.downloads: dict[int, DownloadThread] = {}
        self.caps = capabilities()
        self.selected: set[int] = set()
        self.place = "all"  # the sidebar's choice: which files the list shows
        self.tx = None  # TranscribeThread while captions are being made in the background
        self._tx_pct: dict[int, float] = {}
        self._tx_failed: dict[int, str] = {}
        self._tx_retry = False
        self._convert_after_captions = False  # Convert was pressed while captions were still being made
        self._redo_edited: set[int] = (
            set()
        )  # hand-edited clips you said to redo with a new accuracy / language
        self.join_job: JoinJob | None = None
        self._live_seq = 0
        self._live_note = ""
        self._live_at = 0.0
        self._live_loaded: object = None  # which clip the preview's player has open
        self._live_play_next = False  # the preview's arrows keep playing if it was playing
        self._sample_probe: tuple[str, MediaInfo] | None = None
        self._anchor: int | None = None  # where a Shift-click range starts
        self._restored = False  # True: open at the size already set (screenshots), not the saved one
        self.history = History()  # undo / redo
        self._settings_before = self.settings.to_dict()  # the settings as the last undo step left them
        self._history_busy = False  # undoing or redoing: that's not a new step

        self._build()
        self._menus()

        self._live_signals = PreviewSignals(self)
        self._live_signals.done.connect(self._live_got)
        self.export_panel.player.settled.connect(self._live_settled)
        self.export_panel.player.step.connect(self._live_step)
        space_plays(self, self.export_panel.player)  # Space plays / pauses the preview
        # List-wide refreshes (footer, captions status, live preview) wait a moment and run once:
        # reading 500 files must not redo them 500 times (that took minutes).
        self._soon_captions = False
        self._soon_timer = QTimer(self)
        self._soon_timer.setSingleShot(True)
        self._soon_timer.setInterval(SOON_MS)
        self._soon_timer.timeout.connect(self._refresh_now)
        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(350)  # wait until a slider or a few clicks settle
        self._live_timer.timeout.connect(self._render_live)
        self._settings_timer = QTimer(self)  # a settings change becomes an undo step once it settles
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(tokens.SAVE_DELAY_MS)
        self._settings_timer.timeout.connect(self._record_settings)
        self._schedule_live()
        self.convert.apply_capabilities(self.caps)
        self.pool.start(HardwareTask(self.hw_signals))
        self._refresh_footer()
        self.look_changed()
        QTimer.singleShot(0, self.table.setFocus)

        if not self.caps.ok:
            QTimer.singleShot(300, self._missing_ffmpeg)
        self.latest: update.Release | None = None
        self._upd_thread = None
        QTimer.singleShot(tokens.UPDATE_CHECK_DELAY_MS, self._auto_check_updates)

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        root = GlassRoot()
        self.root = root
        outer = vbox(root, 0, 0)
        self.titlebar = titlebar.install(self)  # Mac: Listo's own title bar (follows the look)
        if self.titlebar is not None:
            outer.addWidget(self.titlebar)
        gap = tokens.GLASS_GAP
        body = hbox(spacing=gap)
        body.setContentsMargins(gap, 0 if self.titlebar is not None else gap, gap, gap)
        self.sidebar = glass(Sidebar())
        self.sidebar.picked.connect(self.go)
        self.sidebar.profile_card.clicked.connect(self._app_menu)
        self.btn_update = self.sidebar.btn_update
        self.btn_update.clicked.connect(self.open_update)
        root.float(self.sidebar)
        body.addWidget(self.sidebar)
        body.addWidget(self._build_center(), 1)

        self.panel = ConvertPanel(self.settings)
        self.convert = self.panel.settings_part  # what the files become
        self.export_panel = self.panel.export_part  # the preview, where they go, their names
        self.convert.changed.connect(self._settings_changed)
        self.export_panel.changed.connect(self._settings_changed)
        self.export_panel.preview_clicked.connect(self.open_preview)
        self.convert.recipe_applied.connect(self.export_panel.reload)
        self.panel.btn_preview.clicked.connect(self.open_preview)
        self.panel.close_wanted.connect(lambda: self.show_panel(False))
        self.inspector = glass(QStackedWidget())  # the glass panel on the right…
        self.inspector.addWidget(self.panel)
        self.dock = Dock(self.inspector, root, self.sidebar, body)  # …which slides in and out
        self.dock.follower = lambda: self.pages.currentWidget()
        outer.addLayout(body, 1)
        self.setCentralWidget(root)
        self.toast = Toast(root)
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._escape)
        self.dock.set_open(self.qs.value("panel_open", True, type=bool), animate=False)

    def _build_center(self) -> QWidget:
        center = QFrame()
        center.setObjectName("Center")
        lay = vbox(center, 0, 0)
        bar = QFrame()
        bar.setObjectName("Toolbar")
        bar.setFixedHeight(tokens.TOOLBAR_H)
        # three parts: the title on the left, the search centred, the + on the right
        grid = QGridLayout(bar)
        grid.setContentsMargins(tokens.SPACE_4, 0, tokens.SPACE_2, 0)
        grid.setHorizontalSpacing(tokens.SPACE_4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)
        left = hbox(spacing=tokens.SPACE_2)
        self.title = QLabel(PLACES["all"][0])
        self.title.setObjectName("PageTitle")
        self.count = ElidedLabel()  # "12", or "3 selected": gives way before the search does
        self.count.setObjectName("PageCount")
        self.count.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        left.addWidget(self.title)
        left.addWidget(self.count)
        left.addStretch(1)
        grid.addLayout(left, 0, 0)
        mid = hbox(spacing=tokens.SPACE_2)
        self.search = SearchField()
        self.search.setPlaceholderText("Search")
        self.search.setProperty("capsule", True)
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(tokens.SEARCH_MIN)  # shrinks before anything squeezes together
        self.search.setMaximumWidth(tokens.SEARCH_W)
        self.search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search.addAction(theme.icon("search", theme.FAINT), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(lambda _t: self._apply_filter())
        mid.addWidget(self.search)
        grid.addLayout(mid, 0, 1, Qt.AlignmentFlag.AlignCenter)
        right = hbox(spacing=tokens.SPACE_2)
        right.addStretch(1)
        self.btn_add = QToolButton()
        self.btn_add.setObjectName("CirclePrimary")
        self.btn_add.setIcon(theme.icon("plus", theme.ON_ACCENT))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setToolTip("Add Files, a Folder or a Link (or just drop them in)")
        self.btn_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_add.setMenu(self._add_menu(self.btn_add))
        self.sidebar.btn_add.setMenu(self._add_menu(self.sidebar.btn_add))
        right.addWidget(self.btn_add)
        grid.addLayout(right, 0, 2)
        lay.addWidget(bar)

        self.pages = QStackedWidget()
        self.empty = EmptyPage(  # before any files are in: the ways to start
            (
                (
                    "film",
                    "Add Files…",
                    "Videos, photos or audio",
                    "Or drop them anywhere on this window.",
                    self.pick_files,
                ),
                ("folder", "Add a Folder…", "Everything inside it", "", self.pick_folder),
                (
                    "link",
                    "Add a Link…",
                    "A video on the web",
                    "YouTube, Vimeo, Instagram and more. Or just paste a link.",
                    self.ask_link,
                ),
            )
        )
        self.table = FileList()
        self.table.pressed.connect(self._card_pressed)
        self.table.opened.connect(self.play_item)
        self.table.remove.connect(self.remove_item)
        self.table.retry.connect(self.retry_item)
        self.table.reveal.connect(self.reveal_item)
        self.table.details.connect(self.show_details)
        self.table.format_clicked.connect(self._format_menu)
        self.table.trim_clicked.connect(self.trim_item)
        self.table.captions_clicked.connect(self.open_captions)
        self.table.menu_wanted.connect(self._row_menu)
        self.table.blank_clicked.connect(self._escape)
        self.table.step.connect(self._step_pick)
        self.table.reordered.connect(self._reordered)
        self.nothing = QLabel("Nothing here.")  # a place or a search with no files in it
        self.nothing.setObjectName("EmptyText")
        self.nothing.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for w in (self.empty, self.table, self.nothing):
            self.pages.addWidget(w)
        lay.addWidget(self.pages, 1)

        footer = QFrame()
        footer.setObjectName("Totals")
        self.footer = footer
        f = hbox(footer, (tokens.SPACE_4, tokens.SPACE_3, tokens.SPACE_2, tokens.SPACE_3), tokens.SPACE_2)
        texts = QVBoxLayout()
        texts.setSpacing(tokens.SPACE_1)
        top = hbox(spacing=tokens.SPACE_3)
        self.f_title = QLabel()
        self.f_title.setObjectName("TotalValue")
        self.f_time = QLabel()  # while converting: "3 of 9 done · About 2 min left", at the bar's right end
        self.f_time.setObjectName("TotalLabel")
        self.f_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.f_title)
        top.addStretch(1)
        top.addWidget(self.f_time)
        self.f_sub = QLabel()
        self.f_sub.setObjectName("TotalLabel")
        self.f_bar = QProgressBar()
        self.f_bar.setRange(0, 1000)
        self.f_bar.setTextVisible(False)
        self.f_bar.hide()
        texts.addLayout(top)
        texts.addWidget(self.f_sub)
        texts.addWidget(self.f_bar)
        f.addLayout(texts, 1)
        f.addSpacing(tokens.SPACE_3)
        self.btn_show = QPushButton("Show Files")
        self.btn_show.clicked.connect(self._show_outputs)
        self.btn_show.hide()
        self.btn_pause = circle_button("pause", "Pause")
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_cancel = circle_button("stop", "Stop", theme.BAD)
        self.btn_cancel.clicked.connect(self.stop)
        self.btn_check = QPushButton("Check Captions")
        self.btn_check.setIcon(theme.icon("captions", theme.TEXT, tokens.ICON_SM))
        self.btn_check.setToolTip("Watch each clip with its captions and fix any words before converting")
        self.btn_check.clicked.connect(self.check_captions)
        self.btn_check.hide()
        self.btn_start = QPushButton("Convert")
        self.btn_start.setObjectName("Primary")
        self.btn_start.clicked.connect(self.start)
        for b in (self.btn_show, self.btn_pause, self.btn_cancel, self.btn_check, self.btn_start):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            f.addWidget(b)
        lay.addWidget(footer)
        return center

    def _add_menu(self, owner: QWidget) -> QMenu:
        m = QMenu(owner)
        m.addAction(theme.menu_icon("file"), "Add Files…", self.pick_files)
        m.addAction(theme.menu_icon("folder"), "Add a Folder…", self.pick_folder)
        m.addAction(theme.menu_icon("link"), "Add a Link…", self.ask_link)
        return m

    def _menus(self) -> None:
        """Commands with shortcuts. The menu bar shows on the Mac; on Windows and Linux it's hidden and the
        shortcuts still work (Settings, feedback and updates are in the profile card's menu)."""
        bar = self.menuBar()

        def act(menu, text: str, fn, keys=None, role=None) -> QAction:
            a = QAction(text, self)
            if keys is not None:
                seqs = keys if isinstance(keys, list) else [keys]
                a.setShortcuts([QKeySequence(k) for k in seqs])
            if role is not None:
                a.setMenuRole(role)
            a.triggered.connect(fn)
            menu.addAction(a)
            self.addAction(a)  # shortcuts work even while the menu bar is hidden
            return a

        f = bar.addMenu("File")
        act(f, "Add Files…", self.pick_files, QKeySequence.StandardKey.Open)
        act(f, "Add a Folder…", self.pick_folder, "Ctrl+Shift+O")
        act(f, "Add a Link…", self.ask_link, "Ctrl+L")
        f.addSeparator()
        act(f, "Preview…", self.open_preview, "Ctrl+P")
        act(f, "Check Captions…", self.check_captions, "Ctrl+Shift+C")
        f.addSeparator()
        act(f, "Convert", self.start, "Ctrl+Return")
        act(f, "Stop", self.stop, "Ctrl+.")
        f.addSeparator()
        prefs = act(f, "Settings…", self.open_settings, QKeySequence.StandardKey.Preferences)
        prefs.setMenuRole(QAction.MenuRole.PreferencesRole)  # the Mac puts it under Listo, ⌘,
        if sys.platform != "darwin":
            prefs.setShortcut(QKeySequence("Ctrl+,"))  # (Windows and Linux have no standard key for it)
        act(f, f"Quit {APP_NAME}", self.close, QKeySequence.StandardKey.Quit, QAction.MenuRole.QuitRole)

        e = bar.addMenu("Edit")
        self.act_undo = act(e, "Undo", self.undo, QKeySequence.StandardKey.Undo)
        self.act_redo = act(e, "Redo", self.redo, "Ctrl+Shift+Z")
        if sys.platform != "darwin":  # Ctrl+Y too, as Windows apps do
            self.act_redo.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
        e.aboutToShow.connect(self._edit_menu_state)
        e.addSeparator()
        # Text fields keep these keys for themselves while you type in them.
        act(e, "Paste", self._paste, QKeySequence.StandardKey.Paste)
        act(e, "Select All", self.select_all, QKeySequence.StandardKey.SelectAll)
        e.addSeparator()
        act(e, "Remove from the List…", self.remove_selected, [Qt.Key.Key_Backspace, Qt.Key.Key_Delete])
        act(e, "Clear Finished", self.clear_finished)
        act(e, "Clear All…", self.clear_all)
        e.addSeparator()
        act(e, "Find", self.search.setFocus, QKeySequence.StandardKey.Find)

        v = bar.addMenu("View")
        for n, key in enumerate(("all", "video", "photo", "audio"), start=1):
            act(v, PLACES[key][0], lambda _c=False, k=key: self.go(k), f"Ctrl+{n}")
        v.addSeparator()
        act(v, "Convert Settings", lambda: self.show_panel(not self.dock.opened), "Ctrl+Alt+I")
        act(v, "Show All Options", lambda: self.convert.open_groups(True))
        act(v, "Fold All Options", lambda: self.convert.open_groups(False))
        v.addSeparator()
        self.look_actions: dict[str, QAction] = {}
        looks = v.addMenu("Appearance")
        group = QActionGroup(looks)
        for key, label in (("system", "Match the System"), ("light", "Light"), ("dark", "Dark")):
            a = looks.addAction(label)
            a.setCheckable(True)
            group.addAction(a)
            a.triggered.connect(lambda _c=False, k=key: self.set_look(k))
            self.look_actions[key] = a

        w = bar.addMenu("Window")
        act(w, "Minimize", self.showMinimized, "Ctrl+M")
        act(w, "Zoom", lambda: titlebar.toggle_size(self))

        h = bar.addMenu("Help")
        act(h, "Keyboard Shortcuts", lambda: self.open_settings("shortcuts"), "Ctrl+/")
        act(h, "Send Feedback…", self.open_feedback)
        upd = act(h, "Check for Updates…", self.check_updates)
        upd.setMenuRole(QAction.MenuRole.ApplicationSpecificRole)  # on the Mac: in the Listo menu
        act(h, "Storage && Cache…", lambda: self.open_settings("data"))
        act(h, "Open Debug Console", self.open_console, "Ctrl+Alt+D")
        act(h, "Show the Log File", self._show_log)
        act(h, "Open Data Folder", self.open_data_folder)
        act(h, f"About {APP_NAME}", self._about, role=QAction.MenuRole.AboutRole)
        bar.setVisible(sys.platform == "darwin")

    def _app_menu(self) -> None:
        """The profile card's menu: feedback, updates and Settings (the way in on every system)."""
        card = self.sidebar.profile_card
        m = QMenu(card)
        m.addAction(theme.menu_icon("message"), "Send Feedback…", self.open_feedback)
        m.addAction(theme.menu_icon("arrow-down"), "Check for Updates…", self.check_updates)
        s = m.addAction(theme.menu_icon("cog"), "Settings…", self.open_settings)
        s.setShortcut(QKeySequence.StandardKey.Preferences)  # shown for reference; the menu bar's runs it
        s.setShortcutVisibleInContextMenu(True)
        at = card.mapToGlobal(QPoint(0, 0))
        m.exec(QPoint(at.x(), at.y() - m.sizeHint().height() - tokens.MENU_GAP))

    # ------------------------------------------------------------------ where you are
    def go(self, place: str) -> None:
        """Show the files in a place of the sidebar (All Files, Videos… To Convert, Done, Need a Look)."""
        self.place = place if place in PLACES else "all"
        self.sidebar.select(self.place)
        self.title.setText(PLACES[self.place][0])
        self._apply_filter()

    def _shown(self, it: Item) -> bool:
        text = self.search.text().strip().casefold()
        if text and text not in os.path.basename(it.path).casefold() and text not in it.card.name.casefold():
            return False
        return in_place(self.place, it.kind, it.state)

    def _apply_filter(self) -> None:
        """Show the files that belong to the place and match the search, in list order."""
        self.table.show_ids([i for i in self.order if self._shown(self.items[i])])
        self._show_page()
        self._show_count()

    def _show_page(self) -> None:
        self.search.setVisible(bool(self.items))  # nothing to search yet
        if not self.items:
            self.pages.setCurrentWidget(self.empty)
        elif not self.table.shown_ids():
            self.pages.setCurrentWidget(self.nothing)
        else:
            self.pages.setCurrentWidget(self.table)

    def _show_count(self) -> None:
        n = len(self.selected)
        shown = len(self.table.shown_ids())
        self.count.set_full_text(f"{n} selected" if n > 1 else (str(shown) if shown else ""))

    def show_panel(self, on: bool) -> None:
        """Open or close the Convert To panel on the right (it remembers for next time)."""
        self.dock.set_open(on)
        self.qs.setValue("panel_open", on)

    def _escape(self) -> None:
        """Esc (or a click on empty space in the list): nothing picked, and the panel slides away.
        While a row is being dragged, Esc puts it back instead."""
        if self.table.lifting():
            self.table.end_lift(drop=False)
            return
        self._select(set())
        self.show_panel(False)

    def resizeEvent(self, e) -> None:
        """The right panel gives up some width on a smaller window, so the toolbar never crowds."""
        super().resizeEvent(e)
        w = max(tokens.INSPECTOR_MIN, min(tokens.INSPECTOR_W, int(self.width() * tokens.INSPECTOR_SHARE)))
        self.dock.set_target(w)
        for i in range(self.inspector.count()):  # every right-hand panel, whatever it is
            self.inspector.widget(i).set_width(w)

    # ------------------------------------------------------------------ settings, look, feedback
    def open_settings(self, pane: str = "general") -> None:
        """Settings, at a section: general, shortcuts, data."""
        from listo.ui.dialogs.settings import SettingsDialog

        SettingsDialog(self, pane if isinstance(pane, str) else "general").exec()

    def auto_update(self) -> bool:
        """Check for updates on their own (Settings › General); on unless switched off."""
        return store.prefs().get("auto_update") is not False

    def set_look(self, appearance: str) -> None:
        """Light, Dark, or Match the System."""
        from listo.app import set_appearance

        store.save_pref("appearance", appearance)
        set_appearance(QApplication.instance(), appearance)

    def set_accent(self, key: str) -> None:
        """The accent color ("" or marigold, Listo's own: the default)."""
        from listo.app import set_appearance

        key = "" if key == tokens.APP_ACCENT or key not in tokens.ACCENTS else key
        store.save_pref("accent", key)
        app = QApplication.instance()
        set_appearance(app, getattr(app, "_appearance", "system"), key)

    def look_changed(self) -> None:
        """The colors changed: redraw what holds its own."""
        current = getattr(QApplication.instance(), "_appearance", "system")
        for k, a in getattr(self, "look_actions", {}).items():
            a.setChecked(k == current)
        self.sidebar.recolor()
        if self.titlebar is not None:
            self.titlebar.word.setText(theme.wordmark())
        self.table.viewport().update()
        self.root.update()

    def open_feedback(self) -> None:
        from listo.ui.dialogs.feedback import FeedbackDialog

        d = FeedbackDialog(self)
        if d.exec():
            self.toast.show_message(
                "Thanks! Sent."
                if d.sent_now
                else "Thanks! It's saved and goes out once sending is switched on."
            )

    def open_data_folder(self) -> None:
        d = data_dir()
        d.mkdir(parents=True, exist_ok=True)
        reveal(d)

    def back_up(self) -> None:
        """Your settings, recipes and checked captions, zipped where you pick."""
        start = store.documents_dir() / f"Listo Backup {time.strftime('%Y-%m-%d')}.zip"
        path, _ = QFileDialog.getSaveFileName(self, "Back Up", str(start), "Zip Files (*.zip)")
        if not path:
            return
        try:
            store.back_up(Path(path))
        except OSError:
            log.warning("back up failed", exc_info=True)
            notice(self, "Couldn't Back Up", "Listo couldn't write the backup there. Pick another folder.")
            return
        self.toast.show_message(f"Backed up to {Path(path).name}.")

    # ------------------------------------------------------------------ undo / redo
    def _step(self, what: str, undo, redo) -> None:
        if not self._history_busy:
            self.history.push(Step(what, undo, redo))

    def _record_settings(self) -> None:
        """A settings change has settled: one undo step for it (a change taken straight back leaves none)."""
        now, before = self.settings.to_dict(), self._settings_before
        if now == before:
            return
        last = self.history.last()
        if last is not None and last.kind == "settings" and last.data[0] == now:
            self.history.drop_last()  # changed straight back
        else:
            self.history.push(
                Step(
                    "the settings",
                    lambda: self._put_settings(before),
                    lambda: self._put_settings(now),
                    "settings",
                    (before, now),
                )
            )
        self._settings_before = now

    def _put_settings(self, values: dict) -> None:
        self._history_busy = True
        try:
            self.settings.apply(values)
            self.convert.reload()
            self.export_panel.reload()
            self._settings_changed()
            self._settings_before = self.settings.to_dict()
        finally:
            self._history_busy = False

    def _reordered(self, shown: list[int]) -> None:
        """A dragged row landed: the files showing are in this order now (the others keep their places)."""
        before = list(self.order)
        spots = [n for n, i in enumerate(before) if i in set(shown)]
        after = list(before)
        for n, iid in zip(spots, shown, strict=False):
            after[n] = iid
        if after == before:
            return
        self._put_order(after)
        self._step("the order", lambda: self._put_order(before), lambda: self._put_order(after))

    def _put_order(self, order: list[int]) -> None:
        self.order = [i for i in order if i in self.items] + [i for i in self.order if i not in set(order)]
        if self.running:
            self.batch.sort(key=lambda i: self.order.index(i) if i in self.items else len(self.order))
        log.info("list order changed")
        self._apply_filter()
        for it in self.items.values():
            if it.state in ("ready", "waiting"):
                self._update_output_name(it)  # a joined video is named after its first and last clip
        self._refresh_footer()
        self._schedule_live()

    def _text_widget(self):
        """The text box you're typing in, if any (it keeps its own undo, cut, copy and paste)."""
        w = QApplication.focusWidget()
        return w if isinstance(w, (QLineEdit, QPlainTextEdit)) else None

    def _text_can_undo(self, redo: bool = False) -> bool:
        w = self._text_widget()
        if isinstance(w, QLineEdit):
            return w.isRedoAvailable() if redo else w.isUndoAvailable()
        if w is not None:
            doc = w.document()
            return doc.isRedoAvailable() if redo else doc.isUndoAvailable()
        return False

    def undo(self) -> None:
        """⌘Z: in a text box, its typing; otherwise the last change to the settings or the list."""
        if self._text_can_undo():
            self._text_widget().undo()
            return
        self._settings_timer.stop()
        self._record_settings()  # a change still settling is the step to undo
        what = self.history.undo()
        self.toast.show_message(f"Undid the change to {what}." if what else "Nothing to undo.")

    def redo(self) -> None:
        if self._text_can_undo(redo=True):
            self._text_widget().redo()
            return
        what = self.history.redo()
        self.toast.show_message(f"Redid the change to {what}." if what else "Nothing to redo.")

    def _edit_menu_state(self) -> None:
        h = self.history
        self.act_undo.setEnabled(self._text_can_undo() or h.can_undo() or self._settings_timer.isActive())
        self.act_redo.setEnabled(self._text_can_undo(redo=True) or h.can_redo())

    # ------------------------------------------------------------------ updates (core/update.py)
    def _auto_check_updates(self) -> None:
        """Every launch, quietly, just after the window is up: if there's a newer Listo, the update window
        says so (and a button stays at the bottom of the sidebar). Not when running from the code (that's
        updated with git) or when switched off in Settings."""
        if self._shut_down() or update.install_kind() == "source" or os.environ.get("LISTO_NO_UPDATE_CHECK"):
            return
        if not self.auto_update():
            return
        known = str(self.qs.value("updates/latest", "") or "")
        if known and update.is_newer(known, __version__):
            self._show_update_button(known)  # found earlier; the window knows without asking again
        self.check_updates(quiet=True)

    def check_updates(self, quiet: bool = False) -> None:
        if self._upd_thread is not None and self._upd_thread.isRunning():
            return
        th = CheckThread(self)
        th.found.connect(lambda rel: self._update_found(rel, quiet))
        th.failed.connect(lambda msg: self._update_failed(quiet))
        self._upd_thread = th
        th.start()

    def _update_found(self, rel: update.Release, quiet: bool) -> None:
        self.latest = rel
        self.qs.setValue("updates/latest", rel.version)
        if rel.newer:
            self._show_update_button(rel.version)
            if quiet:
                self._offer_update()  # found on its own: say so right away (Later closes it, like any window)
            else:
                self.open_update()
        else:
            self.btn_update.hide()
            if not quiet:
                self.toast.show_message(f"You have the newest Listo ({__version__}).")

    def _update_failed(self, quiet: bool) -> None:
        if not quiet:
            self.toast.show_message("Couldn't reach GitHub. Check your internet and try again.")

    def _show_update_button(self, version: str) -> None:
        self.btn_update.setText(f"Update to {version}")
        self.btn_update.show()

    def _offer_update(self) -> None:
        """Show the update window once Listo is free: never on top of another window, an open menu, or a
        batch that's converting (it waits for that to finish)."""
        if self._shut_down() or self.latest is None or not self.latest.newer:
            return
        busy = QApplication.activeModalWidget() is not None or QApplication.activePopupWidget() is not None
        if busy or self.running or not self.isVisible():
            QTimer.singleShot(tokens.UPDATE_WAIT_MS, self._offer_update)
            return
        self.open_update()

    def open_update(self) -> None:
        if self.latest is None:  # known from an earlier day: fetch the details first
            self.check_updates()
            return
        dlg = UpdateDialog(self.latest, self._update_busy, self)
        if dlg.exec() and dlg.plan is not None:
            restart_into(dlg.plan)

    def _update_busy(self) -> str:
        if self.running:
            return "Finish or stop converting first, then restart."
        return ""

    def _shut_down(self) -> bool:
        return getattr(self, "_shut", False)

    def _storage_busy(self, key: str) -> str:
        if key in ("models", "captions") and self.tx is not None:
            return "Captions are being made right now. Try again when they're done."
        if key == "tools" and self.downloads:
            return "A link is downloading right now. Try again when it's done."
        return ""

    def _storage_cleared(self, key: str) -> None:
        """Forget what was deleted, so nothing points at missing files."""
        if key == "captions":
            for it in self.items.values():
                it.transcript = None
            self._tx_failed.clear()
            self._refresh_soon(captions=True)  # (with captions on, they're made again)
        elif key == "extras":
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(theme.stylesheet(data_dir() / "ui"))  # its images live there
            self._live_loaded = None
            self._schedule_live()

    def open_console(self) -> None:
        """A terminal window that follows Listo's log live (core/console.py)."""
        error = console.open_console()
        if error:
            self.toast.show_message(error)
        else:
            log.info("%d files in the list, %s", len(self.items), "converting" if self.running else "idle")

    def check_captions(self) -> None:
        """Check (watch and fix) the captions: the selected clips, or every clip that has them.
        Separate from Convert: Convert uses the captions as they are."""
        sel = [i for i in self.order if i in self.selected] or list(self.order)
        wanted = [self.items[i] for i in sel if self._wants_captions(self.items[i])]
        if not wanted:
            self.toast.show_message("Turn on Captions (in Burn-In) and add a video with sound first.")
            return
        ready = [it for it in wanted if it.transcript is not None]
        if not ready:
            self.toast.show_message("Still making the captions. The button lights up when they're ready.")
            return
        start = next((n for n, it in enumerate(ready) if not it.transcript.reviewed), 0)
        clips = [(Path(it.path).name, it.path, it.info, self.eff(it), it.transcript) for it in ready]
        CaptionEditor(clips, start, "Done", self).exec()
        self._sync_captions()
        self._schedule_live()

    def _update_check_button(self) -> None:
        wanted = [it for it in self.items.values() if self._wants_captions(it)]
        self.btn_check.setVisible(bool(wanted) and not self.running)
        ready = [it for it in wanted if it.transcript is not None]
        new = sum(1 for it in ready if not it.transcript.reviewed)
        making = len(wanted) - len(ready) - sum(1 for it in wanted if it.id in self._tx_failed)
        self.btn_check.setEnabled(bool(ready))
        if not ready and making:
            self.btn_check.setText("Making Captions…")
        elif new:
            self.btn_check.setText(f"Check Captions · {new} New")
        else:
            self.btn_check.setText("Check Captions")

    def _show_log(self) -> None:
        from listo.core.fileutil import reveal
        from listo.core.paths import log_dir

        reveal(str(log_dir() / "listo.log"))

    # ------------------------------------------------------------------ links
    def ask_link(self) -> None:
        clip = QApplication.clipboard().text().strip()
        dlg = QDialog(self)
        dlg.setWindowTitle("Add a Link")
        dlg.setFixedWidth(tokens.DIALOG_W)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(*(tokens.SPACE_5,) * 4)
        lay.setSpacing(tokens.SPACE_3)
        t = QLabel("Add a Link")
        t.setObjectName("DialogTitle")
        lay.addWidget(t)
        edit_ = QLineEdit(clip if is_link(clip) else "")
        edit_.setPlaceholderText("Paste a video link — YouTube, Vimeo, Instagram…")
        lay.addWidget(edit_)
        lay.addWidget(hint("Only download videos you have the rights to use. Saved to Downloads › Listo."))
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dlg.reject)
        ok = QPushButton("Add")
        ok.setObjectName("Primary")
        ok.setDefault(True)
        ok.clicked.connect(dlg.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        edit_.selectAll()
        if dlg.exec() == QDialog.DialogCode.Accepted:
            links = [w for w in edit_.text().split() if is_link(w)]
            if links:
                self.add_links(links)
            elif edit_.text().strip():
                self.toast.show_message("That doesn't look like a link.")

    def _paste(self) -> None:
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit):
            focus.paste()
            return
        md = QApplication.clipboard().mimeData()
        local = [u.toLocalFile() for u in md.urls() if u.isLocalFile()] if md and md.hasUrls() else []
        if local:
            self.add_paths(local)
            return
        links = [w for w in QApplication.clipboard().text().split() if is_link(w)]
        if links:
            self.add_links(links)

    def add_links(self, urls: list[str]) -> None:
        have = {it.url for it in self.items.values() if it.url}
        fresh = []
        for url in urls:
            url = url.strip()
            if url in have:
                continue
            have.add(url)
            fresh.append(url)
        if fresh:
            self._auto_clear()
        added = 0
        for url in fresh:
            iid = self._new_card(url, "link", display=_short_url(url))
            it = self.items[iid]
            it.url = url
            self._start_download(it)
            added += 1
        if not added:
            self.toast.show_message("That link is already in the list.")
        self._refresh_footer()

    def _start_download(self, it: Item) -> None:
        it.state = "downloading"
        it.card.set_state("downloading", "Starting…")
        it.card.set_progress(0)
        th = DownloadThread(it.id, it.url)
        th.progress.connect(self._dl_progress)
        th.titled.connect(self._dl_titled)
        th.done.connect(self._dl_done)
        self.downloads[it.id] = th
        th.start()

    def _dl_progress(self, iid: int, frac: float, text: str) -> None:
        it = self.items.get(iid)
        if not it or it.state != "downloading":
            return
        if frac >= 0:
            it.card.set_progress(frac)
        it.card.set_state("downloading", text if len(text) < 34 else text[:32] + "…")
        if frac < 0:
            it.card.set_meta(text)

    def _dl_titled(self, iid: int, title: str) -> None:
        it = self.items.get(iid)
        if it and title:
            it.card.set_name(title)
            it.card.set_meta(_short_url(it.url))

    def _dl_done(self, iid: int, path: str, error: str) -> None:
        th = self.downloads.pop(iid, None)
        if th:
            th.wait(2000)
            th.deleteLater()
        it = self.items.get(iid)
        if not it:
            return
        if error:
            log.warning("download failed: %s — %s", it.url, error)
            it.state = "failed"
            it.message = error
            it.card.set_state("failed", "Download Failed" if error != "Canceled" else "Canceled")
            it.card.set_output(error)
        else:
            it.path = path
            it.kind = kind_from_ext(path)
            it.card.kind = it.kind
            it.card.set_name(Path(path).name)
            it.state = "probing"
            it.card.set_state("probing")
            it.card.set_progress(0)
            self.pool.start(ProbeTask(iid, path, self.probe_signals))
        self._refresh_footer()
        if self.running:
            self._kick()

    # ------------------------------------------------------------------ trim
    def trim_item(self, iid: int) -> None:
        it = self.items.get(iid)
        if not it or not it.info or it.state not in ("ready", "waiting") or it.kind not in ("video", "audio"):
            return
        if not it.info.duration:
            self.toast.show_message("Listo can't tell how long this file is, so it can't be trimmed.")
            return
        dlg = TrimDialog(it.path, it.info, it.trim, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and it.state in ("ready", "waiting"):
            before, after = it.trim, dlg.result_trim
            if after == before:
                return
            self._put_trim(iid, after)
            self._step(
                f"{Path(it.path).name}'s trim",
                lambda: self._put_trim(iid, before),
                lambda: self._put_trim(iid, after),
            )

    def _put_trim(self, iid: int, trim: tuple[float, float] | None) -> None:
        it = self.items.get(iid)
        if it is None or it.state not in ("ready", "waiting"):
            return
        it.trim = trim
        it.card.set_trim(f"✂ {fmt_time(trim[0])}–{fmt_time(trim[1])}" if trim else "")
        self._refresh_footer()
        self._schedule_live()

    # ------------------------------------------------------------------ adding files
    def pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Add Files", self._last_dir())
        if files:
            self._remember_dir(files[0])
            self.add_paths(files)

    def pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Add a Folder", self._last_dir())
        if d:
            self._remember_dir(d)
            self.add_paths([d])

    def _last_dir(self) -> str:
        return str(self.qs.value("last_dir", str(Path.home())))

    def _remember_dir(self, p: str) -> None:
        self.qs.setValue("last_dir", str(Path(p).parent if Path(p).is_file() else p))

    def _auto_clear(self) -> None:
        """Adding new things after a batch clears the files that went fine (problems stay)."""
        self._show_summary = False
        self.btn_show.hide()
        if self.running:
            return
        self._take_off([i for i in self.order if self.items[i].state in ("done", "skipped")], record=False)

    def add_paths(self, paths: list[str]) -> None:
        existing = {naming.reserve_key(Path(it.path)) for it in self.items.values()}
        added = dupes = skipped = 0
        to_add: list[tuple[str, bool]] = []
        for p in paths:
            pp = Path(p)
            if pp.is_dir():
                for root, dirs, files in os.walk(pp):
                    dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                    for fn in sorted(files):
                        if fn.startswith("."):
                            continue
                        if ext_of(fn) in KNOWN_EXTS:
                            to_add.append((os.path.join(root, fn), False))
                        elif ext_of(fn) not in SIDECAR_EXTS:  # camera sidecars are read, not listed
                            skipped += 1
            elif pp.is_file() and ext_of(pp) not in SIDECAR_EXTS:
                to_add.append((str(pp), True))
        fresh = []
        for path, _explicit in to_add:
            key = naming.reserve_key(Path(path))
            if key in existing:
                dupes += 1
                continue
            existing.add(key)
            fresh.append(path)
        if any(ext_of(p) in KNOWN_EXTS for p in fresh):
            self._auto_clear()
        for path in fresh:
            self._add_item(path)
            added += 1
        msgs = []
        if dupes:
            msgs.append(f"{dupes} already in the list")
        if skipped:
            msgs.append(
                f"skipped {skipped} file{'s' if skipped != 1 else ''} that "
                f"{'aren' if skipped != 1 else 'isn'}'t video, photo or audio"
            )
        if added:
            self._show_summary = False
            log.info("added %d file%s to the list", added, "s" if added != 1 else "")
        if msgs:
            self.toast.show_message(
                (f"Added {added}. " if added else "") + "; ".join(msgs).capitalize() + "."
            )
        self._refresh_footer()
        if self.running:
            self._kick()

    def _new_card(self, path: str, kind: str, display: str = "") -> int:
        iid = self._next_id
        self._next_id += 1
        it = Item(iid, path, kind)
        it.card = Row(iid, display or Path(path).name, kind)
        self.items[iid] = it
        self.order.append(iid)
        self.table.add_row(it.card, shown=self._shown(it))
        if len(self.items) == 1:
            self._show_page()
            if not self.dock.opened:
                self.show_panel(True)  # the first file in: Convert To slides in beside it
        return iid

    def _add_item(self, path: str) -> None:
        kind = kind_from_ext(path)
        if self.running:
            self.reserved.add(naming.reserve_key(Path(path)))
        iid = self._new_card(path, kind)
        it, card = self.items[iid], self.items[iid].card
        if kind == "unknown":
            e = ext_of(path)
            it.state = "unsupported"
            it.message = UNSUPPORTED_HINTS.get(e, f"Listo doesn't know .{e or '?'} files.")
            card.set_meta(it.message)
            card.set_state("unsupported")
            return
        if self.running:
            it.state = "probing"
        self.pool.start(ProbeTask(iid, path, self.probe_signals))

    def _probed(self, iid: int, info: MediaInfo, thumb: bytes) -> None:
        it = self.items.get(iid)
        if not it:
            return
        if self.running:
            self.reserved.add(naming.reserve_key(Path(it.path)))
        it.info = info
        it.kind = info.kind if info.kind != "unknown" else it.kind
        card = it.card
        card.kind = it.kind
        card.set_thumb(thumb)
        if info.error or info.kind == "unknown":
            it.state = "unsupported"
            it.message = info.error or "Listo can't read this file."
            card.set_meta(it.message)
            card.set_state("unsupported")
        else:
            bits = info.summary_bits()
            if info.hdr:
                bits.append(info.hdr_label)
            card.set_meta("  ·  ".join(bits))
            it.state = "waiting" if (self.running and iid in self.batch) else "ready"
            card.set_state(it.state)
            self._update_output_name(it)
            if it.kind == "video" and info.audio:
                it.transcript = captions.load(it.path)
        self._refresh_soon(captions=True)
        if self.running:
            self._kick()

    # ------------------------------------------------------------------ captions
    def _wants_captions(self, it: Item) -> bool:
        return (
            it.kind == "video" and it.info is not None and bool(it.info.audio) and self._base(it).captions
            and it.state in ("ready", "waiting", "done", "warning")
        )  # fmt: skip

    def _made_differently(self, it: Item) -> bool:
        """These captions came from another accuracy setting or language than the one chosen now."""
        t, s = it.transcript, self._base(it)
        if t is None:
            return False
        model = captions.MODELS.get(s.caption_model, captions.MODELS["balanced"])[0]
        wrong_model = bool(t.model) and t.model != model
        wrong_language = (
            s.caption_language != "auto" and bool(t.language) and t.language != s.caption_language
        )
        return wrong_model or wrong_language

    def _needs_redo(self, it: Item) -> bool:
        """Redo in the background: made differently, not hand-edited (unless you said to), not failed."""
        return (
            self._made_differently(it)
            and (not it.transcript.edited or it.id in self._redo_edited)
            and it.id not in self._tx_failed
        )

    def _caption_choice_changed(self) -> None:
        """Accuracy or language changed: redo captions made the other way. Hand-edited ones ask first."""
        key = (self.settings.caption_model, self.settings.caption_language)
        if key == self._caption_choice:
            return
        self._caption_choice = key
        if self.tx is not None:  # clips queued with the old choice: start over with the new one
            self._tx_retry = True
            self.tx.cancel()
        edited = [
            it for it in self.items.values()
            if self._wants_captions(it) and it.transcript is not None and it.transcript.edited
            and self._made_differently(it) and it.id not in self._redo_edited
        ]  # fmt: skip
        if edited:
            n = len(edited)
            if confirm(
                self,
                "Redo Edited Captions?",
                f"You fixed the captions of {n} clip{'s' if n != 1 else ''} by hand. Redo "
                f"{'them' if n != 1 else 'it'} with the new setting too? Your fixes would be replaced.",
                "Redo",
            ):
                self._redo_edited.update(it.id for it in edited)

    def _sync_captions(self) -> None:
        """CC icon on each clip, and quietly start making any captions that are missing (or redo
        ones made with another accuracy / language)."""
        queued = self.tx.queued() if self.tx is not None else set()
        missing = []
        for it in self.items.values():
            if not self._wants_captions(it):
                it.card.set_captions("")
            elif self._needs_redo(it):
                pct = self._tx_pct.get(it.id)
                it.card.set_captions(
                    "working",
                    "Redoing captions with the new setting…" + (f" {int(pct * 100)}%" if pct else ""),
                )
                if it.id not in queued:
                    missing.append(it)
            elif it.transcript is not None:
                silent = not any(c.text.strip() for c in it.transcript.cues)
                it.card.set_captions(
                    "reviewed" if it.transcript.reviewed else "review",
                    "No speech heard in this clip" if silent else "",
                )
            elif it.id in self._tx_failed:
                it.card.set_captions("failed", self._tx_failed[it.id])
            else:
                pct = self._tx_pct.get(it.id)
                it.card.set_captions(
                    "working", f"Making captions in the background… {int(pct * 100)}%" if pct else ""
                )
                if it.id not in queued:
                    missing.append(it)
        if missing:
            self._queue_captions(missing)
        if self.tx is not None and not any(self._wants_captions(it) for it in self.items.values()):
            self.tx.cancel()  # captions switched off: stop listening
        self._update_check_button()

    def _queue_captions(self, items: list[Item]) -> None:
        jobs = [(it.id, it.path, it.info, self.eff(it)) for it in items]
        if self.tx is not None and all(self.tx.add(j) for j in jobs):
            return
        if self.tx is not None:  # it was finishing: pick these up again when it's done
            self._tx_retry = True
            return
        self.tx = TranscribeThread(jobs)
        self.tx.progress.connect(self._tx_progress)
        self.tx.status.connect(self._tx_status)
        self.tx.done.connect(self._tx_done)
        self.tx.finished.connect(self._tx_finished)
        self.tx.start(QThread.Priority.LowestPriority)  # never in the way of the app or conversions

    def _tx_progress(self, iid: int, frac: float) -> None:
        self._tx_pct[iid] = frac
        it = self.items.get(iid)
        if it and (it.transcript is None or self._needs_redo(it)):
            verb = "Making" if it.transcript is None else "Redoing"
            it.card.set_captions("working", f"{verb} captions in the background… {int(frac * 100)}%")

    def _tx_status(self, iid: int, msg: str) -> None:
        it = self.items.get(iid)
        if it and (it.transcript is None or self._needs_redo(it)):
            it.card.set_captions("working", msg)

    def _tx_done(self, iid: int, transcript, error: str) -> None:
        self._tx_pct.pop(iid, None)
        it = self.items.get(iid)
        if not it:
            return
        if transcript is not None:
            it.transcript = transcript
            self._redo_edited.discard(iid)
            if it is self._live_clip():
                self._schedule_live()
        elif error and error != "Canceled":
            self._tx_failed[iid] = error
        self._refresh_soon(captions=True)

    def _tx_finished(self) -> None:
        self.tx = None
        retry, self._tx_retry = self._tx_retry, False
        if retry:
            self._sync_captions()
        if self._convert_after_captions and self.tx is None:
            self._convert_after_captions = False
            self.start()
        self._refresh_footer()

    def _captions_ready(self) -> bool:
        """Before converting: every clip that gets captions must have them, checked. False = not yet."""
        todo = [
            self.items[i]
            for i in self.order
            if self.items[i].state == "ready" and self._wants_captions(self.items[i])
        ]
        making = [it for it in todo if it.transcript is None and it.id not in self._tx_failed]
        if making:
            self._convert_after_captions = True
            self._sync_captions()
            n = len(making)
            self.toast.show_message(
                f"Still making captions for {n} clip{'s' if n != 1 else ''}. "
                "Listo converts as soon as they're ready."
            )
            self._refresh_footer()
            return False
        return True

    def open_captions(self, iid: int) -> None:
        it = self.items.get(iid)
        if not it:
            return
        if it.transcript is not None:
            self._edit_captions([it], "Done")
        elif iid in self._tx_failed:
            self._tx_failed.pop(iid)  # try again
            self._sync_captions()
            self.toast.show_message("Trying the captions for this clip again.")
        else:
            pct = self._tx_pct.get(iid)
            self.toast.show_message(
                "Still making captions for this clip" + (f" ({int(pct * 100)}%)." if pct else ".")
            )

    def _edit_captions(self, items: list[Item], action: str) -> bool:
        clips = [(Path(it.path).name, it.path, it.info, self.eff(it), it.transcript) for it in items]
        ok = CaptionEditor(clips, 0, action, self).exec() == QDialog.DialogCode.Accepted
        self._sync_captions()
        return ok

    @staticmethod
    def _previewable(it: Item) -> bool:
        return (
            it.kind == "video"
            and it.info is not None
            and it.info.video_index is not None
            and not it.info.error
        )

    # ------------------------------------------------------------------ live preview
    def _schedule_live(self) -> None:
        self._live_timer.start()

    def _live_clip(self) -> Item | None:
        clips = [self.items[i] for i in self.order if self._previewable(self.items[i])]
        return next((it for it in clips if it.id in self.selected), clips[0] if clips else None)

    def _clip_cues(self, it: Item | None, s: Settings):
        if not s.captions:
            return None
        if it is not None and it.transcript is not None:
            return it.transcript.cues_for(s.caption_words, s.caption_lines)
        return sample_cues(s.caption_words, s.caption_lines)  # shows the look before the words exist

    def _render_live(self) -> None:
        """Settings or the list changed: (re)load the Export preview's clip, then show the exact
        result where it's paused. While it plays, the new look shows when it pauses."""
        it = self._live_clip()
        player = self.export_panel.player
        if it is None:
            s, path, info = self.settings, sample_clip_if_made(), None
            key: object = ("sample",)
            at, rng = 0.0, None
            if path:
                info = self._sample_info(path)
        else:
            s, path, info = self.eff(it), it.path, it.info
            key = (it.id, it.trim)
            start, length = (it.trim[0], it.trim[1] - it.trim[0]) if it.trim else (0.0, info.duration)
            rng = (start, start + length) if it.trim else None
            at = start  # players open on the first frame (of the trimmed part)
        cues = self._clip_cues(it, s)
        clips = [c for c in (self.items[i] for i in self.order) if self._previewable(c)]
        n = clips.index(it) if it in clips else -1
        player.set_steps(n > 0, 0 <= n < len(clips) - 1)
        if key != self._live_loaded and path and info is not None:
            self._live_loaded = key
            play, self._live_play_next = self._live_play_next, False
            player.load(path, info, s, at, play=play, range_=rng)
        elif key == self._live_loaded:
            at = player.position()
        player.set_settings(s)
        player.set_cues(cues)
        if not player.is_playing():
            self._live_render_at(at)

    def _live_render_at(self, at: float) -> None:
        it = self._live_clip()
        self._live_seq += 1
        self._live_at = at
        if it is None:
            s, path, info = self.settings, "", None
            self._live_note = "Sample picture — add a clip to see yours"
        else:
            s, path, info = self.eff(it), it.path, it.info
            heard = ""
            if (
                s.captions
                and it.transcript is not None
                and not any(c.text.strip() for c in it.transcript.cues)
            ):
                heard = " · No speech heard in this clip"
            self._live_note = f"{Path(it.path).name} · {fmt_duration(at)}{heard}"
        self.pool.start(
            PreviewTask(
                self._live_seq,
                path,
                info,
                s,
                at,
                False,
                self._live_signals,
                captions=self._clip_cues(it, s),
                clock=self._clocks().get(it.id) if it is not None else None,
            )
        )

    def _live_step(self, direction: int) -> None:
        """The Export preview's arrows: select the previous / next clip in the list and show it."""
        clips = [c for c in (self.items[i] for i in self.order) if self._previewable(c)]
        cur = self._live_clip()
        if cur not in clips:
            return
        n = clips.index(cur) + direction
        if 0 <= n < len(clips):
            self._live_play_next = self.export_panel.player.is_playing()
            self.export_panel.player.pause()
            self._select({clips[n].id})
            self._anchor = clips[n].id
            self._scroll_to(clips[n].id)
            self._live_timer.stop()
            self._render_live()  # at once: an arrow press shouldn't wait

    def _live_settled(self, at: float) -> None:
        """The Export preview was paused or moved: show the exact result there."""
        if self._live_loaded is not None:
            self._live_render_at(at)

    def _sample_info(self, path: str) -> MediaInfo:
        if self._sample_probe is None or self._sample_probe[0] != path:
            self._sample_probe = (path, probe(path))
        return self._sample_probe[1]

    def _live_got(self, seq: int, data: bytes, error: str) -> None:
        if seq == self._live_seq:
            self.export_panel.show_preview(data, self._live_note if data else error, self._live_at)
            if self._live_clip() is None and self._live_loaded != ("sample",) and sample_clip_if_made():
                self._render_live()  # the sample clip exists now: load it so it can play

    def play_item(self, iid: int) -> None:
        """Double-click a clip: play it (in the Preview window, with sound)."""
        it = self.items.get(iid)
        if it is None or not self._previewable(it):
            return
        self.export_panel.player.pause()
        clips = [self.items[i] for i in self.order if self._previewable(self.items[i])]
        clocks = self._clocks()
        PreviewDialog(
            [
                (
                    Path(c.path).name,
                    c.path,
                    c.info,
                    self.eff(c),
                    self._clip_cues(c, self.eff(c)),
                    clocks.get(c.id),
                )
                for c in clips
            ],
            clips.index(it),
            self,
            play=True,
        ).exec()

    def open_preview(self) -> None:
        self.export_panel.player.pause()  # one thing playing at a time
        clips = [self.items[i] for i in self.order if self._previewable(self.items[i])]
        if not clips:
            sample = sample_clip()
            if sample:
                s = self.settings
                PreviewDialog(
                    [("Sample picture", sample, probe(sample), s, self._clip_cues(None, s), None)], 0, self
                ).exec()
            return
        start = next((n for n, it in enumerate(clips) if it.id in self.selected), 0)
        clocks = self._clocks()
        PreviewDialog(
            [
                (
                    Path(it.path).name,
                    it.path,
                    it.info,
                    self.eff(it),
                    self._clip_cues(it, self.eff(it)),
                    clocks.get(it.id),
                )
                for it in clips
            ],
            start,
            self,
        ).exec()

    def _base(self, it: Item) -> Settings:
        """The file's settings without its format change, NOT a copy: only for reading settings a
        per-file format change can't touch (captions, burn-ins…), in loops over the whole list."""
        return it.base or self.settings

    def eff(self, it: Item) -> Settings:
        """The settings this file will actually convert with."""
        return (it.base or self.settings).with_override(it.override)

    def _update_output_name(self, it: Item) -> None:
        if (
            not it.info
            or it.state in ("unsupported",)
            or (it.state in FINAL and it.result and it.result.output)
        ):
            return
        s = self.eff(it)
        it.card.set_format(format_label(it.kind, s), bool(it.override), it.state in ("ready", "waiting"))
        if self.export_panel.joining() and it.kind == "video" and it.state in ("ready", "waiting"):
            vids = [self.items[i] for i in self.order if self.items[i].kind == "video" and self.items[i].info]
            first, last = (vids[0], vids[-1]) if vids else (it, it)
            name = join.joined_name(first.path, first.info, self.settings, last.path)
            it.card.set_output(f"→  {name}  (joined)")
            return
        try:
            out_dir = naming.output_dir(it.path, s, it.kind)
            name = naming.planned_name(it.path, it.info, s, it.kind, 1)
            target, _ = naming.resolve_output(it.path, out_dir / name, s.collision, set())
            same = Path(out_dir) == Path(it.path).parent
            where = "" if same else f"{out_dir.name}/"
            if target is None:
                it.card.set_output(f"→  {where}{name}  (exists — will be skipped)")
            else:
                it.card.set_output(f"→  {where}{target.name}")
        except Exception:
            log.debug("output preview failed", exc_info=True)

    def _update_sample(self) -> None:
        for iid in self.order:
            it = self.items[iid]
            if it.info and it.state not in ("unsupported",):
                self.export_panel.set_sample(it.path, it.info, it.kind)
                return
        self.export_panel.set_sample(None, None, "video")

    def _settings_changed(self) -> None:

        self.convert.notify_external_change()
        self.export_panel.refresh()
        self.qs.setValue("settings", self.settings.to_dict())
        self._schedule_live()
        for it in self.items.values():
            if it.state in ("ready", "waiting"):
                self._update_output_name(it)
        self._caption_choice_changed()
        self._sync_captions()
        self._refresh_footer()  # "Convert & Join" on the button
        if not self._history_busy:
            self._settings_timer.start()

    def _format_menu(self, iid: int, at: QPoint) -> None:
        it = self.items.get(iid)
        if not it or it.state not in ("ready", "waiting"):
            return
        s = self.eff(it)
        m = QMenu(self)
        group = QActionGroup(m)

        def add(menu: QMenu, label: str, override: dict, checked: bool) -> None:
            a = menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(checked)
            group.addAction(a)
            a.triggered.connect(lambda _=False, o=override: self._set_override(iid, o))

        add(m, "Same as the Panel", {}, not it.override)
        if it.kind == "video":
            m.addSeparator()
            for p in VIDEO_PRESETS:
                if p.needs and not all(self.caps.has_encoder(e) for e in p.needs):
                    continue
                if p.key in ("prores", "dnxhr"):
                    sub = m.addMenu(p.title)
                    for c in p.variants:
                        add(
                            sub,
                            c.label,
                            {"video_preset": p.key, "video_variant": {p.key: c.key}},
                            bool(it.override) and s.video_preset == p.key and s.variant_for(p.key) == c.key,
                        )
                else:
                    add(m, p.title, {"video_preset": p.key}, bool(it.override) and s.video_preset == p.key)
        elif it.kind == "photo":
            m.addSeparator()
            for f in PHOTO_FORMATS:
                add(m, f.title, {"photo_format": f.key}, bool(it.override) and s.photo_format == f.key)
        elif it.kind == "audio":
            m.addSeparator()
            for f in AUDIO_FORMATS:
                add(m, f.title, {"audio_format": f.key}, bool(it.override) and s.audio_format == f.key)
        m.exec(at + QPoint(0, tokens.MENU_GAP))

    def _set_override(self, iid: int, override: dict) -> None:
        it = self.items.get(iid)
        if not it or it.state not in ("ready", "waiting"):
            return
        before = dict(it.override)
        after = {k: v for k, v in override.items() if k in OVERRIDE_KEYS}
        if after == before:
            return
        self._put_override(iid, after)
        self._step(
            f"{Path(it.path).name}'s format",
            lambda: self._put_override(iid, before),
            lambda: self._put_override(iid, after),
        )

    def _put_override(self, iid: int, override: dict) -> None:
        it = self.items.get(iid)
        if it is not None and it.state in ("ready", "waiting"):
            it.override = dict(override)
            self._update_output_name(it)
            self._schedule_live()

    # ------------------------------------------------------------------ list actions
    def remove_item(self, iid: int) -> None:
        """Take one file off the list (never off the disk). ⌘Z puts it back."""
        self._take_off([iid])

    def _take_off(self, ids: list[int], record: bool = True) -> None:
        """Take files off the list in one go (files converting right now stay). One undo step."""
        gone: list[tuple[int, Item]] = []
        for iid in ids:
            it = self.items.get(iid)
            if not it or iid in self.active:
                continue
            gone.append((self.order.index(iid), it))
            if iid in self.downloads:
                self.downloads[iid].job.cancel()  # its thread finishes on its own
            self.table.drop_row(iid)
            del self.items[iid]
            self.order.remove(iid)
            if iid in self.batch:
                self.batch.remove(iid)
        if not gone:
            return
        self.selected -= {it.id for _n, it in gone}
        self._show_page()
        self._update_sample()
        self._refresh_footer()
        if self.running:
            self._kick()
        if record:
            n = len(gone)
            names = Path(gone[0][1].path).name if n == 1 else f"{n} files"
            again = [it.id for _n, it in gone]
            self._step(
                f"taking {names} off the list",
                lambda: self._put_back(gone),
                lambda: self._take_off(again, False),
            )

    def _put_back(self, gone: list[tuple[int, Item]]) -> None:
        """Undo taking files off the list: each goes back where it was."""
        for index, it in sorted(gone, key=lambda g: g[0]):
            if it.id in self.items:
                continue
            if it.state == "downloading":  # its download stopped when it went: try again from its row
                it.state, it.message = "failed", "Canceled"
                it.card.set_state("failed", "Canceled")
            elif it.state == "waiting" and not self.running:
                it.state, it.base = "ready", None
                it.card.set_state("ready")
            self.items[it.id] = it
            self.order.insert(min(index, len(self.order)), it.id)
            self.table.add_row(it.card, shown=False)
            if self.running and it.state == "waiting" and it.id not in self.batch:
                self.batch.append(it.id)
        self._apply_filter()
        self._update_sample()
        self._refresh_soon(captions=True)
        self._refresh_footer()
        if self.running:
            self._kick()

    def retry_item(self, iid: int) -> None:
        it = self.items.get(iid)
        if it and it.url and not it.info and iid not in self.downloads:
            it.message = ""
            self._start_download(it)  # the download itself failed: try it again
            if self.running and iid not in self.batch:
                self.batch.append(iid)
            self._refresh_footer()
            return
        if not it or not it.info:
            return
        it.result, it.processed, it.message, it.base, it.clock = None, 0.0, "", None, None
        it.state = "waiting" if self.running else "ready"
        if self.running and iid not in self.batch:
            self.batch.append(iid)
        it.card.set_state(it.state)
        it.card.set_progress(0)
        self._update_output_name(it)
        self._refresh_footer()
        if self.running:
            self._kick()

    def reveal_item(self, iid: int) -> None:
        it = self.items.get(iid)
        if it and it.result and it.result.output:
            reveal(it.result.output)

    def show_details(self, iid: int) -> None:
        it = self.items.get(iid)
        if not it:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(Path(it.path).name)
        dlg.resize(*tokens.DETAILS_SIZE)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(*(tokens.SPACE_5,) * 4)
        lay.setSpacing(tokens.SPACE_3)
        r = it.result
        title = {
            "done": "Converted",
            "failed": "This one didn't convert",
            "skipped": "Skipped",
            "warning": "Converted — but double-check it",
            "unsupported": "Can't Convert This File",
        }.get(it.state, it.state.title())
        t = QLabel(title)
        t.setObjectName("DialogTitle")
        lay.addWidget(t)
        lines = [f"From: {it.path}"]
        if r and r.output:
            lines.append(f"To:   {r.output}")
        if r and r.warning:
            lines += ["", "⚠ " + r.warning]
        if it.message:
            lines.append("")
            lines.append(it.message)
        if r and r.notes:
            lines += ["", *r.notes]
        msg = QLabel("\n".join(lines))
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(msg)
        if r and (r.log or r.command):
            log = QPlainTextEdit()
            log.setReadOnly(True)
            text = ""
            if r.command:
                text += "$ " + " ".join(_quote(a) for a in r.command) + "\n\n"
            text += r.log
            log.setPlainText(text)
            lay.addWidget(log, 1)
        else:
            lay.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        if r and (r.log or r.command):
            copy = bb.addButton("Copy Details", QDialogButtonBox.ButtonRole.ActionRole)
            copy.clicked.connect(
                lambda: QApplication.clipboard().setText(
                    "\n".join(lines) + "\n\n" + (log.toPlainText() if r.log or r.command else "")
                )
            )
        lay.addWidget(bb)
        dlg.exec()

    def clear_finished(self) -> None:
        self._take_off([i for i in self.order if self.items[i].state in FINAL])

    def clear_all(self) -> None:
        ids = [i for i in self.order if i not in self.active]
        if len(ids) > 1 and not confirm(
            self, "Clear the List?", f"{len(ids)} files. The files themselves stay where they are.", "Clear"
        ):
            return
        self._take_off(ids)

    # ------------------------------------------------------------------ selection
    def _select(self, ids: set[int]) -> None:
        if {i for i in ids if i in self.items} != self.selected:
            self._schedule_live()
        self.selected = {i for i in ids if i in self.items}
        for iid, it in self.items.items():
            it.card.set_selected(iid in self.selected)
        self._show_count()

    def _card_pressed(self, iid: int, mods) -> None:
        self.table.setFocus()  # so Delete / Backspace reach the list, not a text field
        shown = self.table.shown_ids()
        if mods & Qt.KeyboardModifier.ShiftModifier and self._anchor in shown and iid in shown:
            a, b = sorted((shown.index(self._anchor), shown.index(iid)))
            self._select(self.selected | set(shown[a : b + 1]))
            return
        if mods & Qt.KeyboardModifier.ControlModifier:  # Cmd on a Mac, Ctrl elsewhere
            self._select(self.selected ^ {iid})
        else:
            self._select({iid})
            if not self.dock.opened:
                self.show_panel(True)  # picking a file brings Convert To back
        self._anchor = iid

    def _step_pick(self, direction: int, mods) -> None:
        """↑ / ↓ in the list: pick the file above or below (Shift adds it to what's picked)."""
        shown = self.table.shown_ids()
        if not shown:
            return
        at = self._anchor if self._anchor in shown else None
        n = 0 if at is None else max(0, min(len(shown) - 1, shown.index(at) + direction))
        iid = shown[n]
        if mods & Qt.KeyboardModifier.ShiftModifier:
            self._select(self.selected | {iid})
        else:
            self._select({iid})
        self._anchor = iid
        self.table.scroll_to(iid)

    def select_all(self) -> None:
        """⌘A: every file showing."""
        self._select(set(self.table.shown_ids()))

    def remove_selected(self) -> None:
        """Delete / Backspace: take what's picked off the list, after an alert that names it (files converting
        right now stay)."""
        ids = [i for i in self.order if i in self.selected and i not in self.active]
        if not ids:
            return
        name = Path(self.items[ids[0]].path).name
        what = name if len(ids) == 1 else f"{len(ids)} Files"
        if confirm(
            self, f"Remove {what} from the List?", "The files themselves stay where they are.", "Remove"
        ):
            self._take_off(ids)

    def _list_menu(self, iid: int) -> QMenu:
        """Right-click: what can be done with this file (or what's picked), then clearing the list.
        Removing only takes files off the list, never off the disk."""
        m = QMenu(self)
        it = self.items.get(iid)
        if it is not None:
            if iid not in self.selected:
                self._select({iid})
                self._anchor = iid
            s = it.state
            if self._previewable(it):
                m.addAction(theme.menu_icon("play"), "Play", lambda: self.play_item(iid))
            if s in ("ready", "waiting") and it.info is not None:
                m.addAction(
                    theme.menu_icon("film"),
                    "Change the Format…",
                    lambda: self._format_menu(iid, self.cursor().pos()),
                )
                if it.kind in ("video", "audio"):
                    m.addAction(theme.menu_icon("scissors"), "Trim…", lambda: self.trim_item(iid))
            if it.card.cc[0]:
                m.addAction(theme.menu_icon("captions"), "Captions…", lambda: self.open_captions(iid))
            if s in ("done", "warning"):
                m.addAction(theme.menu_icon("reveal"), "Show the New File", lambda: self.reveal_item(iid))
            if s in ("failed", "done", "skipped", "unsupported", "warning"):
                m.addAction(theme.menu_icon("info"), "Details…", lambda: self.show_details(iid))
            if s in ("failed", "canceled", "skipped", "warning"):
                m.addAction(theme.menu_icon("retry"), "Try Again", lambda: self.retry_item(iid))
            if not m.isEmpty():
                m.addSeparator()
        n = sum(1 for i in self.selected if i not in self.active)
        a = m.addAction(
            theme.menu_icon("x"),
            f"Remove {n} from the List…" if n > 1 else "Remove from the List…",
            self.remove_selected,
        )
        a.setEnabled(n > 0)
        finished = sum(1 for it in self.items.values() if it.state in FINAL)
        a = m.addAction(theme.menu_icon("check"), "Clear Finished", self.clear_finished)
        a.setEnabled(finished > 0)
        a = m.addAction(theme.menu_icon("list-x"), "Clear All…", self.clear_all)
        a.setEnabled(bool(self.items))
        return m

    def _row_menu(self, iid: int, pos: QPoint) -> None:
        self._list_menu(iid).exec(pos)

    # ------------------------------------------------------------------ converting
    def start(self) -> None:
        if self.running:
            return
        if not self._captions_ready():
            return
        if not self.caps.ok and any(it.kind != "photo" for it in self.items.values()):
            self._missing_ffmpeg()
            return
        todo = [iid for iid in self.order if self.items[iid].state in ("ready", "probing", "downloading")]
        if not todo:
            again = [
                iid
                for iid in self.order
                if self.items[iid].state in ("done", "warning", "failed", "canceled", "skipped")
            ]
            if again:
                self.toast.show_message(
                    "Everything here is finished. Use ↻ on a file to run it again, or add more."
                )
            return
        self.join_job = None
        self._last_joined = 0
        self._tape_s = 0.0  # one Convert = one tape
        for iid in todo:
            self.items[iid].clock = None
        if self.export_panel.joining():
            if any(it.state in ("probing", "downloading") for it in self.items.values()):
                self.toast.show_message(
                    "Still reading some files. Press Convert again once every clip is in."
                )
                return
            vids = [
                self.items[i]
                for i in self.order
                if self.items[i].state == "ready" and self.items[i].kind == "video"
            ]
            if len(vids) >= 2:
                s = self.settings.copy()
                self.join_job = JoinJob(
                    ids=[it.id for it in vids], settings=s, conform=join.conform_for(vids[0].info, s),
                    folder=join.parts_folder(vids[0].path, s),
                )  # fmt: skip
                if timecode_mode(s, joining=True) == "continuous":
                    tcs = join.running_timecodes([(it.info, it.length) for it in vids])
                    self.join_job.timecodes = {it.id: tc for it, tc in zip(vids, tcs, strict=True) if tc}
                    for it, tc in zip(vids, tcs, strict=True):
                        it.clock = tc
                    self._tape_s = sum(it.length for it in vids)
        self.batch = []
        self.running, self.paused = True, False
        self._clock = BatchClock(time.monotonic())  # the time left, for the whole batch
        # Every file in the list counts as "taken": Replace can never overwrite another original.
        self.reserved = {naming.reserve_key(Path(it.path)) for it in self.items.values()}
        self.counter = 0
        self.btn_show.hide()
        log.info(
            "convert pressed: %s%s", format_label("video", self.settings),
            " (joining into one video)" if self.join_job else "",
        )  # fmt: skip
        self._kick()
        self._refresh_footer()

    def _join_batch(self) -> None:
        """Ready files (including ones added mid-batch) join, locking in the current settings."""
        for iid in self.order:
            it = self.items[iid]
            if iid in self.batch:
                if it.state == "waiting" and it.base is None:
                    it.base = self.settings.copy()
                continue
            if self.join_job and it.kind == "video" and iid not in self.join_job.ids:
                continue  # videos added during a join wait for the next Convert
            if it.state == "ready":
                it.base = self.settings.copy()
                it.state = "waiting"
                it.card.set_state("waiting")
                self._update_output_name(it)
                self.batch.append(iid)
            elif it.state in ("probing", "downloading"):
                it.base = self.settings.copy()  # same settings as the files dropped with it
                self.batch.append(iid)

    def _kick(self) -> None:
        """Start as many waiting files as we're allowed to run at once."""
        if not self.running:
            return
        self._join_batch()
        if self.paused:
            return
        limit = 2 if self.settings.parallel else 1
        while len(self.active) < limit:
            nxt = next((i for i in self.batch if i in self.items and self.items[i].state == "waiting"), None)
            if nxt is None:
                break
            self._start_item(self.items[nxt])
        if not self.active:
            if any(
                self.items.get(i) and self.items[i].state in ("probing", "downloading") for i in self.batch
            ):
                return  # wait for files that are still being read
            if self.join_job is not None:
                self._start_join()
                return
            self._finish()
            return
        self._refresh_footer()

    def _start_item(self, it: Item) -> None:
        self.counter += 1
        if it.base is None:
            it.base = self.settings.copy()
        s = self.eff(it)
        cues = None
        if s.captions and it.transcript is not None:
            cues = it.transcript.cues_for(s.caption_words, s.caption_lines)
        job = self.join_job
        if job is not None and it.id in job.ids:
            # One part of the joined video: same settings for all, a fixed hidden path, matched shape.
            s = job.settings.copy()
            s.caption_srt = s.keep_dates = False  # the joined video gets these
            if job.ids.index(it.id) > 0 and s.burn_badge == "play":
                s.burn_badge = "none"  # PLAY blinks once, at the start of the joined video (REC stays on)
            cues = (
                it.transcript.cues_for(s.caption_words, s.caption_lines)
                if (s.captions and it.transcript)
                else None
            )
            if cues and job.settings.caption_srt:
                trim = it.trim or (0.0, it.info.duration)
                job.cues[it.id] = captions.for_output(cues, trim[0], trim[1] - trim[0])
            job.folder.mkdir(parents=True, exist_ok=True)
            conv = Conversion(
                it.path, it.info, s, self.caps, self.reserved, self.counter, trim=it.trim, captions=cues,
                target=join.part_path(job.folder, job.ids.index(it.id) + 1, s), conform=job.conform,
                timecode=job.timecodes.get(it.id, ""), cut=job.ids.index(it.id) > 0,
                marks=tape.marks(
                    job.settings, it.length, first=job.ids.index(it.id) == 0, last=it.id == job.ids[-1]
                ),
            )  # fmt: skip
        else:
            conv = Conversion(
                it.path, it.info, s, self.caps, self.reserved, self.counter, trim=it.trim, captions=cues,
                timecode=self._tape_clock(it, s),
            )  # fmt: skip
        it.state, it.processed, it.speed = "converting", 0.0, 0.0
        it.started = time.monotonic()
        it.card.set_state("converting", "Starting…")
        it.card.set_format(format_label(it.kind, s), bool(it.override), False)
        it.card.set_progress(0)
        th = ConvertThread(it.id, conv)
        th.progress.connect(self._progress)
        th.finished_item.connect(self._finished)
        self.active[it.id] = th
        th.start()
        self._pause_button(False)
        if len(self.active) == 1:
            self._scroll_to(it.id)

    def _tape_clock(self, it: Item, s: Settings) -> str:
        """Continuous Timecode for a separate file: its place on this Convert's tape, given once, as it
        starts (clips added mid-batch carry on from the end). "" = the clip keeps its own timecode."""
        if it.kind != "video" or timecode_mode(s) != "continuous":
            it.clock = None
            return ""
        if it.clock is None:
            it.clock = join.running_timecodes([(it.info, it.length)], self._tape_s)[0]
            self._tape_s += it.length
        return it.clock

    def _clocks(self) -> dict[int, tuple[float, str]]:
        """Continuous Timecode as Convert gives it, for previews: {item id: (clip time, timecode there)}.
        Clips with a place on a tape keep it; the rest follow in list order (after the running tape)."""
        out: dict[int, tuple[float, str]] = {}
        pending: list[Item] = []
        for iid in self.order:
            it = self.items[iid]
            if it.kind != "video" or it.info is None:
                continue
            b = self._base(it)
            if (
                timecode_mode(b, self.export_panel.joining(), it.override.get("video_preset", ""))
                != "continuous"
            ):
                continue
            if it.clock is not None:
                out[iid] = (it.trim[0] if it.trim else 0.0, it.clock)
            elif it.state in ("ready", "waiting", "probing", "downloading"):
                pending.append(it)
        tcs = join.running_timecodes(
            [(it.info, it.length) for it in pending], self._tape_s if self.running else 0.0
        )
        for it, tc in zip(pending, tcs, strict=True):
            out[it.id] = (it.trim[0] if it.trim else 0.0, tc)
        return out

    def _progress(self, iid: int, processed: float, speed: float) -> None:
        it = self.items.get(iid)
        if not it or it.state not in ("converting",):
            return
        it.processed = processed
        elapsed = time.monotonic() - it.started
        if elapsed > 1.5 and processed > 0:
            measured = processed / elapsed  # steadier than ffmpeg's own early readings
            it.speed = measured if it.speed <= 0 else it.speed * 0.7 + measured * 0.3
        frac = it.frac
        it.card.set_progress(frac)
        txt = f"{int(frac * 100)}%"
        if it.length and it.speed > 0:
            txt += f" · {_eta(max(0.0, it.length - processed) / it.speed)}"
        it.card.set_state("converting", txt)
        self._refresh_soon()

    def _finished(self, iid: int, r: Result) -> None:
        th = self.active.pop(iid, None)
        if th:
            th.wait(2000)
            th.deleteLater()
        it = self.items.get(iid)
        if it:
            it.result = r
            it.message = r.message
            card = it.card
            if r.status == "done" and self.join_job is not None and iid in self.join_job.ids:
                self.join_job.parts[iid] = r.output
                it.state = "warning" if r.warning else "done"
                card.set_state(it.state, "" if r.warning else "Converted")
                card.set_output(
                    "→  Joining after the last clip" + (f"   ·   {r.warning}" if r.warning else "")
                )
            elif r.status == "done":
                where = r.output.parent.name + "/" if r.output.parent != Path(it.path).parent else ""
                if r.warning:
                    it.state = "warning"
                    card.set_state("warning")
                    card.set_output(f"→  {where}{r.output.name}   ·   {r.warning}")
                else:
                    it.state = "done"
                    card.set_state("done", "Listo ✓")
                    card.set_output(f"→  {where}{r.output.name}")
            else:
                it.state = r.status
                if r.status == "failed":
                    log.warning("conversion failed: %s — %s", it.path, r.message)
                if r.status in ("failed", "skipped"):
                    card.set_state(r.status)
                    card.set_output(r.message)
                else:
                    card.set_state("canceled")
                    card.set_progress(0)
        if self.running:
            self._kick()
        elif not self.active and self.join_job is not None and self.join_job.thread is None:
            self._drop_join()  # stopped before gluing: throw the parts away
        self._refresh_footer()

    # ------------------------------------------------------------------ joining
    def _start_join(self) -> None:
        job = self.join_job
        ids = [i for i in job.ids if i in job.parts]
        first = self.items.get(job.ids[0])
        if not ids or first is None:
            self._drop_join()
            self._finish()
            return
        conv = join.Join(
            [job.parts[i] for i in ids], first.path, first.info, job.settings, self.caps, self.reserved,
            [job.cues.get(i) for i in ids], self.items[ids[-1]].path, job.conform,
        )  # fmt: skip
        job.total_s = sum(self.items[i].length for i in ids if i in self.items)
        job.thread = th = JoinThread(conv)
        th.progress.connect(self._join_progress)
        th.joined.connect(self._joined)
        for i in ids:
            if i in self.items:
                self.items[i].card.set_output("→  Joining into one video…")
        th.start()
        self._refresh_footer()

    def _join_progress(self, done_s: float, _speed: float) -> None:
        if self.join_job is not None:
            self.join_job.done_s = done_s
            self._refresh_footer()

    def _joined(self, r: Result) -> None:
        job = self.join_job
        if job is None:
            return
        if job.thread is not None:
            if job.thread.wait(15000):
                job.thread.deleteLater()
            else:
                _ORPHANS.append(job.thread)  # never let go of a QThread that's still running (crashes)
        ids = [i for i in job.ids if i in job.parts and i in self.items]
        left_out = [i for i in job.ids if i not in job.parts and i in self.items]
        if r.status == "done" and left_out:
            r.notes.append(
                f"{len(left_out)} clip{'s' if len(left_out) != 1 else ''} left out (they didn't convert)."
            )
        for i in ids:
            it = self.items[i]
            it.result = r
            it.message = r.message
            if r.status == "done":
                where = r.output.parent.name + "/" if r.output.parent != Path(it.path).parent else ""
                it.state = "warning" if r.warning else "done"
                it.card.set_state(it.state, "" if r.warning else "Listo ✓")
                it.card.set_output(
                    f"→  {where}{r.output.name}  (joined)" + (f"   ·   {r.warning}" if r.warning else "")
                )
            else:
                it.state = "failed" if r.status == "failed" else r.status
                it.card.set_state(it.state if it.state in ("failed", "skipped") else "canceled")
                it.card.set_output(r.message)
        self.join_job = None
        self._last_joined = len(ids) if r.status == "done" else 0
        if r.status == "failed":
            log.warning("join failed: %s", r.message)
        self._finish()

    def _drop_join(self) -> None:
        """Stopped before the clips were put together: the parts go, and those clips are ready again."""
        job, self.join_job = self.join_job, None
        if job is None:
            return
        shutil.rmtree(job.folder, ignore_errors=True)
        for i in job.parts:
            it = self.items.get(i)
            if it and it.state in ("done", "warning"):
                it.state, it.result, it.base = "ready", None, None
                it.card.set_state("ready")
                it.card.set_progress(0)
                self._update_output_name(it)

    def toggle_pause(self) -> None:
        if not self.running or (not self.active and not self.paused):
            return
        convs = [
            (self.items.get(i), th.conversion) for i, th in self.active.items() if not th.conversion.canceled
        ]
        if not self.paused:
            paused_any = False
            for it, c in convs:
                if c.pause():  # photos and finishing steps can't pause; leave those cards as they are
                    paused_any = True
                    if it:
                        it.state = "paused"
                        it.card.set_state("paused")
            if paused_any or convs:
                self.paused = True
                self._clock.pause(time.monotonic())
                self._pause_button(True)
        else:
            self.paused = False
            for it, c in convs:
                c.resume()
                if it and it.state == "paused":
                    it.state = "converting"
                    it.started = time.monotonic() - (it.processed / it.speed if it.speed > 0 else 0)
                    it.card.set_state("converting", f"{int(it.frac * 100)}%")
            self._clock.resume(time.monotonic())
            self._pause_button(False)
            self._kick()
        self._refresh_footer()

    def _pause_button(self, paused: bool) -> None:
        self.btn_pause.setIcon(theme.icon("play" if paused else "pause", theme.MUTED))
        self.btn_pause.setToolTip("Resume" if paused else "Pause")

    def stop(self) -> None:
        self._convert_after_captions = False
        if not self.running:
            return
        log.info("stop pressed")
        self.running = False
        self.paused = False
        for iid in self.batch:
            it = self.items.get(iid)
            if it and it.state == "waiting":
                it.state = "ready"
                it.base = None
                it.card.set_state("ready")
                self._update_output_name(it)
        for th in self.active.values():
            th.conversion.cancel()
        if self.join_job is not None:
            if self.join_job.thread is not None:
                self.join_job.thread.job.cancel()
            elif not self.active:
                self._drop_join()
        self.batch = []
        self._refresh_footer()

    def _finish(self) -> None:
        self.running = False
        results = [self.items[i] for i in self.batch if i in self.items]
        done = sum(1 for it in results if it.state in ("done", "warning"))
        warned = sum(1 for it in results if it.state == "warning")
        failed = sum(1 for it in results if it.state == "failed")
        skipped = sum(1 for it in results if it.state == "skipped")
        self._last_summary = (done, failed, skipped, warned)
        log.info("finished: %d done, %d failed, %d skipped, %d to check", done, failed, skipped, warned)
        self._last_outputs = [it.result.output for it in results if it.result and it.result.output]
        self.btn_show.setVisible(bool(self._last_outputs))
        QApplication.alert(self, 0)
        self._refresh_footer(finished=True)

    def _show_outputs(self) -> None:
        outs = getattr(self, "_last_outputs", [])
        if outs:
            reveal(outs[0])

    # ------------------------------------------------------------------ footer
    def _refresh_places(self) -> None:
        """The sidebar's counts, and the list again if a file moved in or out of the place shown."""
        counts = dict.fromkeys(PLACES, 0)
        for it in self.items.values():
            for key in PLACES:
                if in_place(key, it.kind, it.state):
                    counts[key] += 1
        problems = counts["attention"] > 0
        self.sidebar.set_counts(counts, self.running, problems)
        self.footer.setVisible(bool(self.items))
        if self.place != "all" or self.search.text().strip():
            want = [i for i in self.order if self._shown(self.items[i])]
            if want != self.table.shown_ids():
                self._apply_filter()
                return
        self._show_page()
        self._show_count()

    def _list_changed(self) -> None:
        """Files were added, read or removed: the live preview may now show another clip."""
        it = self._live_clip()
        key = (it.id, it.trim) if it else None
        if key != getattr(self, "_live_key", "unset"):
            self._live_key = key
            self._schedule_live()

    def _label_duplicates(self) -> None:
        """Same file name twice (e.g. MOV01A.MOD in PRG001 and PRG002)? Show each one's folder."""
        files = [it for it in self.items.values() if it.kind != "link"]
        names = {it.id: os.path.basename(it.path) for it in files}  # (plain strings: fast for long lists)
        counts: dict[str, int] = {}
        for n in names.values():
            counts[n.lower()] = counts.get(n.lower(), 0) + 1
        for it in files:
            n = names[it.id]
            folder = os.path.basename(os.path.dirname(it.path))
            it.card.set_name(f"{folder} / {n}" if counts[n.lower()] > 1 else n)

    def _refresh_soon(self, captions: bool = False) -> None:
        """Ask for a list-wide refresh; many requests in a row become one."""
        self._soon_captions = self._soon_captions or captions
        if not self._soon_timer.isActive():
            # a long list waits a little longer, so the window stays responsive while hundreds arrive
            self._soon_timer.start(SOON_MS + len(self.items) // 2)

    def _refresh_now(self) -> None:
        if self._soon_captions:
            self._soon_captions = False
            self._sync_captions()
        self._update_sample()
        self._refresh_footer()

    def _refresh_footer(self, finished: bool = False) -> None:
        self._label_duplicates()
        self._update_check_button()
        vids = [
            self.items[i]
            for i in self.order
            if self.items[i].kind == "video" and self.items[i].state != "unsupported"
        ]
        self.export_panel.set_video_count(len(vids), vids[-1].path if vids else "")
        joining = self.export_panel.joining()
        if joining != getattr(self, "_was_joining", False):  # 2nd video added / removed: names change
            self._was_joining = joining
            for it in self.items.values():
                if it.state in ("ready", "waiting"):
                    self._update_output_name(it)
        self._list_changed()
        self.convert.set_queue_info(
            any(it.info is not None and it.info.interlaced for it in self.items.values())
        )
        self._refresh_places()
        self.table.can_reorder = not self.running  # (a batch keeps its order while it converts)
        if finished:
            self._show_summary = True
        elif self.running:
            self._show_summary = False
        finished = finished or getattr(self, "_show_summary", False)
        items = [self.items[i] for i in self.order]
        n = len(items)
        convertible = [it for it in items if it.state not in ("unsupported",)]
        self.f_time.setVisible(self.running)
        self.f_sub.setVisible(not self.running)
        if self._convert_after_captions and not self.running:
            self.f_title.setText("Waiting for Captions")
            self.f_sub.setText("Converts as soon as they're ready.")
        job = self.join_job
        if self.running and job is not None and job.thread is not None:
            self.f_bar.show()
            self.f_bar.setValue(int(min(1.0, job.done_s / job.total_s) * 1000) if job.total_s else 0)
            self.f_title.setText(f"Joining {len(job.parts)} Clips into One Video")
            self.f_time.setText("")
            self.btn_start.setEnabled(False)
            self.btn_pause.hide()
            self.btn_cancel.show()
            return
        if self.running:
            batch = [self.items[i] for i in self.batch if i in self.items]
            total_w = sum(it.weight for it in batch) or 1.0
            done_w = sum(it.weight * (1.0 if it.state in FINAL else it.frac) for it in batch)
            finished_n = sum(1 for it in batch if it.state in FINAL)
            self.f_bar.show()
            self.f_bar.setValue(int(done_w / total_w * 1000))
            n = len(batch)
            self.f_title.setText("Paused" if self.paused else f"Converting {n} File{'s' if n != 1 else ''}")
            left = self._clock.left(done_w, total_w, time.monotonic())
            bits = [f"{finished_n} of {n} done"]
            if left is not None and not self.paused:
                bits.append(time_left(left))
            self.f_time.setText(" · ".join(bits))
            self.btn_start.setEnabled(False)
            self.btn_start.setText("Converting…")

            self.btn_pause.show()
            self.btn_cancel.show()
            self.btn_add.setEnabled(True)
            return

        self.btn_pause.hide()
        self.btn_cancel.hide()
        self.f_bar.hide()
        ready = [it for it in items if it.state in ("ready", "probing", "downloading")]
        self.btn_start.setEnabled(bool(ready))
        verb = "Convert && Join" if self.export_panel.joining() else "Convert"  # (&& shows one &)
        self.btn_start.setText(
            f"{verb} {len(ready)} File{'s' if len(ready) != 1 else ''}" if ready else "Convert"
        )
        if finished and hasattr(self, "_last_summary"):
            d, f, sk, w = self._last_summary
            joined = getattr(self, "_last_joined", 0)
            parts = [f"{joined} clips joined into one video" if joined else f"{d} converted"]
            if w:
                parts.append(f"{w} to check")
            if f:
                parts.append(f"{f} failed")
            if sk:
                parts.append(f"{sk} skipped")
            ok = not f and not w
            self.f_title.setText(("Listo · " if ok else "Finished · ") + " · ".join(parts))
            ready = "Your video is ready." if joined else "Your files are ready."
            self.f_sub.setText(ready if ok else "Click ⓘ on a file for details.")
            return
        if n == 0:
            self.f_title.setText("Nothing here yet")
            self.f_sub.setText("")
            self.btn_show.hide()
            return
        kinds = {"video": 0, "photo": 0, "audio": 0, "link": 0}
        dur = 0.0
        for it in convertible:
            if it.kind in kinds:
                kinds[it.kind] += 1
            if it.info and it.kind in ("video", "audio"):
                dur += it.length
        bits = [
            f"{c} {k}{'s' if c != 1 else ''}"
            for k, c in (
                ("video", kinds["video"]),
                ("photo", kinds["photo"]),
                ("audio file", kinds["audio"]),
                ("link", kinds["link"]),
            )
            if c
        ]
        self.f_title.setText(" · ".join(bits) or "Nothing Listo can convert yet")
        sub = []
        if dur:
            sub.append(f"{fmt_duration(dur)} of media")
        bad = sum(1 for it in items if it.state == "unsupported")
        if bad:
            sub.append(f"{bad} file{'s' if bad != 1 else ''} can't be converted")
        self.f_sub.setText(" · ".join(sub))

    def _scroll_to(self, iid: int) -> None:
        QTimer.singleShot(50, lambda: self.table.scroll_to(iid))

    # ------------------------------------------------------------------ misc
    def _hardware_found(self, hw: dict) -> None:
        self.convert.apply_hardware(hw)

    def _missing_ffmpeg(self) -> None:
        notice(
            self,
            "ffmpeg Is Missing",
            "Listo couldn't find its copy of ffmpeg, so it can only convert photos right now. "
            "Running from the code? Run python scripts/fetch_ffmpeg.py.",
        )

    def _about(self) -> None:
        about(self, __version__, (self.caps.version or "").split(" Copyright")[0], str(data_dir()))

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        md = e.mimeData()
        if md.hasUrls() or is_link(md.text()):
            e.acceptProposedAction()
            self.empty.set_hot(True)

    def dragLeaveEvent(self, e) -> None:
        self.empty.set_hot(False)

    def dropEvent(self, e: QDropEvent) -> None:
        self.empty.set_hot(False)
        urls = e.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        links = [u.toString() for u in urls if not u.isLocalFile() and is_link(u.toString())]
        if not urls and is_link(e.mimeData().text()):
            links = [e.mimeData().text().strip()]
        if paths:
            self.add_paths(paths)
        if links:
            self.add_links(links)
        if paths or links:
            e.acceptProposedAction()

    def show(self) -> None:
        """The first time: filling the screen (all of it but the menu bar and Dock). After that: the size
        and place you left it, if it still fits a screen you have (else filling the screen again)."""
        if self._restored:
            super().show()
            return
        geo = self.qs.value("geometry")
        if isinstance(geo, str) and geo and self._fits_after(QByteArray.fromHex(geo.encode())):
            super().show()
        elif self.titlebar is not None:  # the Mac: fill the free area ourselves (zooming is unreliable here)
            titlebar.fill_screen(self)
            super().show()
        else:
            self.showMaximized()

    def _fits_after(self, geo: QByteArray) -> bool:
        """Put the window back where it was; True if that lands wholly on a screen."""
        if not self.restoreGeometry(geo):
            return False
        frame = self.frameGeometry()
        return any(
            sc.availableGeometry().adjusted(-2, -2, 2, 2).contains(frame) for sc in QGuiApplication.screens()
        )

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if self.titlebar is not None and not getattr(self, "_titlebar_fitted", False):
            self._titlebar_fitted = True
            self.titlebar.fit()
            handle = self.windowHandle()
            if handle is not None and hasattr(handle, "safeAreaMarginsChanged"):
                handle.safeAreaMarginsChanged.connect(lambda *_a: self.titlebar.fit())

    def closeEvent(self, e) -> None:
        if self.running and not confirm(
            self,
            "Stop Converting and Quit?",
            "A file is still converting. The unfinished file will be cleaned up.",
            "Quit",
        ):
            e.ignore()
            return
        self.shutdown()
        super().closeEvent(e)

    def shutdown(self) -> None:
        """Stop ffmpeg and clean up — never leave a stray process behind."""
        if getattr(self, "_shut", False):
            return
        self._shut = True
        if self.running:
            self.stop()
        for th in list(self.active.values()):
            th.conversion.cancel()
        for th in list(self.downloads.values()):
            th.job.cancel()
        if self.tx is not None:
            self.tx.cancel()  # ends the captions process
            if not self.tx.wait(5000):
                _ORPHANS.append(self.tx)
        if self.join_job is not None and self.join_job.thread is not None:
            self.join_job.thread.job.cancel()
            if not self.join_job.thread.wait(15000):
                _ORPHANS.append(self.join_job.thread)
        for th in list(self.active.values()) + list(self.downloads.values()):
            if not th.wait(15000):
                _ORPHANS.append(th)  # never destroy a running QThread (that crashes on quit)
        if self._upd_thread is not None and not self._upd_thread.wait(3000):
            _ORPHANS.append(self._upd_thread)
        self.export_panel.player.release()
        self.pool.clear()
        self.pool.waitForDone(3000)
        if not self._restored:
            self.qs.setValue("geometry", bytes(self.saveGeometry().toHex()).decode())

        self.qs.setValue("settings", self.settings.to_dict())


def _eta(sec: float) -> str:
    sec = round(sec)
    if sec < 60:
        return f"{max(sec, 1)}s"
    if sec < 3600:
        return f"{sec // 60}m {sec % 60:02d}s"
    return f"{sec // 3600}h {(sec % 3600) // 60}m"


def _short_url(url: str) -> str:
    u = url.split("://", 1)[-1]
    return u if len(u) <= 60 else u[:57] + "…"


def _quote(a: str) -> str:
    return f'"{a}"' if (" " in a or not a) else a
