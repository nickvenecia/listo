"""The settings panel on the right: recipe picker + Video / Photo / Audio settings."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.presets import (
    AUDIO_FORMATS,
    BUILTIN_RECIPES,
    DEINTERLACE,
    PHOTO_FORMATS,
    RESIZE_PHOTO,
    RESIZE_VIDEO,
    VIDEO_BY_KEY,
    VIDEO_PRESETS,
    Settings,
)
from ..core.tools import Capabilities
from .tokens import SIDEBAR_W, SPACE_1, SPACE_3, SPACE_4
from .widgets import Section, Segmented, combo, disable_item, hbox, set_combo, vbox

ACTION_SAVE, ACTION_UPDATE, ACTION_DELETE = "__save__", "__update__", "__delete__"
LUT_FILE, LUT_FOLDER = "__lut_file__", "__lut_folder__"
LUT_EXTS = {".cube", ".3dl", ".dat", ".m3d", ".csp"}

PHOTO_TIPS = {
    "jpeg": "Smallest, works everywhere",
    "png": "Lossless, keeps transparency",
    "tiff": "Lossless, for print & retouching",
    "webp": "Small, for the web",
    "heic": "iPhone format, very small",
}
AUDIO_TIPS = {
    "wav24": "Edit-ready, lossless",
    "wav16": "CD quality, lossless",
    "aiff": "Lossless, Mac-friendly",
    "flac": "Lossless, half the size",
    "mp3": "Plays everywhere",
    "aac": "Small, great quality",
}


class _FitScroll(QScrollArea):
    """Scroll area whose content always matches the visible width (no clipped edges)."""

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.widget():
            self.widget().setFixedWidth(self.viewport().width())


def _page() -> tuple[QScrollArea, QVBoxLayout]:
    """A scrolling settings page. Sections go in it; the layout spaces them SPACE_3 apart."""
    area = _FitScroll()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    inner = QWidget()
    lay = vbox(inner, (SPACE_4, SPACE_3, SPACE_4, SPACE_4), SPACE_3)
    area.setWidget(inner)
    return area, lay


def _checks(*boxes: QCheckBox, row: bool = False) -> QHBoxLayout | QVBoxLayout:
    """Checkboxes in a row (short labels) or a stack, SPACE_2 apart."""
    lay = hbox(spacing=SPACE_4) if row else vbox(spacing=SPACE_1)
    for b in boxes:
        lay.addWidget(b)
    if row:
        lay.addStretch(1)
    return lay


def _checkbox(text: str, value: bool, on_toggle, tip: str = "") -> QCheckBox:
    box = QCheckBox(text)
    box.setChecked(value)
    box.toggled.connect(on_toggle)
    if tip:
        box.setToolTip(tip)
    return box


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

        lay = vbox(self, (0, SPACE_3, 0, 0), SPACE_3)
        top = vbox(margins=(SPACE_4, 0, SPACE_4, 0), spacing=SPACE_3)
        recipe = Section("Recipe")
        self.recipe = QComboBox()
        self.recipe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.recipe.setToolTip(
            "Recipes remember format, folder and naming so you can reuse them in one click"
        )
        self.recipe.activated.connect(self._recipe_picked)
        recipe.add(self.recipe)
        top.addWidget(recipe)
        self.tabs = Segmented([("video", "Video"), ("photo", "Photo"), ("audio", "Audio")])
        top.addWidget(self.tabs)
        lay.addLayout(top)
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
        fmt = Section("Format")
        self.v_fmt = combo(
            [
                (
                    p.key,
                    f"{p.title}   ·   {'.' + p.ext if p.ext else 'audio file'}",
                    p.subtitle.split(" · ")[0],
                )
                for p in VIDEO_PRESETS
            ],
            self.s.video_preset,
        )
        self.v_fmt.currentIndexChanged.connect(lambda: self._video_preset(self.v_fmt.currentData()))
        fmt.add(self.v_fmt)

        self.sec_variant = Section("Flavor")
        self.v_variant = QComboBox()
        self.v_variant.setCursor(Qt.CursorShape.PointingHandCursor)
        self.v_variant.currentIndexChanged.connect(self._variant_picked)
        self.sec_variant.add(self.v_variant)

        self.sec_size = Section("Size")
        self.v_size = combo([(c.key, c.label, "") for c in RESIZE_VIDEO], self.s.video_resize)
        self.v_size.currentIndexChanged.connect(lambda: self._set("video_resize", self.v_size.currentData()))
        self.sec_size.add(self.v_size)

        self.sec_deint = Section("Interlaced footage")
        self.v_deint = combo([(c.key, c.label, "") for c in DEINTERLACE], self.s.deinterlace)
        self.v_deint.setToolTip(
            "Only affects footage that's actually interlaced (old camcorders, broadcast, 1080i)"
        )
        self.v_deint.currentIndexChanged.connect(lambda: self._set("deinterlace", self.v_deint.currentData()))
        self.sec_deint.add(self.v_deint)

        self.sec_lut = Section("LUT")
        self.lut = QComboBox()
        self.lut.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lut.setToolTip("Apply a LUT to every video — handy for review copies")
        self.lut.activated.connect(self._lut_picked)
        self.sec_lut.add(self.lut)

        self.sec_burn = Section("Burn in")
        self.burn_tc = _checkbox("Timecode", self.s.burn_timecode, lambda v: self._set("burn_timecode", v))
        self.burn_name = _checkbox("File name", self.s.burn_filename, lambda v: self._set("burn_filename", v))
        self.sec_burn.add(_checks(self.burn_tc, self.burn_name, row=True))

        speed = Section("Speed")
        self.v_hw = _checkbox(
            "Hardware encoding (faster)", self.s.hardware, lambda v: self._set("hardware", v)
        )
        self.v_par = _checkbox(
            "Convert two files at once",
            self.s.parallel,
            lambda v: self._set("parallel", v),
            "Fastest with the hardware encoder or lots of small files",
        )
        speed.add(_checks(self.v_hw, self.v_par))

        self.sec_audio = Section("Audio")
        self.v_tracks = _checkbox(
            "Keep every audio track", self.s.keep_all_audio, lambda v: self._set("keep_all_audio", v)
        )
        self.sec_audio.add(self.v_tracks)

        for sec in (
            fmt,
            self.sec_variant,
            self.sec_size,
            self.sec_deint,
            self.sec_lut,
            self.sec_burn,
            speed,
            self.sec_audio,
        ):
            lay.addWidget(sec)
        lay.addStretch(1)
        self.stack.addWidget(page)
        self._sync_lut()

    def _build_photo(self) -> None:
        page, lay = _page()
        fmt = Section("Format")
        self.p_fmt = combo(
            [
                (f.key, f"{f.title.split(' ·')[0]}   ·   .{f.ext}", PHOTO_TIPS.get(f.key, ""))
                for f in PHOTO_FORMATS
            ],
            self.s.photo_format,
        )
        self.p_fmt.currentIndexChanged.connect(
            lambda: (self._set("photo_format", self.p_fmt.currentData()), self._sync_photo())
        )
        fmt.add(self.p_fmt)

        self.sec_quality = Section(f"Quality · {self.s.photo_quality}")
        self.p_q = QSlider(Qt.Orientation.Horizontal)
        self.p_q.setRange(50, 100)
        self.p_q.setValue(self.s.photo_quality)
        self.p_q.valueChanged.connect(self._photo_q)
        self.sec_quality.add(self.p_q)

        size = Section("Size")
        self.p_size = combo([(c.key, c.label, "") for c in RESIZE_PHOTO], self.s.photo_resize)
        self.p_size.currentIndexChanged.connect(lambda: self._set("photo_resize", self.p_size.currentData()))
        size.add(self.p_size)

        meta = Section("Metadata")
        self.p_meta = _checkbox(
            "Keep camera info and color profile",
            self.s.photo_keep_metadata,
            lambda v: self._set("photo_keep_metadata", v),
        )
        meta.add(self.p_meta)
        for sec in (fmt, self.sec_quality, size, meta):
            lay.addWidget(sec)
        lay.addStretch(1)
        self.stack.addWidget(page)

    def _build_audio(self) -> None:
        page, lay = _page()
        fmt = Section("Format")
        self.a_fmt = combo(
            [(f.key, f"{f.title}   ·   .{f.ext}", AUDIO_TIPS.get(f.key, "")) for f in AUDIO_FORMATS],
            self.s.audio_format,
        )
        self.a_fmt.currentIndexChanged.connect(lambda: self._set("audio_format", self.a_fmt.currentData()))
        fmt.add(self.a_fmt)
        lay.addWidget(fmt)
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
        self.sec_variant.set_title(p.variant_label)
        self.sec_variant.setVisible(bool(p.variants))
        self.sec_size.setVisible(p.key not in ("rewrap", "proxy", "gif", "audio"))
        self.sec_deint.setVisible(p.key not in ("rewrap", "audio"))
        looks = p.key not in ("rewrap", "audio")
        self.sec_lut.setVisible(looks)
        self.sec_burn.setVisible(looks)
        self.sec_audio.setVisible(p.edit_format)

    def _sync_photo(self) -> None:
        q = next(f for f in PHOTO_FORMATS if f.key == self.s.photo_format).has_quality
        self.sec_quality.setVisible(q)

    def _photo_q(self, v: int) -> None:
        self.sec_quality.set_title(f"Quality · {v}")
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
            return sorted(
                (str(p) for p in Path(folder).rglob("*") if p.suffix.lower() in LUT_EXTS and p.is_file()),
                key=lambda p: Path(p).name.lower(),
            )[:300]
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
        c.addItem(
            f"Change LUT folder ({Path(lut_folder).name})…" if lut_folder else "Use a LUT folder…", LUT_FOLDER
        )
        c.setCurrentIndex(max(0, c.findData(current)))
        c.setToolTip(current or "Apply a LUT to every video — handy for review copies")
        c.blockSignals(False)

    def _lut_picked(self, index: int) -> None:
        data = self.lut.itemData(index)
        if data == LUT_FILE:
            start = str(Path(self.s.lut_path).parent) if self.s.lut_path else str(Path.home())
            f, _ = QFileDialog.getOpenFileName(
                self, "Choose a LUT", start, "LUT files (*.cube *.3dl *.dat *.m3d *.csp);;All files (*)"
            )
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
            return [
                r for r in data if isinstance(r, dict) and r.get("name") and isinstance(r.get("values"), dict)
            ]
        except (ValueError, TypeError):
            return []

    def _all_recipes(self) -> list[tuple[str, dict, bool]]:
        out = [(n, v, False) for n, v in BUILTIN_RECIPES]
        out += [(r["name"], r["values"], True) for r in self._user_recipes()]
        return out

    def _match_recipe(self) -> None:
        """Show which recipe the current settings match (if any) and rebuild the picker."""
        recipes = self._all_recipes()
        names = ([self._current_recipe] if self._current_recipe else []) + [
            n for n, _, _ in recipes if n != self._current_recipe
        ]
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
            if (
                QMessageBox.question(self, "Delete recipe", f"Delete the recipe “{current}”?")
                == QMessageBox.StandardButton.Yes
            ):
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
            for box, key in (
                (self.v_fmt, self.s.video_preset),
                (self.v_size, self.s.video_resize),
                (self.v_deint, self.s.deinterlace),
                (self.p_fmt, self.s.photo_format),
                (self.p_size, self.s.photo_resize),
                (self.a_fmt, self.s.audio_format),
            ):
                set_combo(box, key)
            for box, val in (
                (self.v_hw, self.s.hardware),
                (self.v_tracks, self.s.keep_all_audio),
                (self.v_par, self.s.parallel),
                (self.burn_tc, self.s.burn_timecode),
                (self.burn_name, self.s.burn_filename),
                (self.p_meta, self.s.photo_keep_metadata),
            ):
                box.blockSignals(True)
                box.setChecked(val)
                box.blockSignals(False)
            self.p_q.blockSignals(True)
            self.p_q.setValue(self.s.photo_quality)
            self.p_q.blockSignals(False)
            self.sec_quality.set_title(f"Quality · {self.s.photo_quality}")
            self._sync_video()
            self._sync_photo()
            self._sync_lut()
        finally:
            self._loading = False
        self._match_recipe()

    # ------------------------------------------------------------------ capabilities
    def apply_capabilities(self, caps: Capabilities) -> None:
        from ..core.photo import is_heic_encodable
        from ..core.video import preset_available

        for p in VIDEO_PRESETS:
            ok = preset_available(p.key, caps) if p.needs else caps.ok
            if not ok:
                disable_item(self.v_fmt, p.key, "This copy of ffmpeg can't make this format.")
        if not is_heic_encodable():
            disable_item(self.p_fmt, "heic", "HEIC support isn't installed.")
        if "libmp3lame" not in caps.encoders:
            disable_item(self.a_fmt, "mp3", "This copy of ffmpeg can't make MP3.")
        if not caps.has_filter("lut3d"):
            self.lut.setEnabled(False)
            self.lut.setToolTip("This copy of ffmpeg can't apply LUTs")
        if not caps.has_filter("drawtext"):
            self.burn_tc.setEnabled(False)
            self.burn_name.setEnabled(False)

    def apply_hardware(self, hw: dict) -> None:
        if hw:
            names = ", ".join(
                sorted(
                    {("Apple VideoToolbox" if "videotoolbox" in e else "NVIDIA NVENC") for e in hw.values()}
                )
            )
            self.v_hw.setEnabled(True)
            self.v_hw.setToolTip(f"Uses {names} — much faster for H.264 and HEVC")
        else:
            self.v_hw.setEnabled(False)
            self.v_hw.setToolTip("No hardware encoder found on this computer")
