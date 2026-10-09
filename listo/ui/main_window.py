"""The main window: queue on the left, settings on the right, controls at the bottom."""

from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QThread, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..core import captions, console, join, naming
from ..core.captions import sample_cues
from ..core.engine import Conversion, Result
from ..core.fileutil import reveal
from ..core.links import is_link
from ..core.log import get_logger
from ..core.presets import (
    AUDIO_FORMATS,
    OVERRIDE_KEYS,
    PHOTO_FORMATS,
    SESSION_ONLY,
    VIDEO_PRESETS,
    Settings,
    format_label,
)
from ..core.probe import (
    KNOWN_EXTS,
    SIDECAR_EXTS,
    UNSUPPORTED_HINTS,
    MediaInfo,
    ext_of,
    fmt_duration,
    kind_from_ext,
    probe,
)
from ..core.sample import sample_clip, sample_clip_if_made
from ..core.tools import capabilities
from . import theme, titlebar, tokens
from .caption_editor import CaptionEditor
from .export_panel import ExportPanel
from .job_card import JobCard
from .preview_dialog import PreviewDialog
from .sidebar import Sidebar
from .trim_dialog import TrimDialog, fmt_time
from .widgets import FitScroll, StepHeader, Toast, repolish
from .workers import (
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
    card: JobCard | None = None
    message: str = ""
    notes: list[str] = field(default_factory=list)
    override: dict = field(default_factory=dict)  # per-file format choice
    base: Settings | None = None  # settings captured when this file joined a batch
    started: float = 0.0
    speed: float = 0.0
    url: str = ""  # set for things added from a link
    trim: tuple[float, float] | None = None
    transcript: object | None = None  # captions.Transcript once speech has been turned into text

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


class _ListArea(QWidget):
    """The space behind the file cards: clicking an empty spot clears the selection."""

    blank_clicked = Signal()

    def mousePressEvent(self, e):
        self.blank_clicked.emit()
        super().mousePressEvent(e)


class DropZone(QFrame):
    def __init__(self, on_click, on_link=None):
        super().__init__()
        self.setObjectName("DropZone")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._on_click = on_click
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(tokens.SPACE_2)
        ic = QLabel()
        ic.setPixmap(theme.pixmap("drop", tokens.ICON_XL, theme.ACCENT, 1.6))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        word = QLabel(f'listo<span style="color:{theme.ACCENT}">.</span>')
        word.setObjectName("Wordmark")
        word.setTextFormat(Qt.TextFormat.RichText)
        word.setAlignment(Qt.AlignmentFlag.AlignCenter)
        word.setToolTip("Drop it in. Get it back edit-ready.")
        title = QLabel("Drop Videos, Photos or Audio Here")
        title.setObjectName("DropTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("or click to choose files — folders work too")
        sub.setObjectName("DropSub")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fmts = QLabel(
            "MOV · MP4 · MTS · MXF · AVI · MKV · MOD · MPG · HEIC · RAW · JPG · PNG · WAV · AIFF · MP3 …"
        )
        fmts.setObjectName("DropFormats")
        fmts.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fmts.setWordWrap(True)
        lay.addWidget(word)
        lay.addSpacing(tokens.SPACE_3)
        lay.addWidget(ic)
        lay.addSpacing(tokens.SPACE_1)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addSpacing(tokens.SPACE_2)
        lay.addWidget(fmts)
        if on_link is not None:
            lay.addSpacing(tokens.SPACE_4)
            row = QHBoxLayout()
            row.setSpacing(tokens.SPACE_2)
            row.addStretch(1)
            self.link = QLineEdit()
            self.link.setObjectName("LinkBox")
            self.link.setPlaceholderText("…or paste a video link (YouTube, Vimeo, Instagram…)")
            self.link.setFixedWidth(tokens.LINK_BOX_W)
            self.link.setCursor(Qt.CursorShape.IBeamCursor)
            go = QPushButton("Add")
            go.setCursor(Qt.CursorShape.PointingHandCursor)

            def submit() -> None:
                text = self.link.text().strip()
                if text:
                    on_link(text)
                    self.link.clear()

            self.link.returnPressed.connect(submit)
            go.clicked.connect(submit)
            row.addWidget(self.link)
            row.addWidget(go)
            row.addStretch(1)
            lay.addLayout(row)

    def set_hot(self, on: bool) -> None:
        self.setProperty("hot", "true" if on else "false")
        repolish(self)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._on_click()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        self.qs = QSettings("Listo", "Listo")
        try:
            import json

            self.settings = Settings.from_dict(json.loads(self.qs.value("settings", "{}") or "{}"))
        except Exception:
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
        self.active: dict[int, ConvertThread] = {}
        self.downloads: dict[int, DownloadThread] = {}
        self.caps = capabilities()
        self.selected: set[int] = set()
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
        self._live_loaded: object = None  # which clip the Export preview's player has open
        self._live_play_next = False  # the preview's arrows keep playing if it was playing
        self._sample_probe: tuple[str, MediaInfo] | None = None
        self._anchor: int | None = None  # where a Shift-click range starts

        self._build()
        self._menus()

        self._live_signals = PreviewSignals(self)
        self._live_signals.done.connect(self._live_got)
        self.export_panel.player.settled.connect(self._live_settled)
        self.export_panel.player.step.connect(self._live_step)
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
        self._schedule_live()
        self.sidebar.apply_capabilities(self.caps)
        self.pool.start(HardwareTask(self.hw_signals))
        self._refresh_footer()
        self.centralWidget().setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        QTimer.singleShot(0, self.centralWidget().setFocus)

        geo = self.qs.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(*tokens.WINDOW_SIZE)
        self.setMinimumSize(QSize(*tokens.WINDOW_MIN))

        if not self.caps.ok:
            QTimer.singleShot(300, self._missing_ffmpeg)

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.titlebar = titlebar.install(self)  # Mac: Listo's own dark title bar, wordmark centred
        if self.titlebar is not None:
            titlebar.ignore_safe_area(root)
            v.addWidget(self.titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(0)
        step1 = StepHeader(1, "Files")
        bar = step1.actions
        self.btn_add = QToolButton()
        self.btn_add.setObjectName("IconBtn")
        self.btn_add.setIcon(theme.icon("plus", theme.MUTED))
        self.btn_add.setIconSize(QSize(tokens.ICON, tokens.ICON))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setToolTip("Add files, a folder or a link — or just drop them in")
        add_menu = QMenu(self)
        add_menu.addAction(theme.menu_icon("file"), "Files…", self.pick_files)
        add_menu.addAction(theme.menu_icon("folder"), "A Folder…", self.pick_folder)
        add_menu.addAction(theme.menu_icon("link"), "A Link…", self.ask_link)
        self.btn_add.setMenu(add_menu)
        self.btn_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        bar.addWidget(self.btn_add)
        self.btn_clear_all = QToolButton()
        self.btn_clear_all.setObjectName("IconBtn")
        self.btn_clear_all.setIcon(theme.icon("list-x", theme.MUTED))
        self.btn_clear_all.setIconSize(QSize(tokens.ICON, tokens.ICON))
        self.btn_clear_all.setToolTip("Remove files from the list (your files aren't touched)")
        self.btn_clear_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.trash_menu = QMenu(self)
        self.trash_menu.aboutToShow.connect(self._fill_trash_menu)
        self.btn_clear_all.setMenu(self.trash_menu)
        self.btn_clear_all.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        bar.addWidget(self.btn_clear_all)
        left_col.addWidget(step1)
        self.queue_stack = QStackedWidget()
        empty_wrap = QWidget()
        ew = QVBoxLayout(empty_wrap)
        ew.setContentsMargins(*(tokens.SPACE_4,) * 4)
        self.drop = DropZone(self.pick_files, self._link_typed)
        ew.addWidget(self.drop)
        self.queue_stack.addWidget(empty_wrap)

        queue_page = QWidget()
        qp = QVBoxLayout(queue_page)
        qp.setContentsMargins(0, 0, 0, 0)
        qp.setSpacing(0)
        self.scroll = FitScroll()
        lst = _ListArea()
        lst.blank_clicked.connect(lambda: self._select(set()))
        self.list_lay = QVBoxLayout(lst)
        self.list_lay.setContentsMargins(
            tokens.SPACE_4, tokens.SPACE_3, tokens.SPACE_4 - tokens.SCROLL_GUTTER, tokens.SPACE_4
        )
        self.list_lay.setSpacing(tokens.SPACE_2)
        self.list_lay.addStretch(1)
        self.scroll.setWidget(lst)
        qp.addWidget(self.scroll, 1)
        self.queue_stack.addWidget(queue_page)
        left_col.addWidget(self.queue_stack, 1)
        self.sidebar = Sidebar(self.settings)
        self.sidebar.changed.connect(self._settings_changed)
        self.export_panel = ExportPanel(self.settings, self)
        self.export_panel.changed.connect(self._settings_changed)
        self.export_panel.preview_clicked.connect(self.open_preview)
        self.sidebar.recipe_applied.connect(self.export_panel.reload)
        body.addLayout(left_col, 1)  # step 1: the files
        body.addWidget(self.sidebar)  # step 2: what they become
        body.addWidget(self.export_panel)  # step 3: preview, where, name, Convert
        v.addLayout(body, 1)
        footer = QFrame()
        footer.setObjectName("Footer")
        f = QHBoxLayout(footer)
        f.setContentsMargins(tokens.SPACE_4, tokens.SPACE_3, tokens.SPACE_4, tokens.SPACE_3)
        f.setSpacing(tokens.SPACE_2)
        left = QVBoxLayout()
        left.setSpacing(tokens.SPACE_1)
        self.f_title = QLabel()
        self.f_title.setObjectName("FooterTitle")
        self.f_sub = QLabel()
        self.f_sub.setObjectName("Muted")
        self.f_bar = QProgressBar()
        self.f_bar.setRange(0, 1000)
        self.f_bar.setTextVisible(False)
        self.f_bar.hide()
        left.addWidget(self.f_title)
        left.addWidget(self.f_sub)
        left.addWidget(self.f_bar)
        f.addLayout(left, 1)
        self.btn_show = QPushButton("Show Files")
        self.btn_show.setObjectName("Ghost")
        self.btn_show.clicked.connect(self._show_outputs)
        self.btn_show.hide()
        self.btn_pause = QPushButton(" Pause")
        self.btn_pause.setIcon(theme.icon("pause"))
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_cancel = QPushButton("Stop")
        self.btn_cancel.setObjectName("Danger")
        self.btn_cancel.clicked.connect(self.stop)
        for b in (self.btn_show, self.btn_pause, self.btn_cancel):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            f.addWidget(b)
        self.btn_console = QToolButton()
        self.btn_console.setObjectName("IconBtn")
        self.btn_console.setIcon(theme.icon("terminal", theme.FAINT))
        self.btn_console.setIconSize(QSize(tokens.ICON, tokens.ICON))
        self.btn_console.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_console.setToolTip("Debug console: watch what Listo is doing, live, in a terminal window")
        self.btn_console.clicked.connect(self.open_console)
        f.addWidget(self.btn_console)
        self.btn_check = QPushButton("Check Captions")
        self.btn_check.setIcon(theme.icon("captions", theme.TEXT))
        self.btn_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check.setToolTip("Watch each clip with its captions and fix any words before converting")
        self.btn_check.clicked.connect(self.check_captions)
        self.btn_check.hide()
        self.export_panel.bottom.addWidget(self.btn_check)
        self.btn_start = QPushButton("Convert")
        self.btn_start.setObjectName("Primary")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.start)
        self.export_panel.bottom.addWidget(self.btn_start)
        left_col.addWidget(footer)
        self.toast = Toast(root)

    def _menus(self) -> None:
        """File / Edit / View / Help. On a Mac they live in the menu bar at the top of the screen;
        on Windows and Linux the bar stays hidden (no extra strip in the window) but every
        shortcut still works. Menus hold commands only; settings stay in the side panel."""

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

        bar = self.menuBar()
        f = bar.addMenu("File")
        act(f, "Add Files…", self.pick_files, QKeySequence.StandardKey.Open)
        act(f, "Add Folder…", self.pick_folder, "Ctrl+Shift+O")
        act(f, "Add a Link…", self.ask_link, "Ctrl+L")
        f.addSeparator()
        act(f, "Preview…", self.open_preview, "Ctrl+P")
        f.addSeparator()
        act(f, "Convert", self.start, "Ctrl+Return")
        act(f, "Stop", self.stop, "Ctrl+.")
        e = bar.addMenu("Edit")
        # Text fields keep these keys for themselves while you type in them.
        act(e, "Paste", self._paste, QKeySequence.StandardKey.Paste)
        e.addSeparator()
        act(e, "Select All", self.select_all, QKeySequence.StandardKey.SelectAll)
        act(e, "Deselect", lambda: self._select(set()), "Esc")
        act(e, "Remove Selected", self.remove_selected, [Qt.Key.Key_Backspace, Qt.Key.Key_Delete])
        e.addSeparator()
        act(e, "Clear Finished", self.clear_finished)
        act(e, "Clear All", self.clear_all)
        v = bar.addMenu("View")
        act(v, "Check Captions…", self._menu_captions, "Ctrl+Shift+C")
        v.addSeparator()
        act(v, "Show All Options", lambda: self.sidebar.open_groups(True))
        act(v, "Fold All Options", lambda: self.sidebar.open_groups(False))
        h = bar.addMenu("Help")
        act(h, "Open Debug Console", self.open_console, "Ctrl+Alt+D")
        act(h, "Show the Log File", self._show_log)
        act(h, f"About {APP_NAME}", self._about, role=QAction.MenuRole.AboutRole)
        if sys.platform != "darwin":
            bar.hide()

    def open_console(self) -> None:
        """A terminal window that follows Listo's log live (core/console.py)."""
        error = console.open_console()
        if error:
            self.toast.show_message(error)
        else:
            log.info("%d files in the list, %s", len(self.items), "converting" if self.running else "idle")

    def _menu_captions(self) -> None:
        self.check_captions()

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
            self.btn_check.setText(" Making Captions…")
        elif new:
            self.btn_check.setText(f" Check Captions · {new} New")
        else:
            self.btn_check.setText(" Check Captions")

    def _show_log(self) -> None:
        from ..core.fileutil import reveal
        from ..core.paths import log_dir

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
        note = QLabel("Only download videos you have the rights to use. Saved to Downloads › Listo.")
        note.setObjectName("Hint")
        note.setWordWrap(True)
        lay.addWidget(note)
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

    def _link_typed(self, text: str) -> None:
        links = [w for w in text.split() if is_link(w)]
        if links:
            self.add_links(links)
        else:
            self.toast.show_message("That doesn't look like a link — it should start with https://")

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
            it.trim = dlg.result_trim
            it.card.set_trim(f"✂ {fmt_time(it.trim[0])}–{fmt_time(it.trim[1])}" if it.trim else "")
            self._refresh_footer()

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
        for iid in list(self.order):
            if self.items[iid].state in ("done", "skipped"):
                self.remove_item(iid)

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
        card = JobCard(iid, display or Path(path).name, kind)
        card.remove.connect(self.remove_item)
        card.retry.connect(self.retry_item)
        card.reveal.connect(self.reveal_item)
        card.details.connect(self.show_details)
        card.format_clicked.connect(self._format_menu)
        card.trim_clicked.connect(self.trim_item)
        card.captions_clicked.connect(self.open_captions)
        card.pressed.connect(self._card_pressed)
        card.opened.connect(self.play_item)
        it.card = card
        self.items[iid] = it
        self.order.append(iid)
        self.list_lay.insertWidget(self.list_lay.count() - 1, card)
        self.queue_stack.setCurrentIndex(1)
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
            ans = QMessageBox.question(
                self,
                "Redo Edited Captions?",
                f"You fixed the captions of {n} clip{'s' if n != 1 else ''} by hand. Redo "
                f"{'them' if n != 1 else 'it'} with the new setting too? Your fixes would be replaced.",
            )
            if ans == QMessageBox.StandardButton.Yes:
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
                self._live_seq, path, info, s, at, False, self._live_signals, captions=self._clip_cues(it, s)
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
            self._scroll_to(clips[n].card)
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
        PreviewDialog(
            [
                (Path(c.path).name, c.path, c.info, self.eff(c), self._clip_cues(c, self.eff(c)))
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
                    [("Sample picture", sample, probe(sample), s, self._clip_cues(None, s))], 0, self
                ).exec()
            return
        start = next((n for n, it in enumerate(clips) if it.id in self.selected), 0)
        PreviewDialog(
            [
                (Path(it.path).name, it.path, it.info, self.eff(it), self._clip_cues(it, self.eff(it)))
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
        import json

        self.sidebar.notify_external_change()
        self.export_panel.refresh()
        self.qs.setValue("settings", json.dumps(self.settings.to_dict()))
        self._schedule_live()
        for it in self.items.values():
            if it.state in ("ready", "waiting"):
                self._update_output_name(it)
        self._caption_choice_changed()
        self._sync_captions()
        self._refresh_footer()  # "Convert & Join" on the button

    def _format_menu(self, iid: int, anchor: QWidget) -> None:
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
        m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _set_override(self, iid: int, override: dict) -> None:
        it = self.items.get(iid)
        if not it or it.state not in ("ready", "waiting"):
            return
        it.override = {k: v for k, v in override.items() if k in OVERRIDE_KEYS}
        self._update_output_name(it)

    # ------------------------------------------------------------------ list actions
    def remove_item(self, iid: int) -> None:
        it = self.items.get(iid)
        if not it or iid in self.active:
            return
        if iid in self.downloads:
            self.downloads[iid].job.cancel()  # its thread finishes on its own
        it.card.setParent(None)
        it.card.deleteLater()
        del self.items[iid]
        self.order.remove(iid)
        if iid in self.selected:
            self._select(self.selected - {iid})
        if iid in self.batch:
            self.batch.remove(iid)
        if not self.items:
            self.queue_stack.setCurrentIndex(0)
        self._update_sample()
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
        it.result, it.processed, it.message, it.base = None, 0.0, "", None
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
        t.setObjectName("FileName")
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
        for iid in list(self.order):
            if self.items[iid].state in FINAL:
                self.remove_item(iid)

    def clear_all(self) -> None:
        for iid in list(self.order):
            if iid not in self.active:
                self.remove_item(iid)

    # ------------------------------------------------------------------ selection
    def _select(self, ids: set[int]) -> None:
        if {i for i in ids if i in self.items} != self.selected:
            self._schedule_live()
        self.selected = {i for i in ids if i in self.items}
        for iid, it in self.items.items():
            it.card.set_selected(iid in self.selected)

    def _card_pressed(self, iid: int, mods) -> None:
        self.centralWidget().setFocus()  # so Delete / Backspace reach the list, not a text field
        if mods & Qt.KeyboardModifier.ShiftModifier and self._anchor in self.order:
            a, b = sorted((self.order.index(self._anchor), self.order.index(iid)))
            self._select(self.selected | set(self.order[a : b + 1]))
            return
        if mods & Qt.KeyboardModifier.ControlModifier:  # Cmd on a Mac, Ctrl elsewhere
            self._select(self.selected ^ {iid})
        else:
            self._select({iid})
        self._anchor = iid

    def select_all(self) -> None:
        self._select(set(self.order))

    def remove_selected(self) -> None:
        for iid in [i for i in self.order if i in self.selected]:
            self.remove_item(iid)  # files that are converting right now are skipped

    def _fill_trash_menu(self) -> None:
        """Nothing is removed until a choice is picked here (only from the list — never from disk)."""
        m = self.trash_menu
        m.clear()
        n = sum(1 for i in self.selected if i not in self.active)
        a = m.addAction(
            theme.menu_icon("x"),
            f"Remove {n} Selected" if n else "Remove Selected",
            self.remove_selected,
        )
        a.setEnabled(n > 0)
        finished = sum(1 for it in self.items.values() if it.state in FINAL)
        a = m.addAction(theme.menu_icon("check"), "Clear Finished", self.clear_finished)
        a.setEnabled(finished > 0)
        m.addSeparator()
        m.addAction(theme.menu_icon("list-x"), "Clear All", self.clear_all)

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
        self.batch = []
        self.running, self.paused = True, False
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
            )  # fmt: skip
        else:
            conv = Conversion(
                it.path, it.info, s, self.caps, self.reserved, self.counter, trim=it.trim, captions=cues
            )
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
        self.btn_pause.setText(" Pause")
        self.btn_pause.setIcon(theme.icon("pause"))
        if len(self.active) == 1:
            self._scroll_to(it.card)

    def _total_speed(self) -> float:
        return sum(self.items[i].speed for i in self.active if i in self.items)

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
            [job.cues.get(i) for i in ids], self.items[ids[-1]].path,
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
                self.btn_pause.setText(" Resume")
                self.btn_pause.setIcon(theme.icon("play"))
        else:
            self.paused = False
            for it, c in convs:
                c.resume()
                if it and it.state == "paused":
                    it.state = "converting"
                    it.started = time.monotonic() - (it.processed / it.speed if it.speed > 0 else 0)
                    it.card.set_state("converting", f"{int(it.frac * 100)}%")
            self.btn_pause.setText(" Pause")
            self.btn_pause.setIcon(theme.icon("pause"))
            self._kick()
        self._refresh_footer()

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
    def _refresh_queue_bar(self) -> None:
        items = [self.items[i] for i in self.order]
        n = len(items)
        self.btn_clear_all.setVisible(n > 0 and not self.running)

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
        self.sidebar.set_queue_info(
            any(it.info is not None and it.info.interlaced for it in self.items.values())
        )
        self._refresh_queue_bar()
        if finished:
            self._show_summary = True
        elif self.running:
            self._show_summary = False
        finished = finished or getattr(self, "_show_summary", False)
        items = [self.items[i] for i in self.order]
        n = len(items)
        convertible = [it for it in items if it.state not in ("unsupported",)]
        if self._convert_after_captions and not self.running:
            self.f_title.setText("Waiting for captions")
            self.f_sub.setText("Listo converts as soon as they're ready.")
        job = self.join_job
        if self.running and job is not None and job.thread is not None:
            self.f_bar.show()
            self.f_bar.setValue(int(min(1.0, job.done_s / job.total_s) * 1000) if job.total_s else 0)
            self.f_title.setText(f"Joining {len(job.parts)} clips into one video")
            self.f_sub.setText("Putting the converted clips together, without re-encoding…")
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
            busy = len(self.active)
            what = (
                f"{busy} files at once" if busy > 1 else f"{min(finished_n + 1, len(batch))} of {len(batch)}"
            )
            self.f_title.setText(("Paused — " if self.paused else "Converting ") + what)
            remaining_media = sum(
                it.length * (1 - it.frac)
                for it in batch
                if it.state not in FINAL and it.kind in ("video", "audio")
            )
            photos_left = sum(1 for it in batch if it.state not in FINAL and it.kind == "photo")
            speed = self._total_speed()
            if speed > 0 and not self.paused:
                self.f_sub.setText(
                    f"{finished_n} of {len(batch)} done · about {_eta(remaining_media / speed + photos_left * 0.6)} left · {speed:.1f}× speed"
                )
            else:
                self.f_sub.setText("Working out how long this will take…" if not self.paused else "Paused")
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
            self.f_title.setText(("Listo! " if ok else "Finished — ") + " · ".join(parts))
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

    def _scroll_to(self, w: QWidget) -> None:
        QTimer.singleShot(50, lambda: self.scroll.ensureWidgetVisible(w, 0, 60))

    # ------------------------------------------------------------------ misc
    def _hardware_found(self, hw: dict) -> None:
        self.sidebar.apply_hardware(hw)

    def _missing_ffmpeg(self) -> None:
        QMessageBox.warning(
            self,
            "ffmpeg is missing",
            "Listo couldn't find its copy of ffmpeg, so it can only convert photos right now.\n\n"
            "If you're running from source, run:  python scripts/fetch_ffmpeg.py",
        )

    def _about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {__version__}<br>Drop it in. Get it back edit-ready.<br><br>"
            f"<span style='color:{theme.MUTED}'>{self.caps.version or 'ffmpeg not found'}</span><br>"
            "Video conversion by <a href='https://ffmpeg.org'>FFmpeg</a> (GPL).",
        )

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        md = e.mimeData()
        if md.hasUrls() or is_link(md.text()):
            e.acceptProposedAction()
            self.drop.set_hot(True)

    def dragLeaveEvent(self, e) -> None:
        self.drop.set_hot(False)

    def dropEvent(self, e: QDropEvent) -> None:
        self.drop.set_hot(False)
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

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if self.titlebar is not None and not getattr(self, "_titlebar_fitted", False):
            self._titlebar_fitted = True
            self.titlebar.fit()
            handle = self.windowHandle()
            if handle is not None and hasattr(handle, "safeAreaMarginsChanged"):
                handle.safeAreaMarginsChanged.connect(lambda *_a: self.titlebar.fit())

    def closeEvent(self, e) -> None:
        if self.running:
            ans = QMessageBox.question(
                self,
                "Stop converting?",
                "A conversion is still running. Quit and stop it? The unfinished file will be cleaned up.",
            )
            if ans != QMessageBox.StandardButton.Yes:
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
        self.export_panel.player.release()
        self.pool.clear()
        self.pool.waitForDone(3000)
        self.qs.setValue("geometry", self.saveGeometry())
        import json

        self.qs.setValue("settings", json.dumps(self.settings.to_dict()))


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
