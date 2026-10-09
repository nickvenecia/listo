"""Save options: where converted files go and what they're called (opened from the bottom bar)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from .. import naming
from ..presets import Settings
from ..probe import MediaInfo
from . import theme
from .job_card import ElidedLabel
from .widgets import FlowLayout, OptionList, Segmented, hint, section_label

NAME_STYLES: tuple[tuple[str, str, str], ...] = (
    ("same", "Same as the original", "{name}"),
    ("format", "Add the format", "{name}_{preset}"),
    ("date", "Shoot date first", "{date}_{name}"),
    ("numbered", "Folder name + number", "{folder}_{n}"),
    ("custom", "Your own pattern", ""),
)
FRIENDLY_TOKENS: tuple[tuple[str, str], ...] = (
    ("name", "Name"), ("preset", "Format"), ("date", "Date"), ("time", "Time"),
    ("res", "Size"), ("height", "Height"), ("fps", "Frame rate"), ("n", "Counter"),
    ("folder", "Folder"), ("ext", "Old extension"),
)
WHERE = (("source", "Next to original"), ("subfolder", "In a subfolder"), ("folder", "Pick a folder"))


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
        where = "Next to originals"
    style = style_for(s.naming)
    name = s.naming if style == "custom" else dict((k, t) for k, t, _ in NAME_STYLES)[style]
    return where, name


class SaveDialog(QDialog):
    changed = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Save options")
        self.setFixedWidth(480)
        self.s = settings
        self._sample: tuple[str, MediaInfo | None, str] | None = None
        self._custom_text = settings.naming if style_for(settings.naming) == "custom" else "{name}_{preset}_{date}"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(8)

        title = QLabel("Save options")
        title.setObjectName("DialogTitle")
        lay.addWidget(title)
        lay.addSpacing(4)

        # ---- live example
        ex = QFrame()
        ex.setObjectName("Example")
        el = QVBoxLayout(ex)
        el.setContentsMargins(14, 12, 14, 12)
        el.setSpacing(4)
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
        lay.addWidget(ex)

        # ---- where
        lay.addSpacing(12)
        lay.addWidget(section_label("Where"))
        self.where = Segmented(list(WHERE))
        self.where.set_value(self.s.destination)
        self.where.changed.connect(self._destination)
        lay.addWidget(self.where)
        self.d_sub_row = QWidget()
        sr = QHBoxLayout(self.d_sub_row)
        sr.setContentsMargins(0, 4, 0, 0)
        lbl = QLabel("Folder name")
        lbl.setObjectName("Muted")
        self.d_sub = QLineEdit(self.s.subfolder_name)
        self.d_sub.setPlaceholderText("Listo")
        self.d_sub.textChanged.connect(lambda t: self._set("subfolder_name", t.strip() or "Listo"))
        sr.addWidget(lbl)
        sr.addWidget(self.d_sub, 1)
        lay.addWidget(self.d_sub_row)
        self.d_folder_row = QWidget()
        fr = QHBoxLayout(self.d_folder_row)
        fr.setContentsMargins(0, 4, 0, 0)
        self.d_path = ElidedLabel("", Qt.TextElideMode.ElideLeft)
        self.d_path.setObjectName("Muted")
        self.d_pick = QPushButton("Change…")
        self.d_pick.setCursor(Qt.CursorShape.PointingHandCursor)
        self.d_pick.clicked.connect(self._choose_folder)
        fr.addWidget(self.d_path, 1)
        fr.addWidget(self.d_pick)
        lay.addWidget(self.d_folder_row)
        self.d_proxy_hint = hint("Edit proxies go into a Proxy folder next to the original.")
        lay.addWidget(self.d_proxy_hint)

        # ---- name
        lay.addSpacing(12)
        lay.addWidget(section_label("Name"))
        self.styles = OptionList([(k, t, "") for k, t, _ in NAME_STYLES])
        self.styles.set_value(style_for(self.s.naming))
        self.styles.changed.connect(self._style)
        lay.addWidget(self.styles)
        self.custom_box = QWidget()
        cb = QVBoxLayout(self.custom_box)
        cb.setContentsMargins(0, 4, 0, 0)
        cb.setSpacing(8)
        self.n_edit = QLineEdit(self._custom_text)
        self.n_edit.setPlaceholderText("{name}")
        self.n_edit.textChanged.connect(self._custom_changed)
        cb.addWidget(self.n_edit)
        tok_wrap = QWidget()
        flow = FlowLayout(tok_wrap, 6)
        for key, label in FRIENDLY_TOKENS:
            b = QPushButton(f"+ {label}")
            b.setObjectName("Token")
            b.setToolTip(dict(naming.TOKENS)[key] + "   {" + key + "}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._insert_token(k))
            flow.addWidget(b)
        cb.addWidget(tok_wrap)
        lay.addWidget(self.custom_box)

        # ---- collisions + dates
        lay.addSpacing(12)
        lay.addWidget(section_label("If that name is already taken"))
        self.c_seg = Segmented([("number", "Add a number"), ("skip", "Skip it"), ("replace", "Replace it")])
        self.c_seg.set_value(self.s.collision)
        self.c_seg.changed.connect(lambda k: self._set("collision", k))
        lay.addWidget(self.c_seg)
        lay.addWidget(hint("Your original files are never touched, whatever you pick."))
        lay.addSpacing(6)
        self.k_dates = QCheckBox("Keep the original file dates")
        self.k_dates.setChecked(self.s.keep_dates)
        self.k_dates.toggled.connect(lambda v: self._set("keep_dates", v))
        lay.addWidget(self.k_dates)

        lay.addSpacing(14)
        done_row = QHBoxLayout()
        done_row.addStretch(1)
        done = QPushButton("Done")
        done.setObjectName("Primary")
        done.setDefault(True)
        done.setCursor(Qt.CursorShape.PointingHandCursor)
        done.clicked.connect(self.accept)
        done_row.addWidget(done)
        lay.addLayout(done_row)
        self._sync()

    # ------------------------------------------------------------------ behavior
    def _set(self, attr: str, value) -> None:
        setattr(self.s, attr, value)
        self._update_example()
        self.changed.emit()

    def _destination(self, key: str) -> None:
        if key == "folder" and not self.s.dest_folder:
            if not self._choose_folder():
                self.where.set_value(self.s.destination)
                return
        self._set("destination", key)
        self._sync()

    def _choose_folder(self) -> bool:
        start = self.s.dest_folder or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Save converted files to…", start)
        if d:
            self.s.dest_folder = d
            self.where.set_value("folder")
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
        if self.styles.value() == "custom":
            self._set("naming", text)

    def _insert_token(self, key: str) -> None:
        self.n_edit.insert("{" + key + "}")
        self.n_edit.setFocus()

    def _sync(self) -> None:
        dest = self.s.destination
        self.d_sub_row.setVisible(dest == "subfolder")
        self.d_folder_row.setVisible(dest == "folder")
        self.d_path.setText(self.s.dest_folder or "No folder chosen")
        self.d_proxy_hint.setVisible(self.s.video_preset == "proxy" and dest == "source")
        self.custom_box.setVisible(self.styles.value() == "custom")
        self._update_example()
        self.adjustSize()

    def set_sample(self, path: str | None, info: MediaInfo | None, kind: str) -> None:
        self._sample = (path, info, kind) if path else None
        self._update_example()

    def _example_for(self, template: str) -> str:
        path, info, kind = self._sample_tuple()
        saved = self.s.naming
        try:
            self.s.naming = template
            return naming.planned_name(path, info, self.s, kind, 1)
        except Exception:  # noqa: BLE001
            return "?"
        finally:
            self.s.naming = saved

    def _sample_tuple(self):
        if self._sample:
            return self._sample
        return (str(Path.home() / "Footage" / "A001_C003.MOV"),
                MediaInfo(kind="video", width=3840, height=2160, fps=23.976), "video")

    def _update_example(self) -> None:
        path, info, kind = self._sample_tuple()
        p = Path(path)
        try:
            out_dir = naming.output_dir(path, self.s, kind)
            name = naming.planned_name(path, info, self.s, kind, 1)
        except Exception:  # noqa: BLE001
            out_dir, name = p.parent, "?"
        self.ex_from.setText(f"{p.parent.name}/{p.name}")
        note = ""
        try:
            target, _ = naming.resolve_output(path, out_dir / name, self.s.collision, set())
            if target is None:
                note = "A file with this name is already there, so this one would be skipped."
            elif target.name != name:
                same = naming.reserve_key(out_dir / name) == naming.reserve_key(Path(path))
                note = ("Same name as the original, so a number is added to keep the original safe."
                        if same else "That name is taken, so a number is added.")
                name = target.name
        except Exception:  # noqa: BLE001
            pass
        self.ex_to.setText(f"→  {out_dir.name}/{name}")
        self.ex_note.setText(note)
        self.ex_note.setVisible(bool(note))
        for key, _, tpl in NAME_STYLES:
            opt = self.styles.options[key]
            if tpl:
                opt.sub.setText(self._example_for(tpl))
            else:
                opt.sub.setText("Build it from parts like name, format and date")
            opt.sub.setVisible(True)

    def showEvent(self, e):  # noqa: N802
        self._sync()
        super().showEvent(e)
