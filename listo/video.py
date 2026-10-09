"""Turn (file, settings) into an ffmpeg command line."""
from __future__ import annotations

from dataclasses import dataclass, field

from .presets import AUDIO_BY_KEY, VIDEO_BY_KEY, Settings
from .probe import MediaInfo
from .tools import Capabilities


class PlanError(Exception):
    """A readable reason this file can't be converted with these settings."""


@dataclass
class Plan:
    args: list[str]
    muxer: str
    notes: list[str] = field(default_factory=list)


H264_CRF = {"high": 18, "standard": 21, "small": 24}
HEVC_CRF = {"high": 20, "standard": 23, "small": 26}
AV1_CRF = {"high": 26, "standard": 32, "small": 38}
VP9_CRF = {"high": 26, "standard": 32, "small": 37}
# Hardware encoders: bits per pixel per frame -> target bitrate.
HW_BPP = {"high": 0.16, "standard": 0.10, "small": 0.06}

MOV_SAFE_AUDIO = {"pcm_s16le", "pcm_s24le", "pcm_s16be", "pcm_s24be", "pcm_f32le", "aac", "alac"}


def preset_available(key: str, caps: Capabilities) -> bool:
    return all(caps.has_encoder(e) for e in VIDEO_BY_KEY[key].needs)


def _pcm_for(info: MediaInfo, little_endian: bool = True) -> str:
    bits = max((a.bits for a in info.audio), default=24)
    width = "16" if bits <= 16 else "24"
    return f"pcm_s{width}{'le' if little_endian else 'be'}"


def _input_args(src: str) -> list[str]:
    return [
        "-hide_banner", "-nostdin", "-y", "-nostats", "-progress", "pipe:1",
        "-fflags", "+genpts", "-probesize", "100M", "-analyzeduration", "100M",
        "-i", src,
    ]


def _audio_only(src: str, out: str, info: MediaInfo, s: Settings, caps: Capabilities) -> Plan:
    if not info.audio:
        raise PlanError("This file has no audio to pull out.")
    fmt = AUDIO_BY_KEY[s.audio_format]
    if fmt.needs and not caps.has_encoder(fmt.needs):
        raise PlanError(f"This copy of ffmpeg can't write {fmt.title}.")
    args = _input_args(src) + ["-map", f"0:{info.audio[0].index}", "-vn", "-c:a", fmt.codec, *fmt.extra]
    if fmt.key in ("mp3", "aac") and info.audio[0].channels not in (1, 2):
        args += ["-ac", "2"]
    args += ["-map_metadata", "0", "-f", fmt.muxer, out]
    notes = []
    if len(info.audio) > 1:
        notes.append("Only the first audio track was exported.")
    return Plan(args, fmt.muxer, notes)


