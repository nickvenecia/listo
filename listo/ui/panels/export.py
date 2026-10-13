"""Saves To, in the right panel: the live preview (placed at the panel's top), joining, the example name, where
files go, what they're called, and the advanced options."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from listo.core import join, naming
from listo.core.log import get_logger
from listo.core.presets import Settings
from listo.core.probe import MediaInfo
from listo.core.store import Prefs
from listo.ui.components.player import ClipPlayer
from listo.ui.components.widgets import (
    Card,
    Disclosure,
    ElidedLabel,
    FlowLayout,
    PathCombo,
    Section,
    ToggleRow,
    combo,
    hbox,
    set_combo,
    vbox,
)
from listo.ui.style.tokens import INSPECTOR_W, SCROLL_GUTTER, SPACE_1, SPACE_2, SPACE_3, SPACE_4

log = get_logger(__name__)

NAME_STYLES: tuple[tuple[str, str, str], ...] = (
    ("same", "Same as the Original", "{name}"),
    ("format", "Add the Format", "{name}_{preset}"),
    ("date", "Shoot Date First", "{date}_{name}"),
    ("numbered", "Folder Name + Number", "{folder}_{n}"),
    ("custom", "Your Own Pattern", ""),
)
FRIENDLY_TOKENS: tuple[tuple[str, str], ...] = (
    ("name", "Name"),
    ("preset", "Format"),
    ("date", "Date"),
    ("time", "Time"),
    ("res", "Size"),
    ("height", "Height"),
    ("fps", "Frame Rate"),
    ("n", "Counter"),
    ("folder", "Folder"),
    ("ext", "Old Extension"),
)
WHERE = [  # then the folders picked before, then "Choose a Destination…" (a PathCombo)
    ("source", "In Source Folder", "Next to each original file"),
    ("subfolder", "Create Subfolder", "A new folder next to each original, with the name you give it"),
]


def style_for(template: str) -> str:
    for key, _, tpl in NAME_STYLES:
        if tpl and tpl == (template or "{name}"):
            return key
    return "custom"


def picture_width(panel_w: int) -> int:
    """The preview's width in a right panel this wide (its padding and scroll bar room taken off)."""
    return panel_w - 2 * SPACE_4 - SCROLL_GUTTER


