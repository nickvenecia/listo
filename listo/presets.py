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


QUALITY = (Choice("high", "High"), Choice("standard", "Standard"), Choice("small", "Small file"))

VIDEO_PRESETS: tuple[VideoPreset, ...] = (
    VideoPreset(
        "prores", "ProRes", "Edit-ready master · .mov", "mov", "prores",
        variants=(
            Choice("0", "Proxy"), Choice("1", "LT"), Choice("2", "422"),
            Choice("3", "422 HQ"), Choice("4", "4444"),
        ),
        variant_label="Flavor", default_variant="2", needs=("prores_ks",), edit_format=True,
    ),
    VideoPreset(
        "dnxhr", "DNxHR", "Edit-ready for Avid & Resolve · .mov", "mov", "dnxhr",
        variants=(
            Choice("dnxhr_lb", "LB"), Choice("dnxhr_sq", "SQ"), Choice("dnxhr_hq", "HQ"),
            Choice("dnxhr_hqx", "HQX 10-bit"), Choice("dnxhr_444", "444"),
        ),
        variant_label="Flavor", default_variant="dnxhr_hq", needs=("dnxhd",), edit_format=True,
    ),
    VideoPreset(
        "h264", "H.264", "Plays everywhere · .mp4", "mp4", "h264",
        variants=QUALITY, variant_label="Quality", default_variant="high",
        needs=("libx264",), hw_codec="h264",
    ),
    VideoPreset(
        "hevc", "HEVC (H.265)", "Same quality, about half the size · .mp4", "mp4", "hevc",
        variants=QUALITY, variant_label="Quality", default_variant="high",
        needs=("libx265",), hw_codec="hevc",
    ),
    VideoPreset(
        "av1", "AV1", "Smallest files, newest players · .mp4", "mp4", "av1",
        variants=QUALITY, variant_label="Quality", default_variant="standard", needs=("libsvtav1",),
    ),
    VideoPreset(
        "webm", "WebM", "For websites · .webm", "webm", "webm",
        variants=QUALITY, variant_label="Quality", default_variant="standard", needs=("libvpx-vp9",),
    ),
    VideoPreset(
        "proxy", "Edit proxy", "Half-res ProRes Proxy, goes in a Proxy folder · .mov", "mov", "proxy",
        needs=("prores_ks",), edit_format=True,
    ),
    VideoPreset(
        "rewrap", "Rewrap", "No re-encode — instant and lossless · .mov", "mov", "rewrap",
        edit_format=True,
    ),
    VideoPreset(
        "gif", "GIF", "Silent looping clip · .gif", "gif", "gif",
        variants=(Choice("480", "480 wide"), Choice("640", "640 wide"), Choice("960", "960 wide")),
        variant_label="Size", default_variant="640", needs=("gif",),
    ),
    VideoPreset(
        "audio", "Audio only", "Pull the sound out (uses the Audio tab's format)", "", "audio",
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
VIDEO_GROUPS = (("edit", "For editing"), ("share", "For sharing"), ("extract", "Pull out"))
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
    Choice("orig", "Original size"),
    Choice("2160", "4K · 2160"),
    Choice("1080", "1080"),
    Choice("720", "720"),
    Choice("540", "540"),
    Choice("half", "Half size"),
)
RESIZE_PHOTO = (
    Choice("orig", "Original size"),
    Choice("6000", "6000 px long edge"),
    Choice("4000", "4000 px"),
    Choice("3000", "3000 px"),
    Choice("2048", "2048 px"),
    Choice("1920", "1920 px"),
    Choice("1080", "1080 px"),
)
DEINTERLACE = (
    Choice("smooth", "Smooth motion (doubles fps: 29.97i → 59.94p)"),
    Choice("film", "Film look (keeps fps: 29.97i → 29.97p)"),
    Choice("off", "Leave interlaced"),
)
DESTINATIONS = (
    Choice("source", "Next to the original"),
    Choice("subfolder", "In a subfolder next to the original"),
    Choice("folder", "In one folder…"),
)
COLLISIONS = (
    Choice("number", "Add a number"),
    Choice("skip", "Skip that file"),
    Choice("replace", "Replace it"),
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
    keep_dates: bool = True
    lut_path: str = ""
    burn_timecode: bool = False
    burn_filename: bool = False
    verify: bool = True
    parallel: bool = False

    def variant_for(self, preset_key: str) -> str:
        p = VIDEO_BY_KEY[preset_key]
        v = self.video_variant.get(preset_key, p.default_variant)
        if p.variants and v not in {c.key for c in p.variants}:
            return p.default_variant
        return v

    def to_dict(self) -> dict:
        return asdict(self)

    def copy(self) -> "Settings":
        return Settings.from_dict(self.to_dict())

    def apply(self, values: dict) -> None:
        """Apply a partial dict (a recipe or a per-file override) in place."""
        for k, v in (values or {}).items():
            if k == "video_variant" and isinstance(v, dict):
                self.video_variant.update(v)
            elif hasattr(self, k) and type(v) is type(getattr(self, k)):
                setattr(self, k, v)

    def matches(self, values: dict) -> bool:
        cur = self.to_dict()
        for k, v in (values or {}).items():
            if k == "video_variant" and isinstance(v, dict):
                if any(self.variant_for(pk) != pv for pk, pv in v.items() if pk in VIDEO_BY_KEY):
                    return False
            elif k in cur and cur[k] != v:
                return False
        return True

    def with_override(self, override: dict) -> "Settings":
        s = self.copy()
        s.apply(override)
        return s

    @classmethod
    def from_dict(cls, d: dict) -> "Settings":
        s = cls()
        for k, v in (d or {}).items():
            if hasattr(s, k) and type(v) is type(getattr(s, k)):
                setattr(s, k, v)
        if s.video_preset not in VIDEO_BY_KEY:
            s.video_preset = "prores"
        if s.audio_format not in AUDIO_BY_KEY:
            s.audio_format = "wav24"
        if s.photo_format not in PHOTO_BY_KEY:
            s.photo_format = "jpeg"
        return s


# Recipes: a few useful starting points. Each only sets the fields it lists.
BUILTIN_RECIPES: tuple[tuple[str, dict], ...] = (
    ("ProRes 422 master", {
        "video_preset": "prores", "video_variant": {"prores": "2"}, "video_resize": "orig",
        "destination": "source", "naming": "{name}", "lut_path": "", "burn_timecode": False,
        "burn_filename": False}),
    ("Cards → ProRes LT, dated", {
        "video_preset": "prores", "video_variant": {"prores": "1"}, "video_resize": "orig",
        "destination": "subfolder", "subfolder_name": "ProRes", "naming": "{date}_{name}",
        "lut_path": "", "burn_timecode": False, "burn_filename": False}),
    ("Edit proxies", {
        "video_preset": "proxy", "destination": "source", "naming": "{name}",
        "lut_path": "", "burn_timecode": False, "burn_filename": False}),
    ("Client review + burn-ins", {
        "video_preset": "h264", "video_variant": {"h264": "standard"}, "video_resize": "1080",
        "destination": "subfolder", "subfolder_name": "Review", "naming": "{name}_review",
        "burn_timecode": True, "burn_filename": True}),
    ("Web / social 1080p", {
        "video_preset": "h264", "video_variant": {"h264": "standard"}, "video_resize": "1080",
        "destination": "source", "naming": "{name}_web", "lut_path": "",
        "burn_timecode": False, "burn_filename": False}),
    ("Photos for the web", {
        "photo_format": "jpeg", "photo_quality": 85, "photo_resize": "2048",
        "destination": "subfolder", "subfolder_name": "Web", "naming": "{name}"}),
)

# What a per-file override may change (just the output format).
OVERRIDE_KEYS = ("video_preset", "video_variant", "photo_format", "audio_format")


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
