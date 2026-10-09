"""Figure out what a file is: video, audio, photo — and the details that matter."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .tools import capabilities, run_quiet

VIDEO_EXTS = {
    "mov",
    "mp4",
    "m4v",
    "mts",
    "m2ts",
    "m2t",
    "ts",
    "mod",
    "tod",
    "mpg",
    "mpeg",
    "vob",
    "avi",
    "mkv",
    "webm",
    "mxf",
    "dv",
    "flv",
    "wmv",
    "asf",
    "3gp",
    "3g2",
    "ogv",
    "f4v",
    "y4m",
    "mjpeg",
    "hevc",
    "h264",
    "264",
    "265",
    "divx",
    "xvid",
}
AUDIO_EXTS = {
    "wav",
    "aif",
    "aiff",
    "aifc",
    "flac",
    "mp3",
    "m4a",
    "aac",
    "ogg",
    "opus",
    "wma",
    "caf",
    "ac3",
    "bwf",
    "w64",
    "alac",
    "amr",
}
RAW_EXTS = {
    "cr2",
    "cr3",
    "crw",
    "nef",
    "nrw",
    "arw",
    "srf",
    "sr2",
    "dng",
    "raf",
    "orf",
    "rw2",
    "pef",
    "srw",
    "3fr",
    "iiq",
    "erf",
    "kdc",
    "mrw",
    "x3f",
    "rwl",
    "mos",
}
IMAGE_EXTS = {
    "jpg",
    "jpeg",
    "jpe",
    "png",
    "tif",
    "tiff",
    "webp",
    "heic",
    "heif",
    "hif",
    "avif",
    "bmp",
    "gif",
    "tga",
    "jp2",
    "psd",
} | RAW_EXTS

# Formats people will try that we can't decode: say so instead of failing silently.
UNSUPPORTED_HINTS = {
    "braw": "Blackmagic RAW isn't supported — export from DaVinci Resolve or Blackmagic RAW Player first.",
    "r3d": "RED R3D isn't supported — export from REDCINE-X or Resolve first.",
    "ari": "ARRIRAW isn't supported — export from ARRI Reference Tool or Resolve first.",
    "crm": "Canon Cinema RAW Light isn't supported — export from Canon RAW Development or Resolve first.",
    "nev": "Nikon N-RAW isn't supported — export from NX Studio or Resolve first.",
}

KNOWN_EXTS = VIDEO_EXTS | AUDIO_EXTS | IMAGE_EXTS
# Files cameras write next to the clips. Listo reads what it needs from them (JVC .MOI: recording
# date + true aspect ratio) and leaves them out of the list instead of calling them unknown files.
SIDECAR_EXTS = {"moi", "thm", "pgi", "tid", "xml", "ifo", "bup", "mpl", "cpi", "bdm", "lrv"}


def ext_of(path: str | Path) -> str:
    return Path(path).suffix.lower().lstrip(".")


@dataclass
class MoiInfo:
    """What a JVC Everio .MOI file says about its .MOD / .TOD clip."""

    recorded: datetime | None = None  # camera clock: the local time where it was shot
    widescreen: bool | None = None  # True 16:9, False 4:3, None unknown
    pal: bool | None = None


def find_moi(clip: str | Path) -> Path | None:
    """The .MOI next to a .MOD / .TOD clip (same name, any letter case)."""
    p = Path(clip)
    if ext_of(p) not in ("mod", "tod"):
        return None
    for cand in (p.with_suffix(".MOI"), p.with_suffix(".moi")):
        if cand.is_file():
            return cand
    try:  # case-sensitive disks (Linux) with odd capitalisation
        stem = p.stem.lower()
        return next(
            (c for c in p.parent.iterdir() if c.suffix.lower() == ".moi" and c.stem.lower() == stem), None
        )
    except OSError:
        return None


def read_moi(path: str | Path) -> MoiInfo:
    """Parse a JVC .MOI (layout as documented by ExifTool's JVC MOI tags):
    0x00 'V6' version, 0x06 year (2 bytes), 0x08 month, 0x09 day, 0x0A hour, 0x0B minute,
    0x0C milliseconds into the minute (2 bytes), 0x80 aspect / TV system byte."""
    info = MoiInfo()
    try:
        data = Path(path).read_bytes()[:0x100]
    except OSError:
        return info
    if len(data) < 0x0E or not data.startswith(b"V"):
        return info
    year = int.from_bytes(data[6:8], "big")
    month, day, hour, minute = data[8], data[9], data[10], data[11]
    ms = int.from_bytes(data[12:14], "big")
    try:
        if 1990 <= year <= 2100:
            info.recorded = datetime(year, month, day, hour, minute, min(59, ms // 1000), (ms % 1000) * 1000)
    except ValueError:
        pass
    if len(data) > 0x80:
        b = data[0x80]
        lo, hi = b & 0x0F, b >> 4
        info.widescreen = True if lo in (4, 5) else False if lo < 2 else None
        info.pal = True if hi == 5 else False if hi == 4 else None
    return info


def kind_from_ext(path: str | Path) -> str:
    e = ext_of(path)
    if e in IMAGE_EXTS:
        return "photo"
    if e in AUDIO_EXTS:
        return "audio"
    if e in VIDEO_EXTS:
        return "video"
    return "unknown"


@dataclass
class AudioTrack:
    index: int
    codec: str
    channels: int
    sample_rate: int
    bits: int  # 16 / 24 / 32, best guess
    duration: float = 0.0


@dataclass
class MediaInfo:
    kind: str = "unknown"  # video | audio | photo | unknown
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    rate: str = ""  # exact frame rate, e.g. "30000/1001"
    vcodec: str = ""
    pix_fmt: str = ""
    bit_depth: int = 8
    field_order: str = ""
    interlaced: bool = False
    color_transfer: str = ""
    color_primaries: str = ""
    color_space: str = ""
    video_index: int | None = None
    audio: list[AudioTrack] = field(default_factory=list)
    timecode: str = ""
    created: datetime | None = None
    sar: float = 1.0  # pixel shape: 1 = square; DV / HDV store wider or narrower pixels
    error: str = ""

    @property
    def hdr(self) -> bool:
        return self.color_transfer in ("smpte2084", "arib-std-b67")

    @property
    def hdr_label(self) -> str:
        return {"smpte2084": "HDR PQ", "arib-std-b67": "HDR HLG"}.get(self.color_transfer, "")

    def summary_bits(self) -> list[str]:
        """Short badges for the UI: 3:24 · 1920×1080 · 29.97i · H.264 · 2 audio"""
        bits: list[str] = []
        if self.duration and self.kind != "photo":
            bits.append(fmt_duration(self.duration))  # first: the most useful, never cut off
        if self.width and self.height:
            bits.append(f"{self.width}×{self.height}")
        if self.kind == "video":
            if self.fps:
                f = f"{self.fps:.3f}".rstrip("0").rstrip(".")
                bits.append(f + ("i" if self.interlaced else "p"))
            if self.vcodec:
                bits.append(pretty_codec(self.vcodec))
        if self.kind in ("video", "audio") and self.audio:
            if self.kind == "audio":
                a = self.audio[0]
                bits.append(pretty_codec(a.codec))
                bits.append(f"{a.sample_rate / 1000:g} kHz" if a.sample_rate else "")
                bits.append({1: "mono", 2: "stereo"}.get(a.channels, f"{a.channels}ch"))
            else:
                n = len(self.audio)
                ch = sum(a.channels for a in self.audio)
                bits.append(
                    f"{n} audio tracks" if n > 1 else ({1: "mono", 2: "stereo"}.get(ch, f"{ch}ch audio"))
                )
        return [b for b in bits if b]


_PRETTY = {
    "h264": "H.264",
    "hevc": "HEVC",
    "prores": "ProRes",
    "mpeg2video": "MPEG-2",
    "mpeg4": "MPEG-4",
    "dvvideo": "DV",
    "dnxhd": "DNx",
    "av1": "AV1",
    "vp9": "VP9",
    "vp8": "VP8",
    "mjpeg": "MJPEG",
    "aac": "AAC",
    "ac3": "AC-3",
    "mp3": "MP3",
    "flac": "FLAC",
    "alac": "ALAC",
    "opus": "Opus",
    "vorbis": "Vorbis",
    "pcm_s16le": "PCM 16",
    "pcm_s24le": "PCM 24",
    "pcm_s16be": "PCM 16",
    "pcm_s24be": "PCM 24",
    "pcm_s32le": "PCM 32",
    "pcm_f32le": "PCM 32f",
    "wmv3": "WMV",
    "vc1": "VC-1",
    "cfhd": "CineForm",
    "rawvideo": "Raw",
}


def pretty_codec(c: str) -> str:
    return _PRETTY.get(c, c.upper() if len(c) <= 5 else c)


def fmt_duration(sec: float) -> str:
    s = round(sec)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _float(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


STANDARD_RATES = ("24000/1001", "24/1", "25/1", "30000/1001", "30/1", "48/1", "50/1", "60000/1001", "60/1")


def nominal_rate(*candidates: str) -> str:
    """Pick a sensible fixed frame rate (for timecode) from ffprobe's avg/r rates."""
    vals = [(c, _fps(c)) for c in candidates if c and _fps(c) > 0]
    for _c, f in vals:  # an exact standard rate wins
        for std in STANDARD_RATES:
            if abs(_fps(std) - f) / _fps(std) < 0.0005:
                return std
    if vals:  # otherwise snap the first usable one to the nearest standard
        f = vals[0][1]
        return min(STANDARD_RATES, key=lambda std: abs(_fps(std) - f))
    return ""


def tc_add(tc: str, seconds: float, rate: str) -> str:
    """Timecode + seconds (handles drop-frame ';' at 29.97/59.94)."""
    try:
        sep_df = ";" in tc
        parts = [int(x) for x in tc.replace(";", ":").replace(".", ":").split(":")]
        h, m, s, f = parts if len(parts) == 4 else (*parts, 0)
        fps = _fps(rate)
        nom = round(fps)
        if nom <= 0:
            return tc
        drop = (nom // 30) * 2 if sep_df and nom in (30, 60) else 0
        total_min = h * 60 + m
        frames = ((total_min * 60 + s) * nom + f) - drop * (total_min - total_min // 10)
        frames += math.ceil(seconds * fps - 1e-3)  # ffmpeg keeps the first frame at/after the cut
        if drop:
            per10 = nom * 600 - drop * 9
            per1 = nom * 60 - drop
            d, r = divmod(frames, per10)
            frames += drop * 9 * d + (drop * ((r - drop) // per1) if r > drop else 0)
        ff = frames % nom
        total_s = frames // nom
        sep = ";" if drop else ":"
        return f"{(total_s // 3600) % 24:02d}:{(total_s // 60) % 60:02d}:{total_s % 60:02d}{sep}{ff:02d}"
    except (ValueError, TypeError):
        return tc


def tc_double_frames(tc: str) -> str:
    """29.97 timecode -> the same moment at 59.94 (frames field doubled)."""
    try:
        head, ff = tc[:-2], int(tc[-2:])
        return f"{head}{ff * 2:02d}"
    except ValueError:
        return tc


def _fps(rate: str) -> float:
    try:
        if "/" in rate:
            n, d = rate.split("/")
            return float(n) / float(d) if float(d) else 0.0
        return float(rate)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _bits_from_audio(s: dict) -> int:
    raw = s.get("bits_per_raw_sample") or s.get("bits_per_sample")
    try:
        b = int(raw)
        if b > 0:
            return b
    except (TypeError, ValueError):
        pass
    fmt = s.get("sample_fmt", "")
    if fmt.startswith("s16"):
        return 16
    if fmt.startswith("u8"):
        return 8
    return 24


def _bit_depth(pix_fmt: str, s: dict) -> int:
    try:
        b = int(s.get("bits_per_raw_sample") or 0)
        if b:
            return b
    except ValueError:
        pass
    for tag, d in (("16", 16), ("12", 12), ("10", 10), ("p010", 10), ("p016", 16)):
        if tag in pix_fmt:
            return d
    return 8


def _sar(value: str) -> float:
    """'4:3' -> 1.333. Missing, '0:1' or nonsense -> 1 (square pixels)."""
    try:
        num, den = (float(x) for x in value.split(":"))
    except ValueError:
        return 1.0
    return num / den if num > 0 and den > 0 and 0.2 < num / den < 5 else 1.0


def _parse_time(value: str) -> datetime | None:
    """ISO date from a metadata tag; None for empty or placeholder dates (1904/1970 = 'not set')."""
    if not value:
        return None
    try:
        t = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.year > 1980 else None


def _shot_time(fmt_tags: dict, stream_tags: list[dict]) -> datetime | None:
    """When the clip was shot. Prefer Apple's tag (local time with its time zone), then the
    usual UTC creation_time on the file, then on any stream."""
    for tags in (fmt_tags, *stream_tags):
        t = _parse_time(tags.get("com.apple.quicktime.creationdate", ""))
        if t:
            return t
    for tags in (fmt_tags, *stream_tags):
        t = _parse_time(tags.get("creation_time", ""))
        if t:
            return t
    return None


def probe(path: str | Path, as_media: bool = False) -> MediaInfo:
    path = str(path)
    kind = kind_from_ext(path)
    if kind == "photo" and not as_media:
        return probe_photo(path)
    if as_media:
        kind = "unknown"
    caps = capabilities()
    info = MediaInfo(kind=kind)
    if not caps.ffprobe:
        info.error = "ffprobe not found"
        return info
    rc, out = run_quiet(
        [caps.ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        timeout=60,
    )
    try:
        data = json.loads(out[out.index("{") :]) if "{" in out else {}
    except ValueError:
        data = {}
    if rc != 0 and not data:
        last = out.strip().splitlines()[-1] if out.strip() else ""
        if "invalid data" in last.lower():
            info.error = "Not a video, audio or photo file Listo can read."
        else:
            info.error = (last.split(": ", 1)[-1] if last else "") or "Couldn't read this file."
        info.kind = "unknown"
        return info

    fmt = data.get("format", {}) or {}
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    try:
        info.duration = float(fmt.get("duration") or 0)
    except ValueError:
        info.duration = 0.0
    info.timecode = tags.get("timecode", "")
    info.created = _shot_time(
        tags, [{k.lower(): v for k, v in (st.get("tags") or {}).items()} for st in data.get("streams", [])]
    )

    video = None
    for s in data.get("streams", []):
        st = s.get("codec_type")
        disp = s.get("disposition") or {}
        stags = {k.lower(): v for k, v in (s.get("tags") or {}).items()}
        if not info.timecode and stags.get("timecode"):
            info.timecode = stags["timecode"]
        if st == "video" and video is None and not disp.get("attached_pic"):
            video = s
        elif st == "audio":
            info.audio.append(
                AudioTrack(
                    index=int(s.get("index", 0)),
                    codec=s.get("codec_name", ""),
                    channels=int(s.get("channels") or 0),
                    sample_rate=int(s.get("sample_rate") or 0),
                    bits=_bits_from_audio(s),
                    duration=_float(s.get("duration")),
                )
            )
        elif st == "data" and stags.get("timecode") and not info.timecode:
            info.timecode = stags["timecode"]

    if video is not None:
        info.kind = "video"
        info.video_index = int(video.get("index", 0))
        info.width = int(video.get("width") or 0)
        info.height = int(video.get("height") or 0)
        info.vcodec = video.get("codec_name", "")
        info.pix_fmt = video.get("pix_fmt", "") or ""
        info.bit_depth = _bit_depth(info.pix_fmt, video)
        info.fps = _fps(video.get("avg_frame_rate", "")) or _fps(video.get("r_frame_rate", ""))
        # avg first: interlaced AVCHD often reports the *field* rate as r_frame_rate
        info.rate = nominal_rate(video.get("avg_frame_rate", ""), video.get("r_frame_rate", ""))
        info.field_order = (video.get("field_order") or "").lower()
        info.interlaced = info.field_order in ("tt", "bb", "tb", "bt")
        info.color_transfer = video.get("color_transfer", "") or ""
        info.color_primaries = video.get("color_primaries", "") or ""
        info.color_space = video.get("color_space", "") or ""
        if not info.duration:
            try:
                info.duration = float(video.get("duration") or 0)
            except ValueError:
                pass
        # Phone footage stores rotation; ffmpeg auto-rotates, so report the visual size.
        rot = 0
        for sd in video.get("side_data_list", []) or []:
            if "rotation" in sd:
                try:
                    rot = abs(int(float(sd["rotation"])))
                except ValueError:
                    pass
        info.sar = _sar(video.get("sample_aspect_ratio", ""))
        moi = find_moi(path)
        if moi:  # JVC camcorders: the .MOI knows the real date and shape (the MPEG header often doesn't)
            m = read_moi(moi)
            if m.recorded and not info.created:
                info.created = m.recorded
            if m.widescreen is not None and info.width and info.height:
                info.sar = (16 / 9 if m.widescreen else 4 / 3) / (info.width / info.height)
        if rot in (90, 270):
            info.width, info.height = info.height, info.width
            info.sar = 1 / info.sar
    elif info.audio:
        info.kind = "audio"
    else:
        info.kind = "unknown"
        info.error = "No video or audio found in this file"
    return info


def probe_photo(path: str) -> MediaInfo:
    info = MediaInfo(kind="photo")
    try:
        from . import photo

        w, h, created = photo.peek(path)
        info.width, info.height, info.created = w, h, created
    except Exception as e:
        info.error = f"Couldn't read this photo ({e.__class__.__name__}: {e})"
    return info


def file_date(path: str | Path, info: MediaInfo | None = None) -> datetime:
    """Best 'when was this shot' date, as the time on the wall where it was shot (no time zone).

    Embedded creation time first: Apple's tag already carries the local zone; a plain UTC tag is
    shown in this computer's zone (the best guess). Otherwise the file's own dates."""
    if info and info.created:
        t = info.created
        try:
            if t.tzinfo is not None and t.utcoffset() == timedelta(0):
                t = t.astimezone()  # UTC only: assume it was shot in this computer's zone
        except (ValueError, OSError):
            pass
        return t.replace(tzinfo=None)
    st = os.stat(path)
    ts = getattr(st, "st_birthtime", None) or st.st_mtime
    return datetime.fromtimestamp(ts)
