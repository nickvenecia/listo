"""Output formats and the settings a conversion runs with."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Choice:
    key: str
    label: str


@dataclass(frozen=True)
class VideoPreset:
    key: str
    title: str
    subtitle: str
    ext: str
    tag: str  # short name for the {preset} naming token
    variants: tuple[Choice, ...] = ()
    variant_label: str = ""
    default_variant: str = ""
    needs: tuple[str, ...] = ()  # ffmpeg encoders that must exist
    edit_format: bool = False  # keeps every audio track as uncompressed PCM
    hw_codec: str = ""  # "h264" / "hevc" if a hardware encoder can be used
    group: str = "share"  # edit | share | extract  (how the Video tab groups them)


QUALITY = (Choice("high", "High"), Choice("standard", "Standard"), Choice("small", "Small File"))

VIDEO_PRESETS: tuple[VideoPreset, ...] = (
    VideoPreset(
        "prores",
        "ProRes",
        "Edit-ready master · .mov",
        "mov",
        "prores",
        variants=(
            Choice("0", "Proxy"),
            Choice("1", "LT"),
            Choice("2", "422"),
            Choice("3", "422 HQ"),
            Choice("4", "4444"),
        ),
        variant_label="Flavor",
        default_variant="2",
        needs=("prores_ks",),
        edit_format=True,
    ),
    VideoPreset(
        "dnxhr",
        "DNxHR",
        "Edit-ready for Avid & Resolve · .mov",
        "mov",
        "dnxhr",
        variants=(
            Choice("dnxhr_lb", "LB"),
            Choice("dnxhr_sq", "SQ"),
            Choice("dnxhr_hq", "HQ"),
            Choice("dnxhr_hqx", "HQX 10-bit"),
            Choice("dnxhr_444", "444"),
        ),
        variant_label="Flavor",
        default_variant="dnxhr_hq",
        needs=("dnxhd",),
        edit_format=True,
    ),
    VideoPreset(
        "h264",
        "H.264",
        "Plays everywhere · .mp4",
        "mp4",
        "h264",
        variants=QUALITY,
        variant_label="Quality",
        default_variant="high",
        needs=("libx264",),
        hw_codec="h264",
    ),
    VideoPreset(
        "hevc",
        "HEVC (H.265)",
        "Same quality, about half the size · .mp4",
        "mp4",
        "hevc",
        variants=QUALITY,
        variant_label="Quality",
        default_variant="high",
        needs=("libx265",),
        hw_codec="hevc",
    ),
    VideoPreset(
        "av1",
        "AV1",
        "Smallest files, newest players · .mp4",
        "mp4",
        "av1",
        variants=QUALITY,
        variant_label="Quality",
        default_variant="standard",
        needs=("libsvtav1",),
    ),
    VideoPreset(
        "webm",
        "WebM",
        "For websites · .webm",
        "webm",
        "webm",
        variants=QUALITY,
        variant_label="Quality",
        default_variant="standard",
        needs=("libvpx-vp9",),
    ),
    VideoPreset(
        "proxy",
        "Edit Proxy",
        "Half-res ProRes Proxy, goes in a Proxy folder · .mov",
        "mov",
        "proxy",
        needs=("prores_ks",),
        edit_format=True,
    ),
    VideoPreset(
        "rewrap",
        "Rewrap",
        "No re-encode — instant and lossless · .mov",
        "mov",
        "rewrap",
        edit_format=True,
    ),
    VideoPreset(
        "gif",
        "GIF",
        "Silent looping clip · .gif",
        "gif",
        "gif",
        variants=(Choice("480", "480 Wide"), Choice("640", "640 Wide"), Choice("960", "960 Wide")),
        variant_label="Size",
        default_variant="640",
        needs=("gif",),
    ),
    VideoPreset(
        "audio",
        "Audio Only",
        "Pull the sound out (uses the Audio tab's format)",
        "",
        "audio",
    ),
)

_GROUPS = {"prores": "edit", "dnxhr": "edit", "proxy": "edit", "rewrap": "edit", "audio": "extract"}
_ORDER = ["prores", "dnxhr", "proxy", "rewrap", "h264", "hevc", "av1", "webm", "gif", "audio"]
VIDEO_PRESETS = tuple(
    sorted(
        (VideoPreset(**{**p.__dict__, "group": _GROUPS.get(p.key, "share")}) for p in VIDEO_PRESETS),
        key=lambda p: _ORDER.index(p.key),
    )
)
VIDEO_GROUPS = (("edit", "For Editing"), ("share", "For Sharing"), ("extract", "Pull Out"))
VIDEO_BY_KEY = {p.key: p for p in VIDEO_PRESETS}


@dataclass(frozen=True)
class AudioFormat:
    key: str
    title: str
    ext: str
    muxer: str
    codec: str
    extra: tuple[str, ...] = ()
    needs: str = ""


AUDIO_FORMATS: tuple[AudioFormat, ...] = (
    AudioFormat("wav24", "WAV · 24-bit", "wav", "wav", "pcm_s24le", ("-rf64", "auto")),
    AudioFormat("wav16", "WAV · 16-bit", "wav", "wav", "pcm_s16le", ("-rf64", "auto")),
    AudioFormat("aiff", "AIFF · 24-bit", "aiff", "aiff", "pcm_s24be"),
    AudioFormat("flac", "FLAC · lossless", "flac", "flac", "flac"),
    AudioFormat("mp3", "MP3 · 320 kbps", "mp3", "mp3", "libmp3lame", ("-b:a", "320k"), needs="libmp3lame"),
    AudioFormat("aac", "AAC · 256 kbps", "m4a", "ipod", "aac", ("-b:a", "256k")),
)
AUDIO_BY_KEY = {a.key: a for a in AUDIO_FORMATS}


@dataclass(frozen=True)
class PhotoFormat:
    key: str
    title: str
    ext: str
    has_quality: bool


PHOTO_FORMATS: tuple[PhotoFormat, ...] = (
    PhotoFormat("jpeg", "JPEG", "jpg", True),
    PhotoFormat("png", "PNG · lossless", "png", False),
    PhotoFormat("tiff", "TIFF · lossless", "tif", False),
    PhotoFormat("webp", "WebP", "webp", True),
    PhotoFormat("heic", "HEIC", "heic", True),
)
PHOTO_BY_KEY = {p.key: p for p in PHOTO_FORMATS}

RESIZE_VIDEO = (
    Choice("orig", "Original Size"),
    Choice("2160", "4K · 2160"),
    Choice("1440", "1440"),
    Choice("1080", "1080"),
    Choice("720", "720"),
    Choice("540", "540"),
    Choice("half", "Half Size"),
)
RESIZE_PHOTO = (
    Choice("orig", "Original Size"),
    Choice("6000", "6000 px Long Edge"),
    Choice("4000", "4000 px"),
    Choice("3000", "3000 px"),
    Choice("2048", "2048 px"),
    Choice("1920", "1920 px"),
    Choice("1080", "1080 px"),
)
DEINTERLACE = (
    Choice("smooth", "Deinterlace — Smooth (59.94p)"),
    Choice("film", "Deinterlace — Film Look (29.97p)"),
    Choice("off", "Leave Interlaced"),
)
DESTINATIONS = (  # the Where dropdown (ui/export_panel.WHERE + the folders picked before)
    Choice("source", "In Source Folder"),
    Choice("subfolder", "Create Subfolder"),
    Choice("folder", "Choose a Destination…"),
)
DESQUEEZE = (
    Choice("1", "No Desqueeze"),
    Choice("1.33", "Desqueeze 1.33×"),
    Choice("1.5", "Desqueeze 1.5×"),
    Choice("1.55", "Desqueeze 1.55×"),
    Choice("1.6", "Desqueeze 1.6×"),
    Choice("1.65", "Desqueeze 1.65×"),
    Choice("1.8", "Desqueeze 1.8×"),
    Choice("2", "Desqueeze 2×"),
)
ASPECT_CHOICES = (
    Choice("orig", "Keep the Original Shape"),
    Choice("16:9", "16:9 · Widescreen"),
    Choice("8:5", "8:5 · 16:10"),
    Choice("4:3", "4:3 · Classic TV"),
    Choice("1:1", "1:1 · Square"),
    Choice("4:5", "4:5 · Instagram Portrait"),
    Choice("9:16", "9:16 · Vertical"),
    Choice("1.85:1", "1.85:1 · Flat"),
    Choice("2:1", "2:1"),
    Choice("2.35:1", "2.35:1 · Scope"),
    Choice("2.39:1", "2.39:1 · Scope (Modern)"),
)
ASPECT_FIT = (
    Choice("crop", "Crop to Fill"),
    Choice("bars", "Add Black Bars"),
    Choice("matte", "Cinema Bars on Top"),
)
BURN_STYLES = (
    Choice("clean", "Clean"),
    Choice("vhs", "VHS Camcorder"),
)
# How clips WITHOUT their own timecode (camcorders, phones) are counted, burned in and stored.
# Clips with real timecode always keep theirs.
TIMECODE_MODES = (
    Choice("continuous", "Continuous Timecode"),  # one Convert = one tape: runs on from clip to clip
    Choice("restart", "Restart Timecode Each Clip"),  # every clip from 00:00:00:00
    Choice("record", "Match Record Time"),  # the time of day it was shot (time-of-day timecode)
)
COLLISIONS = (
    Choice("number", "Add a Number"),
    Choice("skip", "Skip That File"),
    Choice("replace", "Replace It"),
)


@dataclass
class Settings:
    video_preset: str = "prores"
    video_variant: dict[str, str] = field(default_factory=dict)
    video_resize: str = "orig"
    deinterlace: str = "smooth"
    hardware: bool = True
    keep_all_audio: bool = True
    audio_format: str = "wav24"
    photo_format: str = "jpeg"
    photo_quality: int = 92
    photo_resize: str = "orig"
    photo_keep_metadata: bool = True
    destination: str = "source"
    dest_folder: str = ""
    subfolder_name: str = "Listo"
    naming: str = "{name}"
    collision: str = "number"
    join: bool = False  # all the video clips in a batch become one long video (core/join.py)
    keep_dates: bool = True
    lut_path: str = ""
    burn_timecode: bool = False
    timecode_mode: str = "continuous"  # see TIMECODE_MODES (burned in and stored in the file)
    burn_filename: bool = False
    burn_datetime: bool = False  # the clip's own date + a running clock
    burn_style: str = "clean"  # see BURN_STYLES
    burn_badge: str = "play"  # VHS style: "play" (PLAY ► blinks, then goes), "rec" (● REC), "none"
    burn_stop: bool = False  # VHS style: STOP ■ on the last moment of the video (and its end screen)
    desqueeze: str = "1"  # anamorphic squeeze factor, see DESQUEEZE
    aspect: str = "orig"  # see ASPECT_CHOICES (frame.ASPECTS)
    aspect_fit: str = "crop"  # "crop" to fill, "bars" = pad to the new shape, "matte" = cinema bars on top
    matte_opacity: int = 100  # how dark cinema bars are, 0-100
    captions: bool = False  # transcribe speech, review it, burn it in
    caption_language: str = "auto"
    caption_model: str = "balanced"  # captions.MODELS
    caption_style: str = "clean"  # "clean" or "vhs"
    caption_box: bool = True  # black background behind each line
    caption_words: int = 7  # most words per line
    caption_lines: int = 2
    caption_size: str = "medium"  # small / medium / large
    caption_srt: bool = False  # also save an .srt file next to the video
    tape_blue: bool = False  # a screen at the start and end (core/tape.py; VHS look only)
    tape_screen: str = "blue"  # that screen: "blue" (VCR), "black", "bars" (color bars & tone), "color"
    tape_screen_color: str = ""  # "#RRGGBB" for "color" ("" = VCR blue)
    # "off"; "cuts" = a glitch at each cut of a joined video; "rare" / "often" = random glitches too
    tape_glitches: str = "off"
    verify: bool = True
    parallel: bool = False

    @property
    def overlays(self) -> bool:
        """Anything drawn over the picture (burn-ins or captions)."""
        return self.burns or self.captions

    @property
    def burns(self) -> bool:
        """True when anything should be burned into the picture."""
        return self.burn_timecode or self.burn_filename or self.burn_datetime

    def variant_for(self, preset_key: str) -> str:
        p = VIDEO_BY_KEY[preset_key]
        v = self.video_variant.get(preset_key, p.default_variant)
        if p.variants and v not in {c.key for c in p.variants}:
            return p.default_variant
        return v

    def to_dict(self) -> dict:
        return asdict(self)

    def copy(self) -> Settings:
        return Settings.from_dict(self.to_dict())

    def apply(self, values: dict) -> None:
        """Apply a partial dict (a recipe or a per-file override) in place."""
        for k, v in (values or {}).items():
            if k == "video_variant" and isinstance(v, dict):
                self.video_variant.update(v)
            elif hasattr(self, k) and type(v) is type(getattr(self, k)):
                setattr(self, k, v)

    @staticmethod
    def complete(values: dict) -> dict:
        """A saved recipe with today's defaults filled in for settings added after it was saved
        (so an old recipe turns new options off instead of leaving them as they were)."""
        return {**Settings().to_dict(), **_migrate(values or {})}

    def matches(self, values: dict) -> bool:
        cur = self.to_dict()
        for k, v in (values or {}).items():
            if k == "video_variant" and isinstance(v, dict):
                if any(self.variant_for(pk) != pv for pk, pv in v.items() if pk in VIDEO_BY_KEY):
                    return False
            elif k in cur and cur[k] != v:
                return False
        return True

    def with_override(self, override: dict) -> Settings:
        s = self.copy()
        s.apply(override)
        return s

    @classmethod
    def from_dict(cls, d: dict) -> Settings:
        s = cls()
        for k, v in _migrate(d or {}).items():
            if hasattr(s, k) and type(v) is type(getattr(s, k)):
                setattr(s, k, v)
        if s.video_preset not in VIDEO_BY_KEY:
            s.video_preset = "prores"
        if s.audio_format not in AUDIO_BY_KEY:
            s.audio_format = "wav24"
        if s.photo_format not in PHOTO_BY_KEY:
            s.photo_format = "jpeg"
        return s


def _migrate(values: dict) -> dict:
    """Settings saved by older versions, in today's terms."""
    values = dict(values)
    if values.pop("tape_cut_glitch", False) and values.get("tape_glitches", "off") == "off":
        values["tape_glitches"] = "cuts"  # (was its own switch until 2.3)
    return values


