"""The main window: queue on the left, settings on the right, controls at the bottom."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QActionGroup, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .. import APP_NAME, __version__, naming
from ..engine import Conversion, Result
from ..fileutil import reveal
from ..presets import (
    AUDIO_FORMATS, OVERRIDE_KEYS, PHOTO_FORMATS, VIDEO_GROUPS, VIDEO_PRESETS, Settings, format_label,
)
from ..probe import KNOWN_EXTS, UNSUPPORTED_HINTS, MediaInfo, ext_of, fmt_duration, kind_from_ext
from ..tools import capabilities
from . import theme
from .job_card import JobCard
from .save_dialog import SaveDialog, summary as save_summary
from .sidebar import Sidebar
from .widgets import Toast, repolish
from .workers import ConvertThread, HardwareSignals, HardwareTask, ProbeSignals, ProbeTask

FINAL = ("done", "warning", "failed", "skipped", "canceled", "unsupported")


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

    @property
    def weight(self) -> float:
        """How much of the batch this file is, in 'seconds of media'."""
        if self.info and self.info.duration and self.kind in ("video", "audio"):
            return max(self.info.duration, 1.0)
        return 2.0

    @property
    def frac(self) -> float:
        if self.state in ("done", "warning"):
            return 1.0
        if self.state in ("converting", "paused") and self.info and self.info.duration:
            return min(1.0, self.processed / self.info.duration)
        return 0.0


class DropZone(QFrame):
    def __init__(self, on_click):
        super().__init__()
        self.setObjectName("DropZone")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._on_click = on_click
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(theme.pixmap("drop", 44, theme.ACCENT, 1.6))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Drop videos, photos or audio here")
        title.setObjectName("DropTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("or click to choose files — folders work too")
        sub.setObjectName("DropSub")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fmts = QLabel("MOV · MP4 · MTS · MXF · AVI · MKV · MOD · MPG · HEIC · RAW · JPG · PNG · WAV · AIFF · MP3 …")
        fmts.setObjectName("DropFormats")
        fmts.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fmts.setWordWrap(True)
        lay.addWidget(ic)
        lay.addSpacing(4)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addSpacing(8)
        lay.addWidget(fmts)

    def set_hot(self, on: bool) -> None:
        self.setProperty("hot", "true" if on else "false")
        repolish(self)

    def mousePressEvent(self, e):  # noqa: N802
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
        except Exception:  # noqa: BLE001
            self.settings = Settings()

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
        self.caps = capabilities()

        self._build()
        self._menus()
        self.sidebar.apply_capabilities(self.caps)
        self.pool.start(HardwareTask(self.hw_signals))
        self._update_save_button()
        self._refresh_footer()
        self.centralWidget().setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        QTimer.singleShot(0, self.centralWidget().setFocus)

        geo = self.qs.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1000, 660)
        self.setMinimumSize(QSize(780, 520))

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

        header = QFrame()
        header.setObjectName("Header")
        h = QHBoxLayout(header)
        h.setContentsMargins(18, 9, 16, 9)
        word = QLabel(f'listo<span style="color:{theme.ACCENT}">.</span>')
        word.setObjectName("Wordmark")
        word.setTextFormat(Qt.TextFormat.RichText)
        tag = QLabel("Drop it in. Get it back edit-ready.")
        tag.setObjectName("Tagline")
        h.addWidget(word)
        h.addSpacing(12)
        h.addWidget(tag, 0, Qt.AlignmentFlag.AlignBottom)
        h.addStretch(1)
        v.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.queue_stack = QStackedWidget()
        empty_wrap = QWidget()
        ew = QVBoxLayout(empty_wrap)
        ew.setContentsMargins(18, 18, 18, 18)
        self.drop = DropZone(self.pick_files)
        ew.addWidget(self.drop)
        self.queue_stack.addWidget(empty_wrap)

        queue_page = QWidget()
        qp = QVBoxLayout(queue_page)
        qp.setContentsMargins(0, 0, 0, 0)
        qp.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(20, 10, 14, 0)
        self.q_count = QLabel()
        self.q_count.setObjectName("SectionLabel")
        bar.addWidget(self.q_count)
        bar.addSpacing(10)
        self.btn_add = QPushButton(" Add files")
        self.btn_add.setIcon(theme.icon("plus", theme.MUTED))
        self.btn_add.clicked.connect(self.pick_files)
        self.btn_folder = QPushButton(" Add folder")
        self.btn_folder.setIcon(theme.icon("folder", theme.MUTED))
        self.btn_folder.clicked.connect(self.pick_folder)
        for b in (self.btn_add, self.btn_folder):
            b.setObjectName("Ghost")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            bar.addWidget(b)
        bar.addStretch(1)
        self.btn_rm_done = QPushButton("Remove finished")
        self.btn_rm_done.setObjectName("Ghost")
        self.btn_rm_done.setToolTip("Take converted, skipped and failed files off the list")
        self.btn_rm_done.clicked.connect(self.clear_finished)
        self.btn_clear_all = QPushButton("Clear list")
        self.btn_clear_all.setObjectName("Ghost")
        self.btn_clear_all.setToolTip("Empty the list (your files aren't touched)")
        self.btn_clear_all.clicked.connect(self.clear_all)
        for b in (self.btn_rm_done, self.btn_clear_all):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            bar.addWidget(b)
        qp.addLayout(bar)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lst = QWidget()
        self.list_lay = QVBoxLayout(lst)
        self.list_lay.setContentsMargins(18, 6, 12, 14)
        self.list_lay.setSpacing(6)
        self.list_lay.addStretch(1)
        self.scroll.setWidget(lst)
        qp.addWidget(self.scroll, 1)
        self.queue_stack.addWidget(queue_page)
        body.addWidget(self.queue_stack, 1)

        self.sidebar = Sidebar(self.settings)
        self.sidebar.changed.connect(self._settings_changed)
        self.save_dialog = SaveDialog(self.settings, self)
        self.save_dialog.changed.connect(self._settings_changed)
        self.sidebar.recipe_applied.connect(self.save_dialog.reload)
        body.addWidget(self.sidebar)
        v.addLayout(body, 1)

        footer = QFrame()
        footer.setObjectName("Footer")
        f = QHBoxLayout(footer)
        f.setContentsMargins(18, 10, 14, 10)
        f.setSpacing(10)
        left = QVBoxLayout()
        left.setSpacing(4)
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
        self.btn_save = QPushButton()
        self.btn_save.setObjectName("SaveBtn")
        self.btn_save.setIcon(theme.icon("folder", theme.MUTED))
        self.btn_save.setToolTip("Where converted files go and how they're named")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self.open_save_options)
        f.addWidget(self.btn_save)
        self.btn_show = QPushButton("Show files")
        self.btn_show.setObjectName("Ghost")
        self.btn_show.clicked.connect(self._show_outputs)
        self.btn_show.hide()
        self.btn_pause = QPushButton(" Pause")
        self.btn_pause.setIcon(theme.icon("pause"))
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_cancel = QPushButton("Stop")
        self.btn_cancel.setObjectName("Danger")
        self.btn_cancel.clicked.connect(self.stop)
        self.btn_start = QPushButton("Convert")
        self.btn_start.setObjectName("Primary")
        self.btn_start.clicked.connect(self.start)
        for b in (self.btn_show, self.btn_pause, self.btn_cancel, self.btn_start):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            f.addWidget(b)
        v.addWidget(footer)
        self.toast = Toast(root)

    def _menus(self) -> None:
        m = self.menuBar().addMenu("File")
        a = QAction("Add Files…", self)
        a.setShortcut(QKeySequence.StandardKey.Open)
        a.triggered.connect(self.pick_files)
        m.addAction(a)
        a = QAction("Add Folder…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+O"))
        a.triggered.connect(self.pick_folder)
        m.addAction(a)
        m.addSeparator()
        a = QAction("Convert", self)
        a.setShortcut(QKeySequence("Ctrl+Return"))
        a.triggered.connect(self.start)
        m.addAction(a)
        h = self.menuBar().addMenu("Help")
        a = QAction(f"About {APP_NAME}", self)
        a.setMenuRole(QAction.MenuRole.AboutRole)
        a.triggered.connect(self._about)
        h.addAction(a)

    # ------------------------------------------------------------------ adding files
    def pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Add files", self._last_dir())
        if files:
            self._remember_dir(files[0])
            self.add_paths(files)

    def pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Add a folder", self._last_dir())
        if d:
            self._remember_dir(d)
            self.add_paths([d])

    def _last_dir(self) -> str:
        return str(self.qs.value("last_dir", str(Path.home())))

    def _remember_dir(self, p: str) -> None:
        self.qs.setValue("last_dir", str(Path(p).parent if Path(p).is_file() else p))

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
                        else:
                            skipped += 1
            elif pp.is_file():
                to_add.append((str(pp), True))
        for path, explicit in to_add:
            key = naming.reserve_key(Path(path))
            if key in existing:
                dupes += 1
                continue
            existing.add(key)
            self._add_item(path)
            added += 1
        msgs = []
        if dupes:
            msgs.append(f"{dupes} already in the list")
        if skipped:
            msgs.append(f"skipped {skipped} file{'s' if skipped != 1 else ''} that aren't video, photo or audio")
        if added:
            self._show_summary = False
        if msgs:
            self.toast.show_message((f"Added {added}. " if added else "") + "; ".join(msgs).capitalize() + ".")
        self._refresh_footer()
        if self.running:
            self._kick()

    def _add_item(self, path: str) -> None:
        iid = self._next_id
        self._next_id += 1
        kind = kind_from_ext(path)
        it = Item(iid, path, kind)
        if self.running:
            self.reserved.add(naming.reserve_key(Path(path)))
        card = JobCard(iid, Path(path).name, kind)
        card.remove.connect(self.remove_item)
        card.retry.connect(self.retry_item)
        card.reveal.connect(self.reveal_item)
        card.details.connect(self.show_details)
        card.format_clicked.connect(self._format_menu)
        it.card = card
        self.items[iid] = it
        self.order.append(iid)
        self.list_lay.insertWidget(self.list_lay.count() - 1, card)
        self.queue_stack.setCurrentIndex(1)
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
        self._update_sample()
        self._refresh_footer()
        if self.running:
            self._kick()

    def eff(self, it: Item) -> Settings:
        """The settings this file will actually convert with."""
        return (it.base or self.settings).with_override(it.override)

    def _update_output_name(self, it: Item) -> None:
        if not it.info or it.state in ("unsupported",) or it.state in FINAL and it.result and it.result.output:
            return
        s = self.eff(it)
        it.card.set_format(format_label(it.kind, s), bool(it.override), it.state in ("ready", "waiting"))
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
        except Exception:  # noqa: BLE001
            pass

    def _update_sample(self) -> None:
        for iid in self.order:
            it = self.items[iid]
            if it.info and it.state not in ("unsupported",):
                self.save_dialog.set_sample(it.path, it.info, it.kind)
                return
        self.save_dialog.set_sample(None, None, "video")

    def open_save_options(self) -> None:
        self.save_dialog.exec()
        self._settings_changed()

    def _update_save_button(self) -> None:
        where, name = save_summary(self.settings)
        self.btn_save.setText(f"  Save: {where}  ·  {name}")

    def _settings_changed(self) -> None:
        import json

        self._update_save_button()
        self.sidebar.notify_external_change()
        self.qs.setValue("settings", json.dumps(self.settings.to_dict()))
        for it in self.items.values():
            if it.state in ("ready", "waiting"):
                self._update_output_name(it)

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

        add(m, "Same as the panel", {}, not it.override)
        if it.kind == "video":
            for gkey, glabel in VIDEO_GROUPS:
                m.addSection(glabel)
                for p in VIDEO_PRESETS:
                    if p.group != gkey or (p.needs and not all(self.caps.has_encoder(e) for e in p.needs)):
                        continue
                    if p.key in ("prores", "dnxhr"):
                        sub = m.addMenu(p.title)
                        for c in p.variants:
                            add(sub, c.label, {"video_preset": p.key, "video_variant": {p.key: c.key}},
                                bool(it.override) and s.video_preset == p.key and s.variant_for(p.key) == c.key)
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
        it.card.setParent(None)
        it.card.deleteLater()
        del self.items[iid]
        self.order.remove(iid)
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
        dlg.resize(640, 420)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(18, 18, 18, 14)
        r = it.result
        title = {"done": "Converted", "failed": "This one didn't convert", "skipped": "Skipped",
                 "warning": "Converted — but double-check it",
                 "unsupported": "Can't convert this file"}.get(it.state, it.state.title())
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
            copy = bb.addButton("Copy details", QDialogButtonBox.ButtonRole.ActionRole)
            copy.clicked.connect(lambda: QApplication.clipboard().setText(
                "\n".join(lines) + "\n\n" + (log.toPlainText() if r.log or r.command else "")))
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

    # ------------------------------------------------------------------ converting
    def start(self) -> None:
        if self.running:
            return
        if not self.caps.ok and any(it.kind != "photo" for it in self.items.values()):
            self._missing_ffmpeg()
            return
        todo = [iid for iid in self.order if self.items[iid].state in ("ready", "probing")]
        if not todo:
            again = [iid for iid in self.order if self.items[iid].state in ("done", "warning", "failed", "canceled", "skipped")]
            if again:
                self.toast.show_message("Everything here is finished. Use ↻ on a file to run it again, or add more.")
            return
        self.batch = []
        self.running, self.paused = True, False
        # Every file in the list counts as "taken": Replace can never overwrite another original.
        self.reserved = {naming.reserve_key(Path(it.path)) for it in self.items.values()}
        self.counter = 0
        self.btn_show.hide()
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
            if it.state == "ready":
                it.base = self.settings.copy()
                it.state = "waiting"
                it.card.set_state("waiting")
                self._update_output_name(it)
                self.batch.append(iid)
            elif it.state == "probing":
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
            if any(self.items.get(i) and self.items[i].state == "probing" for i in self.batch):
                return  # wait for files that are still being read
            self._finish()
            return
        self._refresh_footer()

    def _start_item(self, it: Item) -> None:
        self.counter += 1
        if it.base is None:
            it.base = self.settings.copy()
        s = self.eff(it)
        conv = Conversion(it.path, it.info, s, self.caps, self.reserved, self.counter)
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
        if it.info and it.info.duration and it.speed > 0:
            txt += f" · {_eta(max(0.0, it.info.duration - processed) / it.speed)}"
        it.card.set_state("converting", txt)
        self._refresh_footer()

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
            if r.status == "done":
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
                if r.status in ("failed", "skipped"):
                    card.set_state(r.status)
                    card.set_output(r.message)
                else:
                    card.set_state("canceled")
                    card.set_progress(0)
        if self.running:
            self._kick()
        self._refresh_footer()

    def toggle_pause(self) -> None:
        if not self.running or (not self.active and not self.paused):
            return
        convs = [(self.items.get(i), th.conversion) for i, th in self.active.items() if not th.conversion.canceled]
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
        if not self.running:
            return
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
        self.q_count.setText(f"{n} FILE{'S' if n != 1 else ''}")
        finished = sum(1 for it in items if it.state in ("done", "warning", "failed", "skipped", "canceled"))
        self.btn_rm_done.setVisible(0 < finished < n)
        self.btn_clear_all.setVisible(n > 0 and not self.running)

    def _refresh_footer(self, finished: bool = False) -> None:
        self._refresh_queue_bar()
        if finished:
            self._show_summary = True
        elif self.running:
            self._show_summary = False
        finished = finished or getattr(self, "_show_summary", False)
        items = [self.items[i] for i in self.order]
        n = len(items)
        convertible = [it for it in items if it.state not in ("unsupported",)]
        if self.running:
            batch = [self.items[i] for i in self.batch if i in self.items]
            total_w = sum(it.weight for it in batch) or 1.0
            done_w = sum(it.weight * (1.0 if it.state in FINAL else it.frac) for it in batch)
            finished_n = sum(1 for it in batch if it.state in FINAL)
            self.f_bar.show()
            self.f_bar.setValue(int(done_w / total_w * 1000))
            busy = len(self.active)
            what = f"{busy} files at once" if busy > 1 else f"{min(finished_n + 1, len(batch))} of {len(batch)}"
            self.f_title.setText(("Paused — " if self.paused else "Converting ") + what)
            remaining_media = sum(
                (it.info.duration if it.info else 0) * (1 - it.frac)
                for it in batch if it.state not in FINAL and it.kind in ("video", "audio")
            )
            photos_left = sum(1 for it in batch if it.state not in FINAL and it.kind == "photo")
            speed = self._total_speed()
            if speed > 0 and not self.paused:
                self.f_sub.setText(f"{finished_n} of {len(batch)} done · about {_eta(remaining_media / speed + photos_left * 0.6)} left · {speed:.1f}× speed")
            else:
                self.f_sub.setText("Working out how long this will take…" if not self.paused else "Paused")
            self.btn_start.hide()
            self.btn_save.hide()
            self.btn_pause.show()
            self.btn_cancel.show()
            self.btn_add.setEnabled(True)
            return
        self.btn_start.show()
        self.btn_save.show()
        self.btn_pause.hide()
        self.btn_cancel.hide()
        self.f_bar.hide()
        ready = [it for it in items if it.state in ("ready", "probing")]
        self.btn_start.setEnabled(bool(ready))
        self.btn_start.setText(f"Convert {len(ready)} file{'s' if len(ready) != 1 else ''}" if ready else "Convert")
        if finished and hasattr(self, "_last_summary"):
            d, f, sk, w = self._last_summary
            parts = [f"{d} converted"]
            if w:
                parts.append(f"{w} to check")
            if f:
                parts.append(f"{f} failed")
            if sk:
                parts.append(f"{sk} skipped")
            ok = not f and not w
            self.f_title.setText(("Listo! " if ok else "Finished — ") + " · ".join(parts))
            self.f_sub.setText("Your files are ready." if ok else "Click ⓘ on a file for details.")
            return
        if n == 0:
            self.f_title.setText("Nothing here yet")
            self.f_sub.setText("Add some files to get started.")
            self.btn_show.hide()
            return
        kinds = {"video": 0, "photo": 0, "audio": 0}
        dur = 0.0
        for it in convertible:
            if it.kind in kinds:
                kinds[it.kind] += 1
            if it.info and it.kind in ("video", "audio"):
                dur += it.info.duration
        bits = [f"{c} {k}{'s' if c != 1 else ''}" for k, c in (("video", kinds["video"]), ("photo", kinds["photo"]), ("audio file", kinds["audio"])) if c]
        self.f_title.setText(" · ".join(bits) or "Nothing Listo can convert yet")
        sub = []
        if dur:
            sub.append(f"{fmt_duration(dur)} of media")
        bad = sum(1 for it in items if it.state == "unsupported")
        if bad:
            sub.append(f"{bad} file{'s' if bad != 1 else ''} can't be converted")
        self.f_sub.setText(" · ".join(sub) or "Pick your formats on the right, then hit Convert.")

    def _scroll_to(self, w: QWidget) -> None:
        QTimer.singleShot(50, lambda: self.scroll.ensureWidgetVisible(w, 0, 60))

    # ------------------------------------------------------------------ misc
    def _hardware_found(self, hw: dict) -> None:
        self.sidebar.apply_hardware(hw)

    def _missing_ffmpeg(self) -> None:
        QMessageBox.warning(
            self, "ffmpeg is missing",
            "Listo couldn't find its copy of ffmpeg, so it can only convert photos right now.\n\n"
            "If you're running from source, run:  python scripts/fetch_ffmpeg.py",
        )

    def _about(self) -> None:
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {__version__}<br>Drop it in. Get it back edit-ready.<br><br>"
            f"<span style='color:{theme.MUTED}'>{self.caps.version or 'ffmpeg not found'}</span><br>"
            "Video conversion by <a href='https://ffmpeg.org'>FFmpeg</a> (GPL).",
        )

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.drop.set_hot(True)

    def dragLeaveEvent(self, e) -> None:  # noqa: N802
        self.drop.set_hot(False)

    def dropEvent(self, e: QDropEvent) -> None:  # noqa: N802
        self.drop.set_hot(False)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.add_paths(paths)
            e.acceptProposedAction()

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.running:
            ans = QMessageBox.question(
                self, "Stop converting?",
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
        for th in list(self.active.values()):
            th.wait(30000)
        self.pool.clear()
        self.pool.waitForDone(3000)
        self.qs.setValue("geometry", self.saveGeometry())
        import json

        self.qs.setValue("settings", json.dumps(self.settings.to_dict()))


def _eta(sec: float) -> str:
    sec = int(round(sec))
    if sec < 60:
        return f"{max(sec, 1)}s"
    if sec < 3600:
        return f"{sec // 60}m {sec % 60:02d}s"
    return f"{sec // 3600}h {(sec % 3600) // 60}m"


def _quote(a: str) -> str:
    return f'"{a}"' if (" " in a or not a) else a
