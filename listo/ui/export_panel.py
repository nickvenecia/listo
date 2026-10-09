"""The export panel (right side): live preview, where files go, what they're called, and Convert."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from ..core import naming
from ..core.log import get_logger
from ..core.presets import Settings
from ..core.probe import MediaInfo
from .job_card import ElidedLabel
from .tokens import EXPORT_W, SCROLL_GUTTER, SPACE_1, SPACE_2, SPACE_3, SPACE_4
from .widgets import (
    ClickLabel,
    Disclosure,
    FitScroll,
    FlowLayout,
    Section,
    StepHeader,
    ToggleRow,
    combo,
    hbox,
    hint,
    set_combo,
    vbox,
)

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
WHERE = (
    ("source", "Next to the Original"),
    ("subfolder", "In a Subfolder"),
    ("folder", "In a Folder I Pick…"),
)


def style_for(template: str) -> str:
    for key, _, tpl in NAME_STYLES:
        if tpl and tpl == (template or "{name}"):
            return key
    return "custom"


def summary(s: Settings) -> tuple[str, str]:
    """Short (where, name) text for the bottom bar."""
    if s.destination == "folder" and s.dest_folder:
        where = Path(s.dest_folder).name or s.dest_folder
    elif s.destination == "subfolder":
        where = f"“{s.subfolder_name or 'Listo'}” subfolders"
    else:
        where = "Next to Originals"
    style = style_for(s.naming)
    name = s.naming if style == "custom" else dict((k, t) for k, t, _ in NAME_STYLES)[style]
    return where, name


class ExportPanel(QFrame):
    changed = Signal()
    preview_clicked = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ExportPanel")
        self.setFixedWidth(EXPORT_W)
        self.s = settings
        self._sample: tuple[str, MediaInfo | None, str] | None = None
        self._custom_text = (
            settings.naming if style_for(settings.naming) == "custom" else "{name}_{preset}_{date}"
        )

        outer = vbox(self, 0, 0)
        outer.addWidget(StepHeader(3, "Export"))
        scroll = FitScroll()
        outer.addWidget(scroll, 1)
        inner = QWidget()
        scroll.setWidget(inner)
        lay = vbox(inner, (SPACE_4, SPACE_3, SPACE_4 - SCROLL_GUTTER, SPACE_4), SPACE_3)

        # ---- live preview: the selected (or first) clip with every setting applied
        prev = Section("Preview")
        pic_w = EXPORT_W - 2 * SPACE_4 - 1  # (the panel's 1 px edge)
        self.picture = ClickLabel("Making a preview…")
        self.picture.setObjectName("Preview")
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setFixedSize(pic_w, round(pic_w * 9 / 16))
        self.picture.setCursor(Qt.CursorShape.PointingHandCursor)
        self.picture.setToolTip("Click for a bigger preview you can scrub through")
        self.picture.clicked.connect(self.preview_clicked)
        prev.add(self.picture)
        self.picture_note = ElidedLabel("", Qt.TextElideMode.ElideMiddle)
        self.picture_note.setObjectName("Hint")
        prev.add(self.picture_note)
        lay.addWidget(prev)

        # ---- live example of the file name
        saves = Section("Saves As")
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
        lay.addWidget(saves)

        # ---- where
        where = Section("Where")
        self.where = combo([(k, t, "") for k, t in WHERE], self.s.destination)
        self.where.currentIndexChanged.connect(lambda _i: self._destination(self.where.currentData()))
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
        self.d_folder_row = QWidget()
        fr = hbox(self.d_folder_row, (0, SPACE_1, 0, 0))
        self.d_path = ElidedLabel("", Qt.TextElideMode.ElideLeft)
        self.d_path.setObjectName("Muted")
        self.d_pick = QPushButton("Change…")
        self.d_pick.setCursor(Qt.CursorShape.PointingHandCursor)
        self.d_pick.clicked.connect(self._choose_folder)
        fr.addWidget(self.d_path, 1)
        fr.addWidget(self.d_pick)
        where.add(self.d_folder_row)
        self.d_proxy_hint = hint("Edit proxies go into a Proxy folder next to the original.")
        where.add(self.d_proxy_hint)
        lay.addWidget(where)

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
        lay.addWidget(name)

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
            is_open=QSettings("Listo", "Listo").value("export_advanced_open", False, type=bool),
        )
        self.adv.toggled.connect(lambda on: QSettings("Listo", "Listo").setValue("export_advanced_open", on))
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
        lay.addStretch(1)

        # ---- the action, always visible at the bottom
        bottom = QFrame()
        bottom.setObjectName("PanelBottom")
        self.bottom = vbox(bottom, SPACE_4, SPACE_2)
        outer.addWidget(bottom)
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

    def _destination(self, key: str) -> None:
        if key == "folder" and not self.s.dest_folder and not self._choose_folder():
            set_combo(self.where, self.s.destination)
            return
        self._set("destination", key)
        self._sync()

    def _choose_folder(self) -> bool:
        start = self.s.dest_folder or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Save Converted Files To…", start)
        if d:
            self.s.dest_folder = d
            set_combo(self.where, "folder")
            self._set("destination", "folder")
            self._sync()
            return True
        return False

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
        self.d_folder_row.setVisible(dest == "folder")
        self.d_path.setText(self.s.dest_folder or "No Folder Chosen")
        self.d_proxy_hint.setVisible(self.s.video_preset == "proxy" and dest == "source")
        self.custom_box.setVisible(self.styles.currentData() == "custom")
        self._update_advanced()
        # The dialog sizes itself before it knows its width; reserve room for every wrapped row.
        self.tok_wrap.ensurePolished()
        for i in range(self.tok_flow.count()):
            self.tok_flow.itemAt(i).widget().ensurePolished()
        self.tok_wrap.setMinimumHeight(self.tok_flow.heightForWidth(EXPORT_W - 2 * SPACE_4 - SPACE_2))
        self._update_example()

    def reload(self) -> None:
        """Refresh controls from the settings (after a recipe is applied)."""
        widgets = (
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
            set_combo(self.where, self.s.destination)
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
        try:
            out_dir = naming.output_dir(path, self.s, kind)
            name = naming.planned_name(path, info, self.s, kind, 1)
        except Exception:
            out_dir, name = p.parent, "?"
        self.ex_from.setText(f"{p.parent.name}/{p.name}")
        note = ""
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
                )
                name = target.name
        except Exception:
            log.debug("example name failed", exc_info=True)
        self.ex_to.setText(f"→  {out_dir.name}/{name}")
        self.ex_note.setText(note)
        self.ex_note.setVisible(bool(note))
        for i, (_key, _, tpl) in enumerate(NAME_STYLES):  # hover an item to see its result
            tip = self._example_for(tpl) if tpl else "Build it from name, format, date…"
            self.styles.setItemData(i, tip, Qt.ItemDataRole.ToolTipRole)

    # ------------------------------------------------------------------ preview
    def show_preview(self, png: bytes, note: str) -> None:
        pm = QPixmap()
        if png and pm.loadFromData(png):
            self.picture.setPixmap(
                pm.scaled(
                    self.picture.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.picture.setPixmap(QPixmap())
            self.picture.setText(note or "No preview")
        self.picture_note.setText(note if png else "")
