"""The settings panel on the right."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import naming
from ..presets import (
    AUDIO_FORMATS, COLLISIONS, DEINTERLACE, DESTINATIONS, PHOTO_FORMATS, RESIZE_PHOTO,
    RESIZE_VIDEO, VIDEO_BY_KEY, VIDEO_PRESETS, Settings,
)
from ..probe import MediaInfo
from ..tools import Capabilities
from .widgets import FlowLayout, OptionList, Segmented, hint, section_label


def _combo(choices, current: str) -> QComboBox:
    c = QComboBox()
    for ch in choices:
        c.addItem(ch.label, ch.key)
    i = c.findData(current)
    c.setCurrentIndex(max(0, i))
    c.setCursor(Qt.CursorShape.PointingHandCursor)
    return c


class _FitScroll(QScrollArea):
    """Scroll area whose content always matches the visible width (no clipped edges)."""

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if self.widget():
            self.widget().setFixedWidth(self.viewport().width())


def _page() -> tuple[QScrollArea, QVBoxLayout]:
    area = _FitScroll()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(18, 6, 18, 18)
    lay.setSpacing(8)
    area.setWidget(inner)
    return area, lay


class Sidebar(QFrame):
    changed = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(340)
        self.s = settings
        self._sample: tuple[str, MediaInfo | None, str] | None = None
        self._emit_timer = QTimer(self)
        self._emit_timer.setSingleShot(True)
        self._emit_timer.setInterval(120)
        self._emit_timer.timeout.connect(self.changed.emit)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(10)
        tabs_wrap = QHBoxLayout()
        tabs_wrap.setContentsMargins(18, 0, 18, 0)
        self.tabs = Segmented([("video", "Video"), ("photo", "Photo"), ("audio", "Audio"), ("save", "Save")])
        self.tabs.setObjectName("Seg")
        tabs_wrap.addWidget(self.tabs)
        lay.addLayout(tabs_wrap)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.lock_note = hint("Settings are locked while converting.")
        self.lock_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lock_note.setContentsMargins(18, 0, 18, 12)
        self.lock_note.hide()
        lay.addWidget(self.lock_note)

        self._build_video()
        self._build_photo()
        self._build_audio()
        self._build_save()
        self.tabs.changed.connect(self._tab)
        self.tabs.set_value("video")
        self._tab("video")
        self._sync_video()
        self._sync_photo()
        self._sync_save()

    # ------------------------------------------------------------------ pages
    def _tab(self, key: str) -> None:
        self.stack.setCurrentIndex(["video", "photo", "audio", "save"].index(key))

    def show_tab(self, key: str) -> None:
        self.tabs.set_value(key)
        self._tab(key)

    def _build_video(self) -> None:
        page, lay = _page()
        lay.addWidget(section_label("Make"))
        self.v_list = OptionList([(p.key, p.title, p.subtitle) for p in VIDEO_PRESETS])
        self.v_list.set_value(self.s.video_preset)
        self.v_list.changed.connect(self._video_preset)
        lay.addWidget(self.v_list)

        self.v_variant_label = section_label("Flavor")
        lay.addSpacing(6)
        lay.addWidget(self.v_variant_label)
        self.v_variant_holder = QVBoxLayout()
        self.v_variant_holder.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self.v_variant_holder)
        self.v_variant: Segmented | None = None

        self.v_size_label = section_label("Size")
        lay.addSpacing(6)
        lay.addWidget(self.v_size_label)
        self.v_size = _combo(RESIZE_VIDEO, self.s.video_resize)
        self.v_size.currentIndexChanged.connect(lambda: self._set("video_resize", self.v_size.currentData()))
        lay.addWidget(self.v_size)

        lay.addSpacing(6)
        self.v_deint_label = section_label("Interlaced footage")
        lay.addWidget(self.v_deint_label)
        self.v_deint = _combo(DEINTERLACE, self.s.deinterlace)
        self.v_deint.currentIndexChanged.connect(lambda: self._set("deinterlace", self.v_deint.currentData()))
        lay.addWidget(self.v_deint)
        self.v_deint_hint = hint("Only affects files that are actually interlaced (old camcorders, broadcast, 1080i).")
        lay.addWidget(self.v_deint_hint)

        lay.addSpacing(6)
        self.v_hw = QCheckBox("Use the hardware encoder (much faster)")
        self.v_hw.setChecked(self.s.hardware)
        self.v_hw.toggled.connect(lambda v: self._set("hardware", v))
        lay.addWidget(self.v_hw)
        self.v_hw_hint = hint("Checking this computer…")
        lay.addWidget(self.v_hw_hint)
        self.v_tracks = QCheckBox("Keep every audio track")
        self.v_tracks.setChecked(self.s.keep_all_audio)
        self.v_tracks.toggled.connect(lambda v: self._set("keep_all_audio", v))
        lay.addWidget(self.v_tracks)
        lay.addStretch(1)
        self.stack.addWidget(page)

    def _build_photo(self) -> None:
        page, lay = _page()
        lay.addWidget(section_label("Make"))
        subs = {
            "jpeg": "Smallest, works everywhere",
            "png": "Lossless, keeps transparency",
            "tiff": "Lossless, for print & retouching",
            "webp": "Small, for the web",
            "heic": "iPhone format, very small",
        }
        self.p_list = OptionList([(f.key, f.title, subs.get(f.key, "")) for f in PHOTO_FORMATS])
        self.p_list.set_value(self.s.photo_format)
        self.p_list.changed.connect(lambda k: (self._set("photo_format", k), self._sync_photo()))
        lay.addWidget(self.p_list)

        lay.addSpacing(6)
        self.p_q_label = section_label(f"Quality · {self.s.photo_quality}")
        lay.addWidget(self.p_q_label)
        self.p_q = QSlider(Qt.Orientation.Horizontal)
        self.p_q.setRange(50, 100)
        self.p_q.setValue(self.s.photo_quality)
        self.p_q.valueChanged.connect(self._photo_q)
        lay.addWidget(self.p_q)

        lay.addSpacing(6)
        lay.addWidget(section_label("Size"))
        self.p_size = _combo(RESIZE_PHOTO, self.s.photo_resize)
        self.p_size.currentIndexChanged.connect(lambda: self._set("photo_resize", self.p_size.currentData()))
        lay.addWidget(self.p_size)
        lay.addSpacing(6)
        self.p_meta = QCheckBox("Keep camera info (EXIF) and color profile")
        self.p_meta.setChecked(self.s.photo_keep_metadata)
        self.p_meta.toggled.connect(lambda v: self._set("photo_keep_metadata", v))
        lay.addWidget(self.p_meta)
        lay.addSpacing(4)
        lay.addWidget(hint("Reads JPEG, PNG, TIFF, WebP, HEIC and camera RAW (CR2, CR3, NEF, ARW, DNG, RAF, ORF, RW2…). "
                           "RAW files are developed with the camera's white balance."))
        lay.addStretch(1)
        self.stack.addWidget(page)

    def _build_audio(self) -> None:
        page, lay = _page()
        lay.addWidget(section_label("Make"))
        subs = {
            "wav24": "Edit-ready, lossless", "wav16": "CD quality, lossless",
            "aiff": "Lossless, Mac-friendly", "flac": "Lossless, half the size",
            "mp3": "Plays everywhere", "aac": "Small, great quality",
        }
        self.a_list = OptionList([(f.key, f.title, subs.get(f.key, "")) for f in AUDIO_FORMATS])
        self.a_list.set_value(self.s.audio_format)
        self.a_list.changed.connect(lambda k: self._set("audio_format", k))
        lay.addWidget(self.a_list)
        lay.addSpacing(4)
        lay.addWidget(hint("Used for audio files, and for video when Video → Audio only is picked."))
        lay.addStretch(1)
        self.stack.addWidget(page)

    def _build_save(self) -> None:
        page, lay = _page()
        lay.addWidget(section_label("Save to"))
        self.d_list = OptionList([(c.key, c.label, "") for c in DESTINATIONS])
        self.d_list.set_value(self.s.destination)
        self.d_list.changed.connect(self._destination)
        lay.addWidget(self.d_list)
        self.d_sub = QLineEdit(self.s.subfolder_name)
        self.d_sub.setPlaceholderText("Subfolder name")
        self.d_sub.textChanged.connect(lambda t: self._set("subfolder_name", t.strip() or "Listo"))
        lay.addWidget(self.d_sub)
        row = QHBoxLayout()
        self.d_path = QLabel()
        self.d_path.setObjectName("Muted")
        self.d_path.setWordWrap(True)
        self.d_pick = QPushButton("Choose…")
        self.d_pick.clicked.connect(self._choose_folder)
        row.addWidget(self.d_path, 1)
        row.addWidget(self.d_pick)
        self.d_folder_row = QWidget()
        self.d_folder_row.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.d_folder_row)
        self.d_proxy_hint = hint("Edit proxies saved next to the original go into a Proxy folder there.")
        lay.addWidget(self.d_proxy_hint)

        lay.addSpacing(10)
        lay.addWidget(section_label("File name"))
        self.n_edit = QLineEdit(self.s.naming)
        self.n_edit.setPlaceholderText("{name}")
        self.n_edit.textChanged.connect(lambda t: self._set("naming", t))
        lay.addWidget(self.n_edit)
        tok_wrap = QWidget()
        flow = FlowLayout(tok_wrap, 6)
        for key, desc in naming.TOKENS:
            b = QPushButton("{" + key + "}")
            b.setObjectName("Token")
            b.setToolTip(desc)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._insert_token(k))
            flow.addWidget(b)
        lay.addWidget(tok_wrap)
        presets_row = QHBoxLayout()
        presets_row.setSpacing(6)
        for label, tpl in (("Original", "{name}"), ("+ format", "{name}_{preset}"),
                           ("Dated", "{date}_{name}"), ("Numbered", "{folder}_{n}")):
            b = QPushButton(label)
            b.setObjectName("Ghost")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, t=tpl: self.n_edit.setText(t))
            presets_row.addWidget(b)
        presets_row.addStretch(1)
        lay.addLayout(presets_row)
        self.n_preview = QLabel()
        self.n_preview.setObjectName("Preview")
        self.n_preview.setWordWrap(True)
        self.n_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.n_preview)

        lay.addSpacing(10)
        lay.addWidget(section_label("If a file with that name exists"))
        self.c_seg = Segmented([(c.key, c.label) for c in COLLISIONS])
        self.c_seg.set_value(self.s.collision)
        self.c_seg.changed.connect(lambda k: self._set("collision", k))
        lay.addWidget(self.c_seg)
        lay.addWidget(hint("Your original files are never overwritten, whatever you pick here."))
        lay.addSpacing(10)
        self.k_dates = QCheckBox("Keep the original file dates")
        self.k_dates.setChecked(self.s.keep_dates)
        self.k_dates.toggled.connect(lambda v: self._set("keep_dates", v))
        lay.addWidget(self.k_dates)
        lay.addStretch(1)
        self.stack.addWidget(page)

    # ------------------------------------------------------------------ behavior
    def _set(self, attr: str, value) -> None:
        setattr(self.s, attr, value)
        if attr == "naming" or attr.startswith(("destination", "subfolder", "video", "photo", "audio")):
            self._update_preview()
        self._emit_timer.start()

    def _video_preset(self, key: str) -> None:
        self._set("video_preset", key)
        self._sync_video()
        self._sync_save()

    def _sync_video(self) -> None:
        p = VIDEO_BY_KEY[self.s.video_preset]
        if self.v_variant is not None:
            self.v_variant.setParent(None)
            self.v_variant.deleteLater()
            self.v_variant = None
        if p.variants:
            seg = Segmented([(c.key, c.label) for c in p.variants])
            seg.set_value(self.s.variant_for(p.key))

            def pick(k: str, key=p.key) -> None:
                self.s.video_variant[key] = k
                self._update_preview()
                self._emit_timer.start()

            seg.changed.connect(pick)
            self.v_variant_holder.addWidget(seg)
            self.v_variant = seg
            self.v_variant_label.setText(p.variant_label.upper())
        self.v_variant_label.setVisible(bool(p.variants))
        resizable = p.key not in ("rewrap", "proxy", "gif", "audio")
        self.v_size_label.setVisible(resizable)
        self.v_size.setVisible(resizable)
        deint = p.key not in ("rewrap", "audio")
        for w in (self.v_deint_label, self.v_deint, self.v_deint_hint):
            w.setVisible(deint)
        self.v_hw.setVisible(bool(p.hw_codec))
        self.v_hw_hint.setVisible(bool(p.hw_codec))
        self.v_tracks.setVisible(p.edit_format)

    def _sync_photo(self) -> None:
        q = next(f for f in PHOTO_FORMATS if f.key == self.s.photo_format).has_quality
        self.p_q_label.setVisible(q)
        self.p_q.setVisible(q)

    def _photo_q(self, v: int) -> None:
        self.p_q_label.setText(f"QUALITY · {v}")
        self._set("photo_quality", v)

    def _destination(self, key: str) -> None:
        if key == "folder" and not self.s.dest_folder:
            if not self._choose_folder():
                self.d_list.set_value(self.s.destination)
                return
        self._set("destination", key)
        self._sync_save()

    def _choose_folder(self) -> bool:
        start = self.s.dest_folder or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Save converted files to…", start)
        if d:
            self.s.dest_folder = d
            self._set("destination", "folder")
            self.d_list.set_value("folder")
            self._sync_save()
            return True
        return False

    def _sync_save(self) -> None:
        dest = self.s.destination
        self.d_sub.setVisible(dest == "subfolder")
        self.d_folder_row.setVisible(dest == "folder")
        self.d_path.setText(self.s.dest_folder or "No folder chosen")
        self.d_proxy_hint.setVisible(self.s.video_preset == "proxy" and dest == "source")
        self._update_preview()

    def _insert_token(self, key: str) -> None:
        self.n_edit.insert("{" + key + "}")
        self.n_edit.setFocus()

    def set_sample(self, path: str | None, info: MediaInfo | None, kind: str) -> None:
        self._sample = (path, info, kind) if path else None
        self._update_preview()

    def _update_preview(self) -> None:
        if not hasattr(self, "n_preview"):
            return
        if self._sample:
            path, info, kind = self._sample
        else:
            path, info, kind = str(Path.home() / "A001_C003.MOV"), MediaInfo(
                kind="video", width=3840, height=2160, fps=23.976), "video"
        try:
            name = naming.planned_name(path, info, self.s, kind, 1)
        except Exception:  # noqa: BLE001
            name = "?"
        self.n_preview.setText(f"{Path(path).name}\n→ {name}")

    def apply_capabilities(self, caps: Capabilities) -> None:
        from ..photo import is_heic_encodable
        from ..video import preset_available

        for p in VIDEO_PRESETS:
            ok = preset_available(p.key, caps) if p.needs else caps.ok
            self.v_list.options[p.key].set_available(ok, "This copy of ffmpeg can't make this format.")
        heic = is_heic_encodable()
        self.p_list.options["heic"].set_available(heic, "HEIC support isn't installed.")
        if "libmp3lame" not in caps.encoders:
            self.a_list.options["mp3"].set_available(False, "This copy of ffmpeg can't make MP3.")

    def apply_hardware(self, hw: dict) -> None:
        if hw:
            names = ", ".join(sorted({("Apple VideoToolbox" if "videotoolbox" in e else "NVIDIA NVENC") for e in hw.values()}))
            self.v_hw.setEnabled(True)
            self.v_hw_hint.setText(f"Found: {names}. Turn off for the smallest files at the same quality.")
        else:
            self.v_hw.setEnabled(False)
            self.v_hw_hint.setText("No hardware encoder found on this computer — using the regular encoder.")

    def set_locked(self, locked: bool) -> None:
        self.stack.setEnabled(not locked)
        self.lock_note.setVisible(locked)