# Recipes are made by you (Save as recipe); none are built in.
BUILTIN_RECIPES: tuple[tuple[str, dict], ...] = ()

# What a per-file override may change (just the output format).
OVERRIDE_KEYS = ("video_preset", "video_variant", "photo_format", "audio_format")
# Off again every time Listo opens (everything else is remembered): captions start heavy background
# work as soon as files arrive, and joining changes what comes out. Recipes still carry them.
SESSION_ONLY = ("captions", "join")


def timecode_mode(s: Settings, joining: bool = False, preset: str = "") -> str:
    """TIMECODE_MODES key for clips without their own timecode (preset: a file's own format choice).
    Rewrap and sound-only can't show timecode (the choice is hidden for them), so they keep the old
    rule: a joined video runs on, separate files don't."""
    if (preset or s.video_preset) in ("rewrap", "audio"):
        return "continuous" if joining else "restart"
    return s.timecode_mode if s.timecode_mode in {c.key for c in TIMECODE_MODES} else "continuous"


def format_label(kind: str, s: Settings) -> str:
    """Short name of what this file will become, e.g. 'ProRes 422' or 'JPEG'."""
    if kind == "photo":
        return PHOTO_BY_KEY[s.photo_format].title.split(" ·")[0]
    if kind == "audio" or (kind == "video" and s.video_preset == "audio"):
        return AUDIO_BY_KEY[s.audio_format].title.replace(" · ", " ")
    p = VIDEO_BY_KEY[s.video_preset]
    if p.variants and p.key in ("prores", "dnxhr"):
        v = s.variant_for(p.key)
        label = next(c.label for c in p.variants if c.key == v)
        return f"{p.title} {label}"
    return p.title


def output_ext(kind: str, s: Settings) -> str:
    if kind == "photo":
        return PHOTO_BY_KEY[s.photo_format].ext
    if kind == "audio" or (kind == "video" and s.video_preset == "audio"):
        return AUDIO_BY_KEY[s.audio_format].ext
    return VIDEO_BY_KEY[s.video_preset].ext


def preset_tag(kind: str, s: Settings) -> str:
    if kind == "photo":
        return s.photo_format
    if kind == "audio" or s.video_preset == "audio":
        return s.audio_format
    p = VIDEO_BY_KEY[s.video_preset]
    if p.key == "prores":
        flavor = {"0": "proxy", "1": "lt", "2": "422", "3": "hq", "4": "4444"}[s.variant_for("prores")]
        return f"prores{flavor}"
    if p.key == "dnxhr":
        return s.variant_for("dnxhr").replace("_", "")
    return p.tag