def build(src: str, out: str, info: MediaInfo, s: Settings, caps: Capabilities) -> Plan:
    if info.kind == "audio" or (info.kind == "video" and s.video_preset == "audio"):
        return _audio_only(src, out, info, s, caps)
    if info.kind != "video" or info.video_index is None:
        raise PlanError(info.error or "No video found in this file.")

    p = VIDEO_BY_KEY[s.video_preset]
    missing = [e for e in p.needs if not caps.has_encoder(e)]
    if missing:
        raise PlanError(f"This copy of ffmpeg can't make {p.title} (missing {', '.join(missing)}).")

    variant = s.variant_for(p.key)
    notes: list[str] = []
    args = _input_args(src) + ["-map", f"0:{info.video_index}"]

    # ---- audio track selection
    tracks = info.audio if (p.edit_format and s.keep_all_audio) else info.audio[:1]
    if p.key == "gif":
        tracks = []
    for a in tracks:
        args += ["-map", f"0:{a.index}"]

    # ---- rewrap: copy the picture untouched
    if p.key == "rewrap" and info.vcodec in ("vp8", "vp9", "av1"):
        raise PlanError(f"{info.vcodec.upper()} video can't be rewrapped into a .mov — pick H.264, HEVC or ProRes instead.")
    if p.key == "dnxhr" and (info.width < 256 or info.height < 120):
        raise PlanError("DNxHR needs video at least 256×120 — pick ProRes or H.264 for tiny clips.")
    if p.key == "av1" and (info.width < 64 or info.height < 64):
        raise PlanError("AV1 needs video at least 64×64 — pick H.264 for tiny clips.")
    if p.key == "rewrap":
        args += ["-c:v", "copy"]
        if info.vcodec == "hevc":
            args += ["-tag:v", "hvc1"]
        if tracks:
            if all(a.codec in MOV_SAFE_AUDIO for a in tracks):
                args += ["-c:a", "copy"]
            else:
                args += ["-c:a", _pcm_for(info)]
        if info.interlaced:
            notes.append("Still interlaced — Rewrap doesn't change the picture.")
        if info.timecode:
            args += ["-timecode", info.timecode]
        args += ["-map_metadata", "0", "-f", "mov", out]
        return Plan(args, "mov", notes)

    # ---- picture filters
    vf: list[str] = []
    if info.interlaced and s.deinterlace != "off":
        mode = "send_field" if s.deinterlace == "smooth" else "send_frame"
        if caps.has_filter("bwdif"):
            vf.append(f"bwdif=mode={mode}:parity=auto:deint=all")
        elif caps.has_filter("yadif"):
            vf.append(f"yadif=mode={mode}:parity=auto:deint=all")
        notes.append("Deinterlaced" + (" to double frame rate." if mode == "send_field" else "."))

    tonemap = info.hdr and p.key in ("h264", "gif", "webm")
    if tonemap:
        if caps.has_filter("zscale") and caps.has_filter("tonemap"):
            vf.append(
                "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
                "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
            )
            notes.append(f"{info.hdr_label} converted to standard range so colors look right.")
        else:
            notes.append(f"{info.hdr_label} source — colors may look flat (tone-mapping unavailable).")

    if p.key == "proxy":
        vf.append("scale=trunc(iw/4)*2:trunc(ih/4)*2")
    elif p.key == "gif":
        width = int(variant)
        if info.duration > 30:
            args += ["-t", "30"]
            notes.append("GIFs are capped at 30 seconds.")
        vf.append(f"fps=15,scale='min({width},iw)':-2:flags=lanczos")
    elif s.video_resize == "half":
        vf.append("scale=trunc(iw/4)*2:trunc(ih/4)*2")
    elif s.video_resize != "orig":
        target = int(s.video_resize)
        if info.height > target:
            vf.append(f"scale=-2:{target}:flags=lanczos")
    # 4:2:0 encoders need even dimensions (screen recordings and crops often aren't).
    if p.key not in ("gif",):
        vf.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")

    ten_bit_hdr = info.hdr and p.key in ("hevc", "av1")
    hw_enc = ""
    if p.hw_codec and s.hardware and not ten_bit_hdr:
        hw_enc = caps.hw.get(p.hw_codec, "")

    from .naming import output_size

    out_size = output_size(info, s, "video")
    vargs: list[str] = []
    if p.key == "prores":
        pix = "yuva444p10le" if variant == "4" else "yuv422p10le"
        vargs = ["-c:v", "prores_ks", "-profile:v", variant, "-vendor", "apl0", "-pix_fmt", pix]
    elif p.key == "proxy":
        vargs = ["-c:v", "prores_ks", "-profile:v", "0", "-vendor", "apl0", "-pix_fmt", "yuv422p10le"]
    elif p.key == "dnxhr":
        pix = {"dnxhr_hqx": "yuv422p10le", "dnxhr_444": "yuv444p10le"}.get(variant, "yuv422p")
        vargs = ["-c:v", "dnxhd", "-profile:v", variant, "-pix_fmt", pix]
    elif p.key == "h264":
        if hw_enc:
            vargs = ["-c:v", hw_enc, *_hw_rate(hw_enc, info, variant, out_size), "-pix_fmt", "yuv420p"]
            notes.append("Encoded with hardware acceleration.")
        else:
            vargs = ["-c:v", "libx264", "-preset", "medium", "-crf", str(H264_CRF[variant]),
                     "-profile:v", "high", "-pix_fmt", "yuv420p"]
    elif p.key == "hevc":
        pix = "yuv420p10le" if (info.bit_depth > 8 or info.hdr) else "yuv420p"
        if hw_enc:
            hw_pix = "p010le" if pix.endswith("10le") else "yuv420p"
            vargs = ["-c:v", hw_enc, *_hw_rate(hw_enc, info, variant, out_size), "-pix_fmt", hw_pix, "-tag:v", "hvc1"]
            notes.append("Encoded with hardware acceleration.")
        else:
            vargs = ["-c:v", "libx265", "-preset", "medium", "-crf", str(HEVC_CRF[variant]),
                     "-pix_fmt", pix, "-tag:v", "hvc1", "-x265-params", "log-level=error"]
    elif p.key == "av1":
        pix = "yuv420p10le" if (info.bit_depth > 8 or info.hdr) else "yuv420p"
        vargs = ["-c:v", "libsvtav1", "-preset", "8", "-crf", str(AV1_CRF[variant]), "-pix_fmt", pix]
    elif p.key == "webm":
        vargs = ["-c:v", "libvpx-vp9", "-crf", str(VP9_CRF[variant]), "-b:v", "0", "-row-mt", "1",
                 "-deadline", "good", "-cpu-used", "4", "-pix_fmt", "yuv420p"]
    elif p.key == "gif":
        vf[-1] += ",split[a][b];[a]palettegen=stats_mode=diff[pal];[b][pal]paletteuse=dither=bayer:bayer_scale=4"
        vargs = ["-loop", "0"]

    if ten_bit_hdr:
        vargs += ["-color_primaries", info.color_primaries or "bt2020",
                  "-color_trc", info.color_transfer, "-colorspace", info.color_space or "bt2020nc"]
        notes.append(f"Kept {info.hdr_label}.")
    elif tonemap and caps.has_filter("zscale"):
        vargs += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]

    if vf:
        args += ["-vf", ",".join(vf)]
    args += vargs

    # ---- audio codec
    if tracks:
        if p.edit_format:
            args += ["-c:a", _pcm_for(info)]
        elif p.key == "webm":
            args += ["-c:a", "libopus" if caps.has_encoder("libopus") else "libvorbis", "-b:a", "160k"]
        else:
            args += ["-c:a", "aac", "-b:a", "256k"]
        if not p.edit_format and tracks[0].channels != 2:
            # Share formats: stereo plays everywhere (and Opus/AAC reject odd camera layouts).
            args += ["-ac", "2" if tracks[0].channels != 1 else "1"]
        if len(info.audio) > len(tracks) and p.key != "gif":
            notes.append(f"Kept the first of {len(info.audio)} audio tracks.")
    else:
        args += ["-an"]

    muxer = {"mov": "mov", "mp4": "mp4", "webm": "webm", "gif": "gif"}[p.ext]
    if muxer in ("mov", "mp4") and info.timecode:
        args += ["-timecode", info.timecode]
    if muxer == "mp4":
        args += ["-movflags", "+faststart"]
    args += ["-map_metadata", "0", "-f", muxer, out]
    return Plan(args, muxer, notes)


def _hw_rate(enc: str, info: MediaInfo, variant: str, size: tuple[int, int]) -> list[str]:
    fps = info.fps or 30.0
    w, h = size if size[0] else (info.width, info.height)
    bitrate = int(max(w * h, 640 * 360) * min(fps, 120) * HW_BPP[variant])
    bitrate = max(bitrate, 1_500_000)
    if enc.endswith("_nvenc"):
        cq = {"high": 19, "standard": 23, "small": 28}[variant]
        return ["-preset", "p5", "-rc", "vbr", "-cq", str(cq), "-b:v", str(bitrate),
                "-maxrate", str(int(bitrate * 1.5))]
    return ["-b:v", str(bitrate), "-maxrate", str(int(bitrate * 1.5))]
