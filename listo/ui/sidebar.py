"""The settings panel on the right: recipe picker + Video / Photo / Audio settings."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QMessageBox,
    QScrollArea, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

from ..presets import (
    AUDIO_FORMATS, BUILTIN_RECIPES, DEINTERLACE, PHOTO_FORMATS, RESIZE_PHOTO, RESIZE_VIDEO,
    VIDEO_BY_KEY, VIDEO_PRESETS, Settings,
)
from ..tools import Capabilities
from .widgets import Segmented, section_label

SIDEBAR_W = 310
ACTION_SAVE, ACTION_UPDATE, ACTION_DELETE = "__save__", "__update__", "__delete__"
LUT_FILE, LUT_FOLDER = "__lut_file__", "__lut_folder__"
LUT_EXTS = {".cube", ".3dl", ".dat", ".m3d", ".csp"}

PHOTO_TIPS = {
    "jpeg": "Smallest, works everywhere", "png": "Lossless, keeps transparency",
    "tiff": "Lossless, for print & retouching", "webp": "Small, for the web", "heic": "iPhone format, very small",
}
AUDIO_TIPS = {
    "wav24": "Edit-ready, lossless", "wav16": "CD quality, lossless", "aiff": "Lossless, Mac-friendly",
    "flac": "Lossless, half the size", "mp3": "Plays everywhere", "aac": "Small, great quality",
}


def _combo(items: list[tuple[str, str, str]], current: str) -> QComboBox:
    """items: (key, label, tooltip)"""
    c = QComboBox()
    for key, label, tip in items:
        c.addItem(label, key)
        if tip:
            c.setItemData(c.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
    c.setCurrentIndex(max(0, c.findData(current)))
    c.setCursor(Qt.CursorShape.PointingHandCursor)
    return c


def _set_combo(c: QComboBox, key: str) -> None:
    c.blockSignals(True)
    c.setCurrentIndex(max(0, c.findData(key)))
    c.blockSignals(False)


def _disable_item(c: QComboBox, key: str, why: str) -> None:
    i = c.findData(key)
    item = c.model().item(i) if i >= 0 and hasattr(c.model(), "item") else None
    if item is not None:
        item.setEnabled(False)
        item.setToolTip(why)


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
    lay.setContentsMargins(14, 6, 14, 16)
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
        self._current_recipe: str | None = None
        self._emit_timer = QTimer(self)
        self._emit_timer.setSingleShot(True)
        self._emit_timer.setInterval(120)
        self._emit_timer.timeout.connect(self._emit_changed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(8)

        rwrap = QVBoxLayout()
        rwrap.setContentsMargins(14, 0, 14, 0)
        rwrap.setSpacing(4)
        rwrap.addWidget(section_label("Recipe"))
        self.recipe = QComboBox()
        self.recipe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.recipe.setToolTip("Recipes remember format, folder and naming so you can reuse them in one click")
        self.recipe.activated.connect(self._recipe_picked)
        rwrap.addWidget(self.recipe)
        lay.addLayout(rwrap)

        tabs_wrap = QHBoxLayout()
        tabs_wrap.setContentsMargins(14, 6, 14, 0)
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
        self._match_recipe()

    # ------------------------------------------------------------------ pages
    def _tab(self, key: str) -> None:
        self.stack.setCurrentIndex(["video", "photo", "audio"].index(key))

    def show_tab(self, key: str) -> None:
        self.tabs.set_value(key)
        self._tab(key)

    def _build_video(self) -> None:
        page, lay = _page()
        lay.addWidget(section_label("Format"))
        self.v_fmt = _combo(
            [(p.key, f"{p.title}   ·   {'.' + p.ext if p.ext else 'audio file'}", p.subtitle.split(" · ")[0])
             for p in VIDEO_PRESETS],
            self.s.video_preset,
        )
        self.v_fmt.currentIndexChanged.connect(lambda: self._video_preset(self.v_fmt.currentData()))
        lay.addWidget(self.v_fmt)

        lay.addSpacing(6)
        self.v_variant_label = section_label("Flavor")
        lay.addWidget(self.v_variant_label)
        self.v_variant = QComboBox()
        self.v_variant.setCursor(Qt.CursorShape.PointingHandCursor)
        self.v_variant.currentIndexChanged.connect(self._variant_picked)
        lay.addWidget(self.v_variant)

        self.v_size_label = section_label("Size")
        lay.addSpacing(6)
        lay.addWidget(self.v_size_label)
        self.v_size = _combo([(c.key, c.label, "") for c in RESIZE_VIDEO], self.s.video_resize)
        self.v_size.currentIndexChanged.connect(lambda: self._set("video_resize", self.v_size.currentData()))
        lay.addWidget(self.v_size)

        lay.addSpacing(6)
        self.v_deint_label = section_label("Interlaced footage")
        lay.addWidget(self.v_deint_label)
        self.v_deint = _combo([(c.key, c.label, "") for c in DEINTERLACE], self.s.deinterlace)
        self.v_deint.setToolTip("Only affects footage that's actually interlaced (old camcorders, broadcast, 1080i)")
        self.v_deint.currentIndexChanged.connect(lambda: self._set("deinterlace", self.v_deint.currentData()))
        lay.addWidget(self.v_deint)

        # ---- look: LUT + burn-ins
        self.look_box = QWidget()
        lb = QVBoxLayout(self.look_box)
        lb.setContentsMargins(0, 6, 0, 0)
        lb.setSpacing(6)
        lb.addWidget(section_label("LUT"))
        self.lut = QComboBox()
        self.lut.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lut.setToolTip("Apply a LUT to every video — handy for review copies")
        self.lut.activated.connect(self._lut_picked)
        lb.addWidget(self.lut)
        lb.addSpacing(4)
        lb.addWidget(section_label("Burn in"))
        self.burn_tc = QCheckBox("Timecode")
        self.burn_tc.setChecked(self.s.burn_timecode)
        self.burn_tc.toggled.connect(lambda v: self._set("burn_timecode", v))
        self.burn_name = QCheckBox("File name")
        self.burn_name.setChecked(self.s.burn_filename)
        self.burn_name.toggled.connect(lambda v: self._set("burn_filename", v))
        brow = QHBoxLayout()
        brow.setSpacing(18)
        brow.addWidget(self.burn_tc)
        brow.addWidget(self.burn_name)
        brow.addStretch(1)
        lb.addLayout(brow)
        lay.addWidget(self.look_box)

        # ---- speed
        lay.addSpacing(6)
        lay.addWidget(section_label("Speed"))
        self.v_hw = QCheckBox("Hardware encoding (faster)")
        self.v_hw.setChecked(self.s.hardware)
        self.v_hw.toggled.connect(lambda v: self._set("hardware", v))
        lay.addWidget(self.v_hw)
        self.v_par = QCheckBox("Convert two files at once")
        self.v_par.setToolTip("Fastest with the hardware encoder or lots of small files")
        self.v_par.setChecked(self.s.parallel)
        self.v_par.toggled.connect(lambda v: self._set("parallel", v))
        lay.addWidget(self.v_par)
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
        lay.addWidget(section_label("Format"))
        self.p_fmt = _combo([(f.key, f"{f.title.split(' ·')[0]}   ·   .{f.ext}", PHOTO_TIPS.get(f.key, ""))
                             for f in PHOTO_FORMATS], self.s.photo_format)
        self.p_fmt.currentIndexChanged.connect(
            lambda: (self._set("photo_format", self.p_fmt.currentData()), self._sync_photo()))
        lay.addWidget(self.p_fmt)

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
        self.p_size = _combo([(c.key, c.label, "") for c in RESIZE_PHOTO], self.s.photo_resize)
        self.p_size.currentIndexChanged.connect(lambda: self._set("photo_resize", self.p_size.currentData()))
        lay.addWidget(self.p_size)
        lay.addSpacing(6)
        self.p_meta = QCheckBox("Keep camera info and color profile")
        self.p_meta.setChecked(self.s.photo_keep_metadata)
        self.p_meta.toggled.connect(lambda v: self._set("photo_keep_metadata", v))
        lay.addWidget(self.p_meta)
        lay.addStretch(1)
        self.stack.addWidget(page)

    def _build_audio(self) -> None:
        page, lay = _page()
        lay.addWidget(section_label("Format"))
        self.a_fmt = _combo([(f.key, f"{f.title}   ·   .{f.ext}", AUDIO_TIPS.get(f.key, ""))
                             for f in AUDIO_FORMATS], self.s.audio_format)
        self.a_fmt.currentIndexChanged.connect(lambda: self._set("audio_format", self.a_fmt.currentData()))
        lay.addWidget(self.a_fmt)
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
        """Settings changed elsewhere (e.g. Export options) — keep the recipe picker honest."""
        self._match_recipe()

    def _video_preset(self, key: str) -> None:
        self._set("video_preset", key)
        self._sync_video()

    def _variant_picked(self) -> None:
        if self._loading or self.v_variant.signalsBlocked():
            return
        key = self.v_variant.currentData()
        if key:
            self.s.video_variant[self.s.video_preset] = key
            self._emit_timer.start()

    def _sync_video(self) -> None:
        p = VIDEO_BY_KEY[self.s.video_preset]
        self.v_variant.blockSignals(True)
        self.v_variant.clear()
        for c in p.variants:
            self.v_variant.addItem(c.label, c.key)
        self.v_variant.setCurrentIndex(max(0, self.v_variant.findData(self.s.variant_for(p.key))))
        self.v_variant.blockSignals(False)
        self.v_variant_label.setText(p.variant_label.upper() if p.variants else "")
        for w in (self.v_variant_label, self.v_variant):
            w.setVisible(bool(p.variants))
        resizable = p.key not in ("rewrap", "proxy", "gif", "audio")
        self.v_size_label.setVisible(resizable)
        self.v_size.setVisible(resizable)
        deint = p.key not in ("rewrap", "audio")
        for w in (self.v_deint_label, self.v_deint):
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

    # ---- LUTs: a dropdown of your LUT folder + recently used LUTs
    def _recent_luts(self) -> list[str]:
        try:
            data = json.loads(self.qs.value("recent_luts", "[]") or "[]")
        except (ValueError, TypeError):
            data = []
        return [p for p in data if isinstance(p, str) and Path(p).is_file()]

    def _folder_luts(self) -> list[str]:
        folder = str(self.qs.value("lut_folder", "") or "")
        if not folder or not Path(folder).is_dir():
            return []
        try:
            return sorted((str(p) for p in Path(folder).rglob("*") if p.suffix.lower() in LUT_EXTS and p.is_file()),
                          key=lambda p: Path(p).name.lower())[:300]
        except OSError:
            return []

    def _remember_lut(self, path: str) -> None:
        recent = [path] + [p for p in self._recent_luts() if p != path]
        self.qs.setValue("recent_luts", json.dumps(recent[:10]))

    def _sync_lut(self) -> None:
        c = self.lut
        c.blockSignals(True)
        c.clear()
        c.addItem("No LUT", "")
        folder = self._folder_luts()
        recent = [p for p in self._recent_luts() if p not in folder]
        current = self.s.lut_path
        if current and current not in folder and current not in recent:
            recent.insert(0, current)
        for group in (recent, folder):
            if group:
                c.insertSeparator(c.count())
                for p in group:
                    c.addItem(Path(p).stem, p)
                    c.setItemData(c.count() - 1, p, Qt.ItemDataRole.ToolTipRole)
        c.insertSeparator(c.count())
        c.addItem("Choose a LUT file…", LUT_FILE)
        lut_folder = str(self.qs.value("lut_folder", "") or "")
        c.addItem(f"Change LUT folder ({Path(lut_folder).name})…" if lut_folder else "Use a LUT folder…", LUT_FOLDER)
        c.setCurrentIndex(max(0, c.findData(current)))
        c.setToolTip(current or "Apply a LUT to every video — handy for review copies")
        c.blockSignals(False)

    def _lut_picked(self, index: int) -> None:
        data = self.lut.itemData(index)
        if data == LUT_FILE:
            start = str(Path(self.s.lut_path).parent) if self.s.lut_path else str(Path.home())
            f, _ = QFileDialog.getOpenFileName(
                self, "Choose a LUT", start, "LUT files (*.cube *.3dl *.dat *.m3d *.csp);;All files (*)")
            if f:
                self._remember_lut(f)
                self._set("lut_path", f)
        elif data == LUT_FOLDER:
            start = str(self.qs.value("lut_folder", "") or Path.home())
            d = QFileDialog.getExistingDirectory(self, "Choose your LUT folder", start)
            if d:
                self.qs.setValue("lut_folder", d)
        elif data is not None:
            if data:
                self._remember_lut(data)
            self._set("lut_path", data)
        self._sync_lut()

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

    def _match_recipe(self) -> None:
        """Show which recipe the current settings match (if any) and rebuild the picker."""
        recipes = self._all_recipes()
        names = ([self._current_recipe] if self._current_recipe else []) + \
            [n for n, _, _ in recipes if n != self._current_recipe]
        found = None
        for name in names:
            vals = next((v for n, v, _ in recipes if n == name), None)
            if vals is not None and self.s.matches(vals):
                found = name
                break
        self._current_recipe = found
        user = {r["name"] for r in self._user_recipes()}

        c = self.recipe
        c.blockSignals(True)
        c.clear()
        c.addItem("No recipe" if not recipes else "Custom settings", None)
        for name, _, _ in recipes:
            c.addItem(name, name)
        c.insertSeparator(c.count())
        c.addItem("Save current settings as a recipe…", ACTION_SAVE)
        if found in user:
            c.addItem(f"Update “{found}” with current settings", ACTION_UPDATE)
            c.addItem(f"Delete “{found}”", ACTION_DELETE)
        c.setCurrentIndex(max(0, c.findData(found)) if found else 0)
        c.blockSignals(False)

    def _recipe_picked(self, index: int) -> None:
        data = self.recipe.itemData(index)
        current = self._current_recipe
        if data == ACTION_SAVE:
            self._save_recipe()
        elif data == ACTION_UPDATE and current:
            self._store_recipe(current)
        elif data == ACTION_DELETE and current:
            if QMessageBox.question(self, "Delete recipe", f"Delete the recipe “{current}”?") == \
                    QMessageBox.StandardButton.Yes:
                self._delete_recipe(current)
        elif data:
            vals = next((v for n, v, _ in self._all_recipes() if n == data), None)
            if vals is not None:
                self.s.apply(vals)
                if self.s.destination == "folder" and not self.s.dest_folder:
                    self.s.destination = "source"
                self._current_recipe = data
                self.reload()
                self.recipe_applied.emit()
                self.changed.emit()
                return
        self._match_recipe()  # put the picker back on the right entry

    def _save_recipe(self) -> None:
        name, ok = QInputDialog.getText(self, "Save recipe", "Name this recipe:")
        name = name.strip()
        if not ok or not name:
            return
        if name in (ACTION_SAVE, ACTION_UPDATE, ACTION_DELETE):
            return
        self._store_recipe(name)

    def _store_recipe(self, name: str) -> None:
        recipes = [r for r in self._user_recipes() if r["name"] != name]
        values = self.s.to_dict()
        values["video_variant"] = {p.key: self.s.variant_for(p.key) for p in VIDEO_PRESETS if p.variants}
        recipes.append({"name": name, "values": values})
        self.qs.setValue("recipes", json.dumps(recipes))
        self._current_recipe = name
        self._match_recipe()

    def _delete_recipe(self, name: str) -> None:
        recipes = [r for r in self._user_recipes() if r["name"] != name]
        self.qs.setValue("recipes", json.dumps(recipes))
        self._current_recipe = None
        self._match_recipe()

    def reload(self) -> None:
        """Refresh every control from the settings (after a recipe is applied)."""
        self._loading = True
        try:
            for combo, key in ((self.v_fmt, self.s.video_preset), (self.v_size, self.s.video_resize),
                               (self.v_deint, self.s.deinterlace), (self.p_fmt, self.s.photo_format),
                               (self.p_size, self.s.photo_resize), (self.a_fmt, self.s.audio_format)):
                _set_combo(combo, key)
            for box, val in ((self.v_hw, self.s.hardware), (self.v_tracks, self.s.keep_all_audio),
                             (self.v_par, self.s.parallel), (self.burn_tc, self.s.burn_timecode),
                             (self.burn_name, self.s.burn_filename), (self.p_meta, self.s.photo_keep_metadata)):
                box.blockSignals(True)
                box.setChecked(val)
                box.blockSignals(False)
            self.p_q.blockSignals(True)
            self.p_q.setValue(self.s.photo_quality)
            self.p_q.blockSignals(False)
            self.p_q_label.setText(f"QUALITY · {self.s.photo_quality}")
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
            if not ok:
                _disable_item(self.v_fmt, p.key, "This copy of ffmpeg can't make this format.")
        if not is_heic_encodable():
            _disable_item(self.p_fmt, "heic", "HEIC support isn't installed.")
        if "libmp3lame" not in caps.encoders:
            _disable_item(self.a_fmt, "mp3", "This copy of ffmpeg can't make MP3.")
        if not caps.has_filter("lut3d"):
            self.lut.setEnabled(False)
            self.lut.setToolTip("This copy of ffmpeg can't apply LUTs")
        if not caps.has_filter("drawtext"):
            self.burn_tc.setEnabled(False)
            self.burn_name.setEnabled(False)

    def apply_hardware(self, hw: dict) -> None:
        if hw:
            names = ", ".join(sorted({("Apple VideoToolbox" if "videotoolbox" in e else "NVIDIA NVENC") for e in hw.values()}))
            self.v_hw.setEnabled(True)
            self.v_hw.setToolTip(f"Uses {names} — much faster for H.264 and HEVC")
        else:
            self.v_hw.setEnabled(False)
            self.v_hw.setToolTip("No hardware encoder found on this computer")