class ExportSettings(QWidget):
    changed = Signal()
    preview_clicked = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.s = settings
        self._panel_w = INSPECTOR_W
        self._sample: tuple[str, MediaInfo | None, str] | None = None
        self._custom_text = (
            settings.naming if style_for(settings.naming) == "custom" else "{name}_{preset}_{date}"
        )

        lay = vbox(self, 0, SPACE_3)

        # ---- live preview: the picked (or first) clip with every setting applied (the panel puts it on top)
        self.preview_box = prev = QWidget()
        vbox(prev, 0, SPACE_1)
        pic_w = picture_width(INSPECTOR_W)
        # Paused: the exact result (MainWindow renders it). Playing: the clip with its captions, with sound.
        self.player = ClipPlayer(pic_w, round(pic_w * 9 / 16))
        self.player.stage.setCursor(Qt.CursorShape.PointingHandCursor)
        self.player.stage.setToolTip("Click for a bigger preview")
        self.player.clicked.connect(self.preview_clicked)
        self.player.set_message("Making a preview…")
        prev.layout().addWidget(self.player)
        self.picture_note = ElidedLabel("")
        self.picture_note.setObjectName("Hint")
        prev.layout().addWidget(self.picture_note)

        card = Card("Saves To")

        # ---- separate files, or every video in one (only when there are 2+ videos to join)
        self._videos = 0
        self._last_video = ""
        self.videos_sec = Section("Videos")
        self.join_pick = combo(
            [
                ("separate", "One File per Clip", "Each clip becomes its own file"),
                ("join", "Join Into One Video", "Every clip, in list order, becomes one long video"),
            ],
            "join" if self.s.join else "separate",
        )
        self.join_pick.currentIndexChanged.connect(
            lambda _i: self._set("join", self.join_pick.currentData() == "join")
        )
        self.videos_sec.add(self.join_pick)
        card.add(self.videos_sec)

        # ---- live example of the file name
        saves = Section()
        ex = QFrame()
        ex.setObjectName("Example")
        el = vbox(ex, (SPACE_4, SPACE_3, SPACE_4, SPACE_3), SPACE_1)
        self.ex_from = ElidedLabel("", Qt.TextElideMode.ElideMiddle)
        self.ex_from.setObjectName("ExFrom")
        self.ex_to = ElidedLabel("", Qt.TextElideMode.ElideLeft)
        self.ex_to.setObjectName("ExTo")
        self.ex_note = QLabel()
        self.ex_note.setObjectName("Hint")
        self.ex_note.setWordWrap(True)
        el.addWidget(self.ex_from)
        el.addWidget(self.ex_to)
        el.addWidget(self.ex_note)
        saves.add(ex)
        card.add(saves)

        # ---- where
        where = Section("Where")
        self.where = PathCombo(
            Prefs(), "recent_folders", WHERE, "Choose a Destination…", self._ask_folder,
            folders=True,
        )  # fmt: skip
        self.where.set_value(self._where_value())
        self.where.picked.connect(self._destination)
        where.add(self.where)
        self.d_sub_row = QWidget()
        sr = hbox(self.d_sub_row, (0, SPACE_1, 0, 0))
        lbl = QLabel("Folder Name")
        lbl.setObjectName("Muted")
        self.d_sub = QLineEdit(self.s.subfolder_name)
        self.d_sub.setPlaceholderText("Listo")
        self.d_sub.textChanged.connect(lambda t: self._set("subfolder_name", t.strip() or "Listo"))
        sr.addWidget(lbl)
        sr.addWidget(self.d_sub, 1)
        where.add(self.d_sub_row)
        card.add(where)

        # ---- name
        name = Section("Name")
        self.styles = combo([(k, t, "") for k, t, _ in NAME_STYLES], style_for(self.s.naming))
        self.styles.currentIndexChanged.connect(lambda _i: self._style(self.styles.currentData()))
        name.add(self.styles)
        self.custom_box = QWidget()
        cb = vbox(self.custom_box, (0, SPACE_1, 0, 0), SPACE_2)
        self.n_edit = QLineEdit(self._custom_text)
        self.n_edit.setPlaceholderText("{name}")
        self.n_edit.textChanged.connect(self._custom_changed)
        cb.addWidget(self.n_edit)
        self.tok_wrap = tok_wrap = QWidget()
        self.tok_flow = flow = FlowLayout(tok_wrap)
        for key, label in FRIENDLY_TOKENS:
            b = QPushButton(f"+ {label}")
            b.setObjectName("Token")
            b.setToolTip(dict(naming.TOKENS)[key] + "   {" + key + "}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._insert_token(k))
            flow.addWidget(b)
        cb.addWidget(tok_wrap)
        name.add(self.custom_box)
        card.add(name)
        lay.addWidget(card)

        # ---- collisions + dates
        taken = Section("Name Taken")
        self.collision = combo(
            [
                ("number", "Add a Number", "photo.jpg becomes photo_2.jpg"),
                ("skip", "Skip the File", "Leave the existing file alone and don't convert this one"),
                ("replace", "Replace the Old Copy", "Overwrite the earlier converted file"),
            ],
            self.s.collision,
        )
        self.collision.setToolTip("Your original files are never touched, whatever you pick")
        self.collision.currentIndexChanged.connect(
            lambda _i: self._set("collision", self.collision.currentData())
        )
        taken.add(self.collision)
        self.adv = Disclosure(
            "Advanced Options",
            is_open=Prefs().value("export_advanced_open", False, type=bool),
        )
        self.adv.toggled.connect(lambda on: Prefs().setValue("export_advanced_open", on))
        self.adv.add(taken)

        after = Section("After Converting")
        self.k_dates = ToggleRow("Keep the Original File Dates")
        self.k_dates.setChecked(self.s.keep_dates)
        self.k_dates.toggled.connect(lambda v: self._set("keep_dates", v))
        after.add(self.k_dates)
        self.k_verify = ToggleRow("Double-Check Each File")
        self.k_verify.setToolTip(
            "Re-reads every new video and audio file and flags it if the length doesn't match the original"
        )
        self.k_verify.setChecked(self.s.verify)
        self.k_verify.toggled.connect(lambda v: self._set("verify", v))
        after.add(self.k_verify)
        self.adv.add(after)
        lay.addWidget(self.adv)
        self._sync()

    def set_panel_width(self, panel_w: int) -> None:
        """The right panel's width changed (a smaller window): the preview and the name tokens follow."""
        if panel_w == self._panel_w:
            return
        self._panel_w = panel_w
        w = picture_width(panel_w)
        self.player.set_size(w, round(w * 9 / 16))
        self._sync()

    # ------------------------------------------------------------------ behavior
    def _set(self, attr: str, value) -> None:
        setattr(self.s, attr, value)
        self._update_example()
        self._update_advanced()
        self.changed.emit()

    def _update_advanced(self) -> None:
        base = Settings()
        n = sum(1 for k in ("collision", "keep_dates", "verify") if getattr(self.s, k) != getattr(base, k))
        self.adv.set_summary(f"{n} changed" if n else "")

    def _where_value(self) -> str:
        """The Where dropdown's value: "source", "subfolder" or the chosen folder."""
        return (
            self.s.dest_folder
            if self.s.destination == "folder" and self.s.dest_folder
            else self.s.destination
        )

    def _ask_folder(self, start: str) -> str:
        return QFileDialog.getExistingDirectory(self, "Save Converted Files To…", start)

    def _destination(self, value: str) -> None:
        if value in ("source", "subfolder"):
            self._set("destination", value)
        else:
            self.s.dest_folder = value
            self._set("destination", "folder")
        self._sync()

    def _style(self, key: str) -> None:
        if key == "custom":
            self._set("naming", self.n_edit.text() or "{name}")
        else:
            self._set("naming", dict((k, tpl) for k, _, tpl in NAME_STYLES)[key])
        self._sync()

    def _custom_changed(self, text: str) -> None:
        if self.styles.currentData() == "custom":
            self._set("naming", text)

    def _insert_token(self, key: str) -> None:
        self.n_edit.insert("{" + key + "}")
        self.n_edit.setFocus()

    def _sync(self) -> None:
        dest = self.s.destination
        self.d_sub_row.setVisible(dest == "subfolder")
        self.custom_box.setVisible(self.styles.currentData() == "custom")
        self.videos_sec.setVisible(self._videos >= 2 and join.can_join(self.s))
        self._update_advanced()
        # The dialog sizes itself before it knows its width; reserve room for every wrapped row.
        self.tok_wrap.ensurePolished()
        for i in range(self.tok_flow.count()):
            self.tok_flow.itemAt(i).widget().ensurePolished()
        room = picture_width(self._panel_w) - 2 * SPACE_3  # inside the Saves To card
        self.tok_wrap.setMinimumHeight(self.tok_flow.heightForWidth(room))
        self._update_example()

    def reload(self) -> None:
        """Refresh controls from the settings (after a recipe is applied)."""
        widgets = (
            self.join_pick,
            self.where,
            self.d_sub,
            self.styles,
            self.n_edit,
            self.collision,
            self.k_dates,
            self.k_verify,
        )
        for w in widgets:
            w.blockSignals(True)
        try:
            set_combo(self.join_pick, "join" if self.s.join else "separate")
            self.where.set_value(self._where_value())
            self.d_sub.setText(self.s.subfolder_name)
            style = style_for(self.s.naming)
            set_combo(self.styles, style)
            if style == "custom":
                self.n_edit.setText(self.s.naming)
            set_combo(self.collision, self.s.collision)
            self.k_dates.setChecked(self.s.keep_dates)
            self.k_verify.setChecked(self.s.verify)
        finally:
            for w in widgets:
                w.blockSignals(False)
        self._sync()

    def set_video_count(self, n: int, last: str = "") -> None:
        """How many videos are in the list (joining only appears with two or more) and the last one
        (a joined video is named after the first and last clip)."""
        if (n, last) != (self._videos, self._last_video):
            self._videos, self._last_video = n, last
            self._sync()

    def refresh(self) -> None:
        """The format may have changed (a GIF can't be joined)."""
        self._sync()

    def joining(self) -> bool:
        return self.s.join and self._videos >= 2 and join.can_join(self.s)

    def set_sample(self, path: str | None, info: MediaInfo | None, kind: str) -> None:
        self._sample = (path, info, kind) if path else None
        self._update_example()

    def _example_for(self, template: str) -> str:
        path, info, kind = self._sample_tuple()
        saved = self.s.naming
        try:
            self.s.naming = template
            return naming.planned_name(path, info, self.s, kind, 1)
        except Exception:
            return "?"
        finally:
            self.s.naming = saved

    def _sample_tuple(self):
        if self._sample:
            return self._sample
        return (
            str(Path.home() / "Footage" / "A001_C003.MOV"),
            MediaInfo(kind="video", width=3840, height=2160, fps=23.976),
            "video",
        )

    def _update_example(self) -> None:
        path, info, kind = self._sample_tuple()
        p = Path(path)
        joined = self.joining() and kind == "video"
        try:
            out_dir = naming.output_dir(path, self.s, kind)
            if joined:
                name = join.joined_name(path, info, self.s, self._last_video)
            else:
                name = naming.planned_name(path, info, self.s, kind, 1)
        except Exception:
            out_dir, name = p.parent, "?"
        self.ex_from.set_full_text(
            f"{p.name} … {Path(self._last_video).name} ({self._videos} clips)"
            if joined
            else f"{p.parent.name}/{p.name}"
        )
        note = f"All {self._videos} videos in one file, in list order." if joined else ""
        try:
            target, _ = naming.resolve_output(path, out_dir / name, self.s.collision, set())
            if target is None:
                note = "A file with this name is already there, so this one would be skipped."
            elif target.name != name:
                same = naming.reserve_key(out_dir / name) == naming.reserve_key(Path(path))
                note = (
                    "Same name as the original, so a number is added to keep the original safe."
                    if same
                    else "That name is taken, so a number is added."
                ) + (f" {note}" if note else "")
                name = target.name
        except Exception:
            log.debug("example name failed", exc_info=True)
        self.ex_to.set_full_text(f"→  {out_dir.name}/{name}")
        self.ex_note.setText(note)
        self.ex_note.setVisible(bool(note))
        for i, (_key, _, tpl) in enumerate(NAME_STYLES):  # hover an item to see its result
            tip = self._example_for(tpl) if tpl else "Build it from name, format, date…"
            self.styles.setItemData(i, tip, Qt.ItemDataRole.ToolTipRole)

    # ------------------------------------------------------------------ preview
    def show_preview(self, png: bytes, note: str, at: float | None = None) -> None:
        """The exact result frame at `at` seconds (or why there isn't one)."""
        pm = QPixmap()
        if png and pm.loadFromData(png):
            self.player.set_still(pm, at)
        else:
            self.player.set_still(None)
            self.player.set_message(note or "No preview")
        self.picture_note.set_full_text(note if png else "")
