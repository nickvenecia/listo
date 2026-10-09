"""The settings panel on the right: recipe picker + Video / Photo / Audio settings."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QInputDialog,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.captions import LANGUAGES
from ..core.captions import MODELS as CAPTION_MODELS
from ..core.presets import (
    ASPECT_CHOICES,
    AUDIO_FORMATS,
    BUILTIN_RECIPES,
    DEINTERLACE,
    DESQUEEZE,
    PHOTO_FORMATS,
    RESIZE_PHOTO,
    RESIZE_VIDEO,
    VIDEO_BY_KEY,
    VIDEO_PRESETS,
    Settings,
)
from ..core.tape import NO_EFFECTS
from ..core.tools import Capabilities
from .tokens import SCROLL_GUTTER, SIDEBAR_W, SPACE_1, SPACE_3, SPACE_4
from .widgets import (
    Disclosure,
    FitScroll,
    Section,
    Segmented,
    StepHeader,
    ToggleRow,
    combo,
    disable_item,
    hbox,
    set_combo,
    vbox,
)

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


def _page() -> tuple[QScrollArea, QVBoxLayout]:
    """A scrolling settings page. Sections go in it; the layout spaces them SPACE_3 apart."""
    area = FitScroll()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    inner = QWidget()
    lay = vbox(inner, (SPACE_4, SPACE_3, SPACE_4 - SCROLL_GUTTER, SPACE_4), SPACE_3)
    area.setWidget(inner)
    return area, lay


def _checks(*rows: ToggleRow, row: bool = False) -> QVBoxLayout:
    """On/off settings stacked as full-width rows (label left, switch right). `row` is ignored:
    side-by-side boxes made the panel look cluttered and left-leaning."""
    lay = vbox(spacing=0)
    for r in rows:
        lay.addWidget(r)
    return lay


def _checkbox(text: str, value: bool, on_toggle, tip: str = "") -> ToggleRow:
    box = ToggleRow(text, value)
    box.toggled.connect(on_toggle)
    if tip:
        box.setToolTip(tip)
    return box


# Settings counted in each folded group's "· N changed" (so nothing changed hides when folded).
GROUPS: dict[str, tuple[str, ...]] = {
    "picture": ("desqueeze", "aspect", "deinterlace", "lut_path"),
    "text": (
        "burn_timecode",
        "burn_filename",
        "burn_datetime",
        "captions",
        "tape_blue",
        "tape_cut_glitch",
        "tape_glitches",
    ),
    "sound": ("hardware", "parallel", "keep_all_audio"),
    "photo": ("photo_keep_metadata",),
}


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
        self._hw_ok: bool | None = None  # None until the hardware check finishes
        self._has_interlaced = False  # any interlaced file in the list
        self._current_recipe: str | None = None
        self._emit_timer = QTimer(self)
        self._emit_timer.setSingleShot(True)
        self._emit_timer.setInterval(120)
        self._emit_timer.timeout.connect(self._emit_changed)

        lay = vbox(self, 0, SPACE_3)
        lay.addWidget(StepHeader(2, "Convert To"))
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
        self._update_advanced()
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

        self.sec_frame = Section("Frame")
        self.v_squeeze = combo([(c.key, c.label, "") for c in DESQUEEZE], self.s.desqueeze)
        self.v_squeeze.setToolTip(
            "For footage shot with an anamorphic lens: stretches it back to its real shape"
        )
        self.v_squeeze.currentIndexChanged.connect(
            lambda: self._set("desqueeze", self.v_squeeze.currentData())
        )
        self.v_aspect = combo([(c.key, c.label, "") for c in ASPECT_CHOICES], self.s.aspect)
        self.v_aspect.setToolTip("The shape of the finished video")
        self.v_aspect.currentIndexChanged.connect(self._aspect_picked)
        self.v_fit = combo(
            [
                ("crop", "Crop to Fill", "Fills the new shape, trimming the edges that don't fit (centered)"),
                ("bars", "Add Black Bars", "Keeps the whole picture; the video becomes the new shape"),
                ("matte", "Cinema Bars on Top", "Keeps the video's size and draws bars over the picture"),
            ],
            self.s.aspect_fit,
        )
        self.v_fit.currentIndexChanged.connect(self._fit_picked)
        for c in (self.v_squeeze, self.v_aspect, self.v_fit):
            self.sec_frame.add(c)
        self.matte_row = QWidget()
        mr = hbox(self.matte_row, spacing=SPACE_3)
        lbl = QLabel("Bar Opacity")
        lbl.setObjectName("Muted")
        self.matte_q = QSlider(Qt.Orientation.Horizontal)
        self.matte_q.setRange(0, 100)
        self.matte_q.setSingleStep(5)
        self.matte_q.setPageStep(10)
        self.matte_q.setValue(self.s.matte_opacity)
        self.matte_q.setCursor(Qt.CursorShape.PointingHandCursor)
        self.matte_val = QLabel(f"{self.s.matte_opacity}%")
        self.matte_val.setObjectName("Muted")
        self.matte_q.valueChanged.connect(self._matte_opacity)
        mr.addWidget(lbl)
        mr.addWidget(self.matte_q, 1)
        mr.addWidget(self.matte_val)
        self.sec_frame.add(self.matte_row)

        self.sec_deint = Section("Interlaced Footage")
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

        self.sec_burn = Section("Clip Info")
        self.burn_tc = _checkbox("Timecode", self.s.burn_timecode, lambda v: self._burn("burn_timecode", v))
        self.burn_name = _checkbox(
            "File Name", self.s.burn_filename, lambda v: self._burn("burn_filename", v)
        )
        self.burn_dt = _checkbox(
            "Date & Time",
            self.s.burn_datetime,
            lambda v: self._burn("burn_datetime", v),
            "When the clip was shot, read from the clip itself, with a clock that runs as it plays",
        )
        self.sec_burn.add(_checks(self.burn_tc, self.burn_name, self.burn_dt))
        self.burn_style = combo(
            [
                ("clean", "Clean Look", "Small labels on dark boxes in the corners"),
                (
                    "vhs",
                    "VHS Camcorder Look",
                    "PLAY, date and a running clock in a VCR font, like an old camcorder",
                ),
            ],
            self.s.burn_style,
        )
        self.burn_style.currentIndexChanged.connect(
            lambda: self._set_and_sync("burn_style", self.burn_style.currentData())
        )
        self.burn_badge = combo(
            [
                (
                    "play",
                    "PLAY ► at the Start",
                    "Blinks for the first few seconds, then goes away, like a VCR",
                ),
                ("rec", "● REC", "Red dot blinking, like a camcorder while recording"),
                ("none", "No Badge", ""),
            ],
            self.s.burn_badge,
        )
        self.burn_badge.currentIndexChanged.connect(
            lambda: self._set_and_sync("burn_badge", self.burn_badge.currentData())
        )

        # ---- tape effects (core/tape.py)
        self.sec_tape = Section("Tape Effects")
        self.tape_blue = _checkbox(
            "Blue Screen at Start and End", self.s.tape_blue, lambda v: self._set("tape_blue", v),
            "Two seconds of VCR blue before the video starts and after it ends",
        )  # fmt: skip
        self.tape_cut = _checkbox(
            "Glitch Between Joined Clips", self.s.tape_cut_glitch, lambda v: self._set("tape_cut_glitch", v),
            "Half a second of tape tracking trouble at each cut, like a camcorder starting to record again",
        )  # fmt: skip
        self.sec_tape.add(_checks(self.tape_blue, self.tape_cut))
        self.tape_glitches = combo(
            [
                ("off", "No Random Glitches", ""),
                ("rare", "Glitches Now and Then", "A short tracking glitch about every minute and a half"),
                ("often", "Glitches Often", "A short tracking glitch about every half minute"),
            ],
            self.s.tape_glitches,
        )
        self.tape_glitches.currentIndexChanged.connect(
            lambda: self._set("tape_glitches", self.tape_glitches.currentData())
        )
        self.sec_tape.add(self.tape_glitches)

        self.sec_cc = Section("Captions")
        self.cc_on = _checkbox(
            "Add Captions",
            self.s.captions,
            lambda v: self._set_and_sync("captions", v),
            "Listo listens to each clip on this computer, you check the words, then they're burned in",
        )
        self.sec_cc.add(self.cc_on)
        self.cc_box = QWidget()
        cb = vbox(self.cc_box, 0, SPACE_1)
        self.cc_lang = combo([(k, t, "") for k, t in LANGUAGES], self.s.caption_language)
        self.cc_lang.setToolTip("'Detect automatically' also follows people switching languages")
        self.cc_lang.currentIndexChanged.connect(
            lambda: self._set("caption_language", self.cc_lang.currentData())
        )
        self.cc_model = combo(
            [
                (k, f"{t} · {CAPTION_MODELS[k][1]} download", "")
                for k, t in (("fast", "Fast"), ("balanced", "Balanced Accuracy"), ("best", "Most Accurate"))
            ],
            self.s.caption_model,
        )
        self.cc_model.setToolTip("Downloaded once the first time it's used. More accurate = slower")
        self.cc_model.currentIndexChanged.connect(
            lambda: self._set("caption_model", self.cc_model.currentData())
        )
        self.cc_style = combo(
            [
                ("clean", "Clean", "Like modern subtitles"),
                ("vhs", "VHS", "VCR font, like closed captions on tape"),
            ],
            self.s.caption_style,
        )
        self.cc_style.currentIndexChanged.connect(
            lambda: self._set("caption_style", self.cc_style.currentData())
        )
        self.cc_bg = _checkbox("Black Background", self.s.caption_box, lambda v: self._set("caption_box", v))
        self.cc_size = combo(
            [("small", "Small Text", ""), ("medium", "Medium Text", ""), ("large", "Large Text", "")],
            self.s.caption_size,
        )
        self.cc_size.currentIndexChanged.connect(
            lambda: self._set("caption_size", self.cc_size.currentData())
        )
        self.cc_lines = combo(
            [("1", "1 Line at a Time", ""), ("2", "Up to 2 Lines", ""), ("3", "Up to 3 Lines", "")],
            str(self.s.caption_lines),
        )
        self.cc_lines.currentIndexChanged.connect(
            lambda: self._set("caption_lines", int(self.cc_lines.currentData()))
        )
        words_row = QWidget()
        wr = hbox(words_row, spacing=SPACE_3)
        wl = QLabel("Words per Line")
        wl.setObjectName("Muted")
        self.cc_words = QSlider(Qt.Orientation.Horizontal)
        self.cc_words.setRange(2, 12)
        self.cc_words.setValue(self.s.caption_words)
        self.cc_words.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cc_words_val = QLabel(str(self.s.caption_words))
        self.cc_words_val.setObjectName("Muted")
        self.cc_words.valueChanged.connect(self._caption_words)
        wr.addWidget(wl)
        wr.addWidget(self.cc_words, 1)
        wr.addWidget(self.cc_words_val)
        self.cc_srt = _checkbox(
            "Also Save a Caption File (.srt)", self.s.caption_srt, lambda v: self._set("caption_srt", v),
            "For YouTube, players and editing apps",
        )  # fmt: skip
        for w in (self.cc_lang, self.cc_model, self.cc_style, self.cc_size, self.cc_lines, words_row):
            cb.addWidget(w)
        cb.addLayout(_checks(self.cc_bg, self.cc_srt))
        self.sec_cc.add(self.cc_box)
        self.sec_burn.add(self.burn_style)
        self.sec_burn.add(self.burn_badge)

        speed = Section("Speed")
        self.v_hw = _checkbox(
            "Hardware Encoding (Faster)", self.s.hardware, lambda v: self._set("hardware", v)
        )
        self.v_par = _checkbox(
            "Convert Two Files at Once",
            self.s.parallel,
            lambda v: self._set("parallel", v),
            "Fastest with the hardware encoder or lots of small files",
        )
        speed.add(_checks(self.v_hw, self.v_par))

        self.sec_audio = Section("Audio")
        self.v_tracks = _checkbox(
            "Keep Every Audio Track", self.s.keep_all_audio, lambda v: self._set("keep_all_audio", v)
        )
        self.sec_audio.add(self.v_tracks)

        for sec in (fmt, self.sec_variant, self.sec_size):
            lay.addWidget(sec)
        self.g_picture = self._group("Image", "picture")
        for sec in (self.sec_frame, self.sec_deint, self.sec_lut):
            self.g_picture.add(sec)
        self.g_text = self._group("Burn-In", "text")
        for sec in (self.sec_burn, self.sec_cc, self.sec_tape):
            self.g_text.add(sec)
        self.g_sound = self._group("Encoding", "sound")
        for sec in (self.sec_audio, speed):
            self.g_sound.add(sec)
        for g in (self.g_picture, self.g_text, self.g_sound):
            lay.addWidget(g)
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
        for sec in (fmt, self.sec_quality, size):
            lay.addWidget(sec)
        self.p_adv = self._group("More", "photo")
        self.p_adv.add(meta)
        lay.addWidget(self.p_adv)
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
        self._update_advanced()
        self._emit_timer.start()

    # ------------------------------------------------------------------ advanced options
    def _group(self, title: str, key: str) -> Disclosure:
        d = Disclosure(title, is_open=self.qs.value(f"group_open/{key}", False, type=bool))
        d.toggled.connect(lambda on, k=key: self.qs.setValue(f"group_open/{k}", on))
        d.setProperty("group", key)
        return d

    def open_groups(self, on: bool) -> None:
        for d in (self.g_picture, self.g_text, self.g_sound, self.p_adv):
            d.set_open(on, emit=True)

    def _update_advanced(self) -> None:
        """Each folded group says how many of its settings differ from a fresh start."""
        if not hasattr(self, "p_adv"):
            return
        base = Settings()
        for d in (self.g_picture, self.g_text, self.g_sound, self.p_adv):
            keys = GROUPS[d.property("group")]
            n = sum(1 for k in keys if getattr(self.s, k) != getattr(base, k))
            d.set_summary(f"{n} changed" if n else "")

    def _emit_changed(self) -> None:
        self._update_advanced()
        self._match_recipe()
        self.changed.emit()

    def notify_external_change(self) -> None:
        """Settings changed elsewhere (e.g. Export options) — keep the recipe picker honest."""
        self._sync_text()  # (joining shows "Glitch Between Joined Clips")
        self._match_recipe()

    def _video_preset(self, key: str) -> None:
        self._set("video_preset", key)
        self._sync_video()

    def _set_and_sync(self, attr: str, value) -> None:
        self._set(attr, value)
        self._sync_text()

    def _caption_words(self, v: int) -> None:
        self.cc_words_val.setText(str(v))
        self._set("caption_words", v)

    def _sync_text(self) -> None:
        """Burn-in and caption options only show when they're switched on."""
        self.tape_cut.setVisible(self.s.join)  # only joined videos have cuts
        self.burn_style.setVisible(self.s.burns)
        self.burn_badge.setVisible(self.s.burns and self.s.burn_style == "vhs")
        self.cc_box.setVisible(self.s.captions)

    def _aspect_picked(self) -> None:
        self._set("aspect", self.v_aspect.currentData())
        self._sync_frame()

    def _fit_picked(self) -> None:
        self._set("aspect_fit", self.v_fit.currentData())
        self._sync_frame()

    def _matte_opacity(self, v: int) -> None:
        self.matte_val.setText(f"{v}%")
        self._set("matte_opacity", v)

    def _sync_frame(self) -> None:
        reshaping = self.s.aspect != "orig"
        self.v_fit.setVisible(reshaping)
        self.matte_row.setVisible(reshaping and self.s.aspect_fit == "matte")

    def _burn(self, attr: str, value: bool) -> None:
        self._set(attr, value)
        self._sync_text()

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
        self.sec_deint.setVisible(p.key not in ("rewrap", "audio") and self._has_interlaced)
        self.v_hw.setVisible(bool(self._hw_ok) and p.key in ("h264", "hevc"))
        looks = p.key not in ("rewrap", "audio")
        self.sec_lut.setVisible(looks)
        self.sec_burn.setVisible(looks)
        self.sec_tape.setVisible(p.key not in NO_EFFECTS)
        self.sec_frame.setVisible(looks)
        self._sync_frame()
        self._sync_text()
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
        c.addItem("Choose a LUT File…", LUT_FILE)
        lut_folder = str(self.qs.value("lut_folder", "") or "")
        c.addItem(
            f"Change LUT folder ({Path(lut_folder).name})…" if lut_folder else "Use a LUT Folder…", LUT_FOLDER
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
            d = QFileDialog.getExistingDirectory(self, "Choose Your LUT Folder", start)
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
            if vals is not None and self.s.matches(Settings.complete(vals)):
                found = name
                break
        self._current_recipe = found
        user = {r["name"] for r in self._user_recipes()}

        c = self.recipe
        c.blockSignals(True)
        c.clear()
        c.addItem("No Recipe" if not recipes else "Custom Settings", None)
        for name, _, _ in recipes:
            c.addItem(name, name)
        c.insertSeparator(c.count())
        c.addItem("Save Current Settings as a Recipe…", ACTION_SAVE)
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
                QMessageBox.question(self, "Delete Recipe", f"Delete the recipe “{current}”?")
                == QMessageBox.StandardButton.Yes
            ):
                self._delete_recipe(current)
        elif data:
            vals = next((v for n, v, _ in self._all_recipes() if n == data), None)
            if vals is not None:
                self.s.apply(Settings.complete(vals))
                if self.s.destination == "folder" and not self.s.dest_folder:
                    self.s.destination = "source"
                self._current_recipe = data
                self.reload()
                self.recipe_applied.emit()
                self.changed.emit()
                return
        self._match_recipe()  # put the picker back on the right entry

    def _save_recipe(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Recipe", "Name this recipe:")
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
                (self.v_squeeze, self.s.desqueeze),
                (self.v_aspect, self.s.aspect),
                (self.v_fit, self.s.aspect_fit),
                (self.burn_style, self.s.burn_style),
                (self.burn_badge, self.s.burn_badge),
                (self.tape_glitches, self.s.tape_glitches),
                (self.cc_lang, self.s.caption_language),
                (self.cc_model, self.s.caption_model),
                (self.cc_style, self.s.caption_style),
                (self.cc_size, self.s.caption_size),
                (self.cc_lines, str(self.s.caption_lines)),
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
                (self.burn_dt, self.s.burn_datetime),
                (self.cc_on, self.s.captions),
                (self.tape_blue, self.s.tape_blue),
                (self.tape_cut, self.s.tape_cut_glitch),
                (self.cc_bg, self.s.caption_box),
                (self.cc_srt, self.s.caption_srt),
                (self.p_meta, self.s.photo_keep_metadata),
            ):
                box.blockSignals(True)
                box.setChecked(val)
                box.blockSignals(False)
            self.cc_words.blockSignals(True)
            self.cc_words.setValue(self.s.caption_words)
            self.cc_words.blockSignals(False)
            self.cc_words_val.setText(str(self.s.caption_words))
            self.matte_q.blockSignals(True)
            self.matte_q.setValue(self.s.matte_opacity)
            self.matte_q.blockSignals(False)
            self.matte_val.setText(f"{self.s.matte_opacity}%")
            self.p_q.blockSignals(True)
            self.p_q.setValue(self.s.photo_quality)
            self.p_q.blockSignals(False)
            self.sec_quality.set_title(f"Quality · {self.s.photo_quality}")
            self._sync_video()
            self._sync_photo()
            self._sync_lut()
        finally:
            self._loading = False
        self._update_advanced()
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

    def apply_hardware(self, hw: dict) -> None:
        if hw:
            names = ", ".join(
                sorted(
                    {("Apple VideoToolbox" if "videotoolbox" in e else "NVIDIA NVENC") for e in hw.values()}
                )
            )
            self.v_hw.setToolTip(f"Uses {names} — much faster for H.264 and HEVC")
        self._hw_ok = bool(hw)
        self._sync_video()

    def set_queue_info(self, has_interlaced: bool) -> None:
        """What's in the list decides which settings matter (e.g. deinterlacing only for interlaced files)."""
        if has_interlaced != self._has_interlaced:
            self._has_interlaced = has_interlaced
            self._sync_video()
