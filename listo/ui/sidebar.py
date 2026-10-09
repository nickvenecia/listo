"""The settings panel on the right: recipe picker + Video / Photo / Audio formats."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSlider, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from ..presets import (
    AUDIO_FORMATS, BUILTIN_RECIPES, DEINTERLACE, PHOTO_FORMATS, RESIZE_PHOTO, RESIZE_VIDEO,
    VIDEO_BY_KEY, VIDEO_GROUPS, VIDEO_PRESETS, Settings,
)
from ..tools import Capabilities
from . import theme
from .job_card import ElidedLabel
from .widgets import OptionList, Segmented, hint, section_label

SIDEBAR_W = 300


def _combo(choices, current: str) -> QComboBox:
    c = QComboBox()
    for ch in choices:
        c.addItem(ch.label, ch.key)
    c.setCurrentIndex(max(0, c.findData(current)))
    c.setCursor(Qt.CursorShape.PointingHandCursor)
    return c


def _set_combo(c: QComboBox, key: str) -> None:
    c.blockSignals(True)
    c.setCurrentIndex(max(0, c.findData(key)))
    c.blockSignals(False)


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
    lay.setContentsMargins(14, 4, 14, 16)
    lay.setSpacing(6)
    area.setWidget(inner)
    return area, lay


class Sidebar(QFrame):
    changed = Signal()
    recipe_applied = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(SIDEBAR_W)
        self.s = settings
        self.qs = QSettings("Listo", "Listo")
        self._loading = False
        self._emit_timer = QTimer(self)
        self._emit_timer.setSingleShot(True)
        self._emit_timer.setInterval(120)
        self._emit_timer.timeout.connect(self._emit_changed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(8)

        # ---- recipe
        rwrap = QVBoxLayout()
        rwrap.setContentsMargins(14, 0, 14, 0)
        rwrap.setSpacing(4)
        rwrap.addWidget(section_label("Recipe"))
        rrow = QHBoxLayout()
        rrow.setSpacing(4)
        self.recipe = QComboBox()
        self.recipe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.recipe.setToolTip("Saved combinations of format, folder and naming")
        self.recipe.activated.connect(self._recipe_picked)
        self.recipe_more = QToolButton()
        self.recipe_more.setObjectName("IconBtn")
        self.recipe_more.setText("•••")
        self.recipe_more.setToolTip("Save or delete recipes")
        self.recipe_more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.recipe_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.recipe_menu = QMenu(self)
        self.recipe_menu.aboutToShow.connect(self._build_recipe_menu)
        self.recipe_more.setMenu(self.recipe_menu)
        self.recipe_more.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        rrow.addWidget(self.recipe, 1)
        rrow.addWidget(self.recipe_more)
        rwrap.addLayout(rrow)
        lay.addLayout(rwrap)

        tabs_wrap = QHBoxLayout()
        tabs_wrap.setContentsMargins(14, 4, 14, 0)
        self.tabs = Segmented([("video", "Video"), ("photo", "Photo"), ("audio", "Audio")])
        tabs_wrap.addWidget(self.tabs)
        lay.addLayout(tabs_wrap)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        self._build_video()
        self._build_photo()
        self._build_audio()
        self.tabs.changed.connect(self._tab)
        self.tabs.set_value("video")
        self._tab("video")
        self._sync_video()
        self._sync_photo()
        self._refresh_recipes()

    # ------------------------------------------------------------------ pages
    def _tab(self, key: str) -> None:
        self.stack.setCurrentIndex(["video", "photo", "audio"].index(key))

    def show_tab(self, key: str) -> None:
        self.tabs.set_value(key)
        self._tab(key)

    def _build_video(self) -> None:
        page, lay = _page()
        items: list[tuple[str, str, str]] = []
        for gkey, glabel in VIDEO_GROUPS:
            items.append(("#" + gkey, glabel.upper(), ""))
            items += [(p.key, p.title, p.subtitle) for p in VIDEO_PRESETS if p.group == gkey]
        self.v_list = OptionList(items)
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

        # ---- look: LUT + burn-ins
        self.look_box = QWidget()
        lb = QVBoxLayout(self.look_box)
        lb.setContentsMargins(0, 6, 0, 0)
        lb.setSpacing(6)
        lb.addWidget(section_label("Look"))
        lrow = QHBoxLayout()
        lrow.setSpacing(4)
        self.lut_label = ElidedLabel("", Qt.TextElideMode.ElideMiddle)
        self.lut_label.setObjectName("Muted")
        self.lut_pick = QPushButton("Add LUT…")
        self.lut_pick.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lut_pick.clicked.connect(self._choose_lut)
        self.lut_clear = QToolButton()
        self.lut_clear.setObjectName("IconBtn")
        self.lut_clear.setIcon(theme.icon("x", theme.MUTED, 14))
        self.lut_clear.setIconSize(QSize(14, 14))
        self.lut_clear.setToolTip("Remove the LUT")
        self.lut_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lut_clear.clicked.connect(lambda: (self._set("lut_path", ""), self._sync_lut()))
        lrow.addWidget(self.lut_label, 1)
        lrow.addWidget(self.lut_pick)
        lrow.addWidget(self.lut_clear)
        lb.addLayout(lrow)
        self.burn_tc = QCheckBox("Burn in timecode")
        self.burn_tc.setChecked(self.s.burn_timecode)
        self.burn_tc.toggled.connect(lambda v: self._set("burn_timecode", v))
        self.burn_name = QCheckBox("Burn in file name")
        self.burn_name.setChecked(self.s.burn_filename)
        self.burn_name.toggled.connect(lambda v: self._set("burn_filename", v))
        lb.addWidget(self.burn_tc)
        lb.addWidget(self.burn_name)
        lb.addWidget(hint("For review copies. A .cube LUT is applied to every video in the batch."))
        lay.addWidget(self.look_box)

        # ---- speed
        lay.addSpacing(6)
        lay.addWidget(section_label("Speed"))
        self.v_hw = QCheckBox("Use the hardware encoder")
        self.v_hw.setChecked(self.s.hardware)
        self.v_hw.toggled.connect(lambda v: self._set("hardware", v))
        lay.addWidget(self.v_hw)
        self.v_hw_hint = hint("Checking this computer…")
        lay.addWidget(self.v_hw_hint)
        self.v_par = QCheckBox("Convert two files at once")
        self.v_par.setChecked(self.s.parallel)
        self.v_par.toggled.connect(lambda v: self._set("parallel", v))
        lay.addWidget(self.v_par)
        lay.addWidget(hint("Fastest with the hardware encoder or lots of small files."))
        lay.addSpacing(6)
        self.v_tracks = QCheckBox("Keep every audio track")
        self.v_tracks.setChecked(self.s.keep_all_audio)
        self.v_tracks.toggled.connect(lambda v: self._set("keep_all_audio", v))
        lay.addWidget(self.v_tracks)
        lay.addStretch(1)
        self.stack.addWidget(page)
        self._sync_lut()

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

    # ------------------------------------------------------------------ behavior
    def _set(self, attr: str, value) -> None:
        if self._loading:
            return
        setattr(self.s, attr, value)
        self._emit_timer.start()

    def _emit_changed(self) -> None:
        self._match_recipe()
        self.changed.emit()

    def notify_external_change(self) -> None:
        """Settings changed elsewhere (e.g. Save options) — keep the recipe picker honest."""
        self._match_recipe()

    def _video_preset(self, key: str) -> None:
        self._set("video_preset", key)
        self._sync_video()

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
        self.look_box.setVisible(p.key not in ("rewrap", "audio"))
        self.v_tracks.setVisible(p.edit_format)

    def _sync_photo(self) -> None:
        q = next(f for f in PHOTO_FORMATS if f.key == self.s.photo_format).has_quality
        self.p_q_label.setVisible(q)
        self.p_q.setVisible(q)

    def _photo_q(self, v: int) -> None:
        self.p_q_label.setText(f"QUALITY · {v}")
        self._set("photo_quality", v)

    def _choose_lut(self) -> None:
        start = str(Path(self.s.lut_path).parent) if self.s.lut_path else str(Path.home())
        f, _ = QFileDialog.getOpenFileName(
            self, "Choose a LUT", start, "LUT files (*.cube *.3dl *.dat *.m3d *.csp);;All files (*)")
        if f:
            self._set("lut_path", f)
            self._sync_lut()

    def _sync_lut(self) -> None:
        has = bool(self.s.lut_path)
        self.lut_label.setText(Path(self.s.lut_path).name if has else "No LUT")
        self.lut_label.setToolTip(self.s.lut_path)
        self.lut_pick.setText("Change…" if has else "Add LUT…")
        self.lut_clear.setVisible(has)

    # ------------------------------------------------------------------ recipes
    def _user_recipes(self) -> list[dict]:
        try:
            data = json.loads(self.qs.value("recipes", "[]") or "[]")
            return [r for r in data if isinstance(r, dict) and r.get("name") and isinstance(r.get("values"), dict)]
        except (ValueError, TypeError):
            return []

    def _all_recipes(self) -> list[tuple[str, dict, bool]]:
        out = [(n, v, False) for n, v in BUILTIN_RECIPES]
        out += [(r["name"], r["values"], True) for r in self._user_recipes()]
        return out

    def _refresh_recipes(self) -> None:
        self.recipe.blockSignals(True)
        self.recipe.clear()
        self.recipe.addItem("Custom settings", None)
        for name, _, user in self._all_recipes():
            self.recipe.addItem(("★ " if user else "") + name, name)
        self.recipe.blockSignals(False)
        self._match_recipe()

    def _match_recipe(self) -> None:
        current = self.recipe.currentData()
        recipes = self._all_recipes()
        # keep the chosen one if it still matches, otherwise find any that does
        names = ([current] if current else []) + [n for n, _, _ in recipes if n != current]
        found = None
        for name in names:
            vals = next((v for n, v, _ in recipes if n == name), None)
            if vals is not None and self.s.matches(vals):
                found = name
                break
        self.recipe.blockSignals(True)
        self.recipe.setCurrentIndex(max(0, self.recipe.findData(found)) if found else 0)
        self.recipe.blockSignals(False)

    def _recipe_picked(self, index: int) -> None:
        name = self.recipe.itemData(index)
        if not name:
            return
        vals = next((v for n, v, _ in self._all_recipes() if n == name), None)
        if vals is None:
            return
        self.s.apply(vals)
        if self.s.destination == "folder" and not self.s.dest_folder:
            self.s.destination = "source"
        self.reload()
        self.recipe_applied.emit()
        self.changed.emit()

    def _build_recipe_menu(self) -> None:
        m = self.recipe_menu
        m.clear()
        m.addAction("Save current settings as a recipe…", self._save_recipe)
        name = self.recipe.currentData()
        if name in {r["name"] for r in self._user_recipes()}:
            m.addAction(f"Update “{name}” with current settings", lambda: self._store_recipe(name))
            m.addAction(f"Delete “{name}”", lambda: self._delete_recipe(name))

    def _save_recipe(self) -> None:
        name, ok = QInputDialog.getText(self, "Save recipe", "Name this recipe:")
        name = name.strip()
        if not ok or not name:
            return
        if name in {n for n, _ in BUILTIN_RECIPES}:
            QMessageBox.information(self, "Save recipe", "That name is taken by a built-in recipe — try another.")
            return
        self._store_recipe(name)

    def _store_recipe(self, name: str) -> None:
        recipes = [r for r in self._user_recipes() if r["name"] != name]
        values = self.s.to_dict()
        values["video_variant"] = {p.key: self.s.variant_for(p.key) for p in VIDEO_PRESETS if p.variants}
        recipes.append({"name": name, "values": values})
        self.qs.setValue("recipes", json.dumps(recipes))
        self._refresh_recipes()
        self.recipe.setCurrentIndex(max(0, self.recipe.findData(name)))

    def _delete_recipe(self, name: str) -> None:
        recipes = [r for r in self._user_recipes() if r["name"] != name]
        self.qs.setValue("recipes", json.dumps(recipes))
        self._refresh_recipes()

    def reload(self) -> None:
        """Refresh every control from the settings (after a recipe is applied)."""
        self._loading = True
        try:
            self.v_list.set_value(self.s.video_preset)
            _set_combo(self.v_size, self.s.video_resize)
            _set_combo(self.v_deint, self.s.deinterlace)
            for box, val in ((self.v_hw, self.s.hardware), (self.v_tracks, self.s.keep_all_audio),
                             (self.v_par, self.s.parallel), (self.burn_tc, self.s.burn_timecode),
                             (self.burn_name, self.s.burn_filename), (self.p_meta, self.s.photo_keep_metadata)):
                box.blockSignals(True)
                box.setChecked(val)
                box.blockSignals(False)
            self.p_list.set_value(self.s.photo_format)
            self.p_q.blockSignals(True)
            self.p_q.setValue(self.s.photo_quality)
            self.p_q.blockSignals(False)
            self.p_q_label.setText(f"QUALITY · {self.s.photo_quality}")
            _set_combo(self.p_size, self.s.photo_resize)
            self.a_list.set_value(self.s.audio_format)
            self._sync_video()
            self._sync_photo()
            self._sync_lut()
        finally:
            self._loading = False
        self._match_recipe()

    # ------------------------------------------------------------------ capabilities
    def apply_capabilities(self, caps: Capabilities) -> None:
        from ..photo import is_heic_encodable
        from ..video import preset_available

        for p in VIDEO_PRESETS:
            ok = preset_available(p.key, caps) if p.needs else caps.ok
            self.v_list.options[p.key].set_available(ok, "This copy of ffmpeg can't make this format.")
        self.p_list.options["heic"].set_available(is_heic_encodable(), "HEIC support isn't installed.")
        if "libmp3lame" not in caps.encoders:
            self.a_list.options["mp3"].set_available(False, "This copy of ffmpeg can't make MP3.")
        if not caps.has_filter("lut3d"):
            self.lut_pick.setEnabled(False)
        if not caps.has_filter("drawtext"):
            self.burn_tc.setEnabled(False)
            self.burn_name.setEnabled(False)

    def apply_hardware(self, hw: dict) -> None:
        if hw:
            names = ", ".join(sorted({("Apple VideoToolbox" if "videotoolbox" in e else "NVIDIA NVENC") for e in hw.values()}))
            self.v_hw.setEnabled(True)
            self.v_hw_hint.setText(f"Found {names} — much faster for H.264 and HEVC.")
        else:
            self.v_hw.setEnabled(False)
            self.v_hw_hint.setText("No hardware encoder on this computer — using the regular one.")
