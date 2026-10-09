"""Figure out what a file is: video, audio, photo — and the details that matter."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .tools import capabilities, run_quiet

VIDEO_EXTS = {
    "mov", "mp4", "m4v", "mts", "m2ts", "m2t", "ts", "mod", "tod", "mpg", "mpeg",
    "vob", "avi", "mkv", "webm", "mxf", "dv", "flv", "wmv", "asf", "3gp", "3g2",
    "ogv", "f4v", "y4m", "mjpeg", "hevc", "h264", "264", "265", "divx", "xvid",
}
AUDIO_EXTS = {
    "wav", "aif", "aiff", "aifc", "flac", "mp3", "m4a", "aac", "ogg", "opus", "wma",
    "caf", "ac3", "bwf", "w64", "alac", "amr",
}
RAW_EXTS = {
    "cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2", "dng", "raf", "orf", "rw2",
    "pef", "srw", "3fr", "iiq", "erf", "kdc", "mrw", "x3f", "rwl", "mos",
}
IMAGE_EXTS = {
    "jpg", "jpeg", "jpe", "png", "tif", "tiff", "webp", "heic", "heif", "hif", "avif",
    "bmp", "gif", "tga", "jp2", "psd",
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


def ext_of(path: str | Path) -> str:
    return Path(path).suffix.lower().lstrip(".")


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
    error: str = ""

    @property
    def hdr(self) -> bool:
        return self.color_transfer in ("smpte2084", "arib-std-b67")

    @property
    def hdr_label(self) -> str:
        return {"smpte2084": "HDR PQ", "arib-std-b67": "HDR HLG"}.get(self.color_transfer, "")

    def summary_bits(self) -> list[str]:
        """Short badges for the UI: 1920×1080 · 29.97i · H.264 · 2 audio · 3:24"""
        bits: list[str] = []
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
                bits.append(f"{n} audio tracks" if n > 1 else ({1: "mono", 2: "stereo"}.get(ch, f"{ch}ch audio")))
        if self.duration and self.kind != "photo":
            bits.append(fmt_duration(self.duration))
        return [b for b in bits if b]


_PRETTY = {
    "h264": "H.264", "hevc": "HEVC", "prores": "ProRes", "mpeg2video": "MPEG-2",
    "mpeg4": "MPEG-4", "dvvideo": "DV", "dnxhd": "DNx", "av1": "AV1", "vp9": "VP9",
    "vp8": "VP8", "mjpeg": "MJPEG", "aac": "AAC", "ac3": "AC-3", "mp3": "MP3",
    "flac": "FLAC", "alac": "ALAC", "opus": "Opus", "vorbis": "Vorbis",
    "pcm_s16le": "PCM 16", "pcm_s24le": "PCM 24", "pcm_s16be": "PCM 16",
    "pcm_s24be": "PCM 24", "pcm_s32le": "PCM 32", "pcm_f32le": "PCM 32f",
    "wmv3": "WMV", "vc1": "VC-1", "cfhd": "CineForm", "rawvideo": "Raw",
}


def pretty_codec(c: str) -> str:
    return _PRETTY.get(c, c.upper() if len(c) <= 5 else c)


def fmt_duration(sec: float) -> str:
    s = int(round(sec))
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
    for c, f in vals:  # an exact standard rate wins
        for std in STANDARD_RATES:
            if abs(_fps(std) - f) / _fps(std) < 0.0005:
                return std
    if vals:  # otherwise snap the first usable one to the nearest standard
        f = vals[0][1]
        return min(STANDARD_RATES, key=lambda std: abs(_fps(std) - f))
    return ""


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


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
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
        data = json.loads(out[out.index("{"):]) if "{" in out else {}
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
    info.created = _parse_time(tags.get("creation_time", ""))

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
        if rot in (90, 270):
            info.width, info.height = info.height, info.width
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
    except Exception as e:  # noqa: BLE001 — any decoder error becomes a readable message
        info.error = f"Couldn't read this photo ({e.__class__.__name__}: {e})"
    return info


def file_date(path: str | Path, info: MediaInfo | None = None) -> datetime:
    """Best 'when was this shot' date: embedded creation time, else file dates."""
    if info and info.created:
        try:
            return info.created.astimezone() if info.created.tzinfo else info.created
        except (ValueError, OSError):
            return info.created
    st = os.stat(path)
    ts = getattr(st, "st_birthtime", None) or st.st_mtime
    return datetime.fromtimestamp(ts)
