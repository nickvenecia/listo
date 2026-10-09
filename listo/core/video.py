"""Turn (file, settings) into an ffmpeg command line."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from . import burnin, tape
from .burnin import BurnPlan
from .frame import Area, frame_plan, resized
from .presets import AUDIO_BY_KEY, VIDEO_BY_KEY, Settings
from .probe import MediaInfo, tc_add, tc_double_frames
from .tools import Capabilities


class PlanError(Exception):
    """A readable reason this file can't be converted with these settings."""


@dataclass
class Plan:
    args: list[str]
    muxer: str
    notes: list[str] = field(default_factory=list)
    burn: BurnPlan | None = None  # images for burn-ins; call cleanup() when ffmpeg is done

    def cleanup(self) -> None:
        if self.burn:
            self.burn.cleanup()


H264_CRF = {"high": 18, "standard": 21, "small": 24}
HEVC_CRF = {"high": 20, "standard": 23, "small": 26}
AV1_CRF = {"high": 26, "standard": 32, "small": 38}
VP9_CRF = {"high": 26, "standard": 32, "small": 37}
# Hardware encoders: bits per pixel per frame -> target bitrate.
HW_BPP = {"high": 0.16, "standard": 0.10, "small": 0.06}

MOV_SAFE_AUDIO = {"pcm_s16le", "pcm_s24le", "pcm_s16be", "pcm_s24be", "pcm_f32le", "aac", "alac"}


FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT = FONTS / "Inter-SemiBold.otf"
VHS_FONT = FONTS / "VCR_OSD_Mono.ttf"


def fesc(value: str) -> str:
    """Escape a value for use inside an ffmpeg filter graph (handles Windows paths, quotes, colons)."""
    value = value.replace("\\", "/") if (len(value) > 2 and value[1] == ":") else value
    lvl1 = "".join("\\" + c if c in "\\:'[],;=%" else c for c in value)
    return "".join("\\" + c if c in "\\'[],;" else c for c in lvl1)


def _out_rate(info: MediaInfo, s: Settings, doubled: bool) -> str:
    try:
        r = Fraction(info.rate) if info.rate else Fraction(info.fps).limit_denominator(1001)
    except (ValueError, ZeroDivisionError):
        return ""
    if r <= 0:
        return ""
    r = r * 2 if doubled else r
    return f"{r.numerator}/{r.denominator}"


def lut_filters(s: Settings, caps: Capabilities, notes: list[str]) -> list[str]:
    if not s.lut_path:
        return []
    if not Path(s.lut_path).is_file():
        raise PlanError(f"The LUT file is missing: {s.lut_path}")
    if not caps.has_filter("lut3d"):
        notes.append("LUT skipped — this copy of ffmpeg can't apply LUTs.")
        return []
    notes.append(f"LUT applied: {Path(s.lut_path).name}.")
    return [f"lut3d=file={fesc(s.lut_path)}"]


def burn_plan(
    info: MediaInfo,
    s: Settings,
    frame: tuple[int, int],
    area: Area,
    doubled: bool,
    src: str,
    notes: list[str],
    start_tc: str = "",
    start_s: float = 0.0,
    cues: list | None = None,
    marks: burnin.Marks | None = None,
) -> BurnPlan:
    """Burn-in and caption images for this conversion (drawn by Listo, so any ffmpeg works)."""
    if not s.burns and not cues:
        return BurnPlan()
    if not frame[0] or not frame[1]:
        notes.append("Burn-ins and captions skipped — couldn't read the picture size.")
        return BurnPlan()
    tc, rate = "", None
    if s.burn_timecode:
        r = _out_rate(info, s, doubled)
        if r:
            rate = Fraction(r)
            tc = start_tc or info.timecode or "00:00:00:00"
            if ";" in tc and r not in ("30000/1001", "60000/1001"):
                tc = tc.replace(";", ":")  # drop-frame only exists at 29.97 / 59.94
        else:
            notes.append("Timecode burn-in skipped — frame rate unknown.")
    shot = None
    if s.burns and s.burn_datetime:
        if not info.created:
            notes.append("No recording time inside the clip — the date comes from the file instead.")
        shot = burnin.shot_start(src, info, start_s)
    bp = burnin.plan(info, s, frame, area, src, shot, tc, rate, cues, marks)
    if bp.layers:
        notes.append("Burn-ins added" + (" (VHS style)." if s.burn_style == "vhs" else "."))
    if bp.captions:
        notes.append(f"Captions added ({len(cues or [])}).")
    return bp


@dataclass
class Conform:
    """Every part of a joined video must match exactly (size, frame rate, sound) so the parts can be
    glued without re-encoding. Taken from the first clip; see core.join."""

    width: int = 0
    height: int = 0
    rate: str = ""  # "30000/1001"; empty for sound-only
    sample_rate: int = 48000
    channels: int = 2


def preset_available(key: str, caps: Capabilities) -> bool:
    return all(caps.has_encoder(e) for e in VIDEO_BY_KEY[key].needs)


def _pcm_for(info: MediaInfo, little_endian: bool = True) -> str:
    bits = max((a.bits for a in info.audio), default=24)
    width = "16" if bits <= 16 else "24"
    return f"pcm_s{width}{'le' if little_endian else 'be'}"


def _input_args(src: str, trim: tuple[float, float] | None = None) -> list[str]:
    args = [
        "-hide_banner",
        "-nostdin",
        "-y",
        "-nostats",
        "-progress",
        "pipe:1",
        "-fflags",
        "+genpts",
        "-probesize",
        "100M",
        "-analyzeduration",
        "100M",
    ]
    if trim:
        args += ["-ss", f"{trim[0]:.3f}"]
    args += ["-i", src]
    if trim:
        args += ["-t", f"{max(0.05, trim[1] - trim[0]):.3f}"]
    return args


def _audio_only(
    src: str,
    out: str,
    info: MediaInfo,
    s: Settings,
    caps: Capabilities,
    trim: tuple[float, float] | None = None,
    conform: Conform | None = None,
) -> Plan:
    if not info.audio:
        raise PlanError("This file has no audio to pull out.")
    fmt = AUDIO_BY_KEY[s.audio_format]
    if fmt.needs and not caps.has_encoder(fmt.needs):
        raise PlanError(f"This copy of ffmpeg can't write {fmt.title}.")
    args = [*_input_args(src, trim), "-map", f"0:{info.audio[0].index}", "-vn", "-c:a", fmt.codec, *fmt.extra]
    if conform is not None:
        args += ["-ar", str(conform.sample_rate), "-ac", str(conform.channels)]
    elif fmt.key in ("mp3", "aac") and info.audio[0].channels not in (1, 2):
        args += ["-ac", "2"]
    args += ["-map_metadata", "0", "-f", fmt.muxer, out]
    notes = []
    if len(info.audio) > 1:
        notes.append("Only the first audio track was exported.")
    return Plan(args, fmt.muxer, notes)


def build(
    src: str,
    out: str,
    info: MediaInfo,
    s: Settings,
    caps: Capabilities,
    trim: tuple[float, float] | None = None,
    captions: list | None = None,
    conform: Conform | None = None,
    timecode: str = "",
    glitch_cut: bool = False,
    marks: burnin.Marks | None = None,
) -> Plan:
    """captions: the clip's reviewed cues (on the clip's own timeline); they're shifted for a trim.
    conform: this clip is one part of a joined video and must match the others (rewrap ignores it).
    timecode: where this clip's timecode starts instead of its own (a joined video's running counter)."""
    if info.kind == "audio" or (info.kind == "video" and s.video_preset == "audio"):
        return _audio_only(src, out, info, s, caps, trim, conform)
    if info.kind != "video" or info.video_index is None:
        raise PlanError(info.error or "No video found in this file.")

    p = VIDEO_BY_KEY[s.video_preset]
    missing = [e for e in p.needs if not caps.has_encoder(e)]
    if missing:
        raise PlanError(f"This copy of ffmpeg can't make {p.title} (missing {', '.join(missing)}).")

    variant = s.variant_for(p.key)
    notes: list[str] = []
    args = [*_input_args(src, trim), "-map", f"0:{info.video_index}"]
    # Timecode of the first frame we keep (so trimmed clips still line up in the edit)
    start_tc = info.timecode
    if trim and info.timecode and info.rate:
        start_tc = tc_add(info.timecode, trim[0], info.rate)
    if timecode:
        start_tc = timecode  # already counts from where the (trimmed) clip starts

    # ---- audio track selection
    tracks = info.audio if (p.edit_format and s.keep_all_audio) else info.audio[:1]
    if p.key == "gif":
        tracks = []
    for a in tracks:
        args += ["-map", f"0:{a.index}"]

    # ---- rewrap: copy the picture untouched
    if p.key == "rewrap" and info.vcodec in ("vp8", "vp9", "av1"):
        raise PlanError(
            f"{info.vcodec.upper()} video can't be rewrapped into a .mov — pick H.264, HEVC or ProRes instead."
        )
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
        if s.lut_path or s.burns or s.desqueeze != "1" or s.aspect != "orig":
            notes.append("LUT, burn-ins and reshaping skipped — Rewrap doesn't re-encode.")
        if trim:
            notes.append("Rewrap trims on the nearest keyframe, so the start may be a little early.")
        if start_tc:
            args += ["-timecode", start_tc]
        args += ["-map_metadata", "0", "-f", "mov", out]
        return Plan(args, "mov", notes)

    # ---- picture filters
    from .naming import output_size

    out_size = output_size(info, s, "video")
    vf: list[str] = []
    doubled = False
    if info.interlaced and s.deinterlace != "off":
        doubled = s.deinterlace == "smooth"
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

    # Shape first (desqueeze, crop / bars), so the LUT and burn-ins see the final frame.
    shape_vf, fw, fh, area = frame_plan(info.width, info.height, info.sar, s)
    if doubled and start_tc:
        start_tc = tc_double_frames(start_tc)
    vf += lut_filters(s, caps, notes)
    vf += shape_vf
    if shape_vf:
        bars_only = s.aspect_fit == "matte" and s.desqueeze == "1"
        notes.append(f"Cinema bars added ({s.aspect})." if bars_only else f"Reshaped to {fw}×{fh}.")
    cues = None
    if s.captions and captions:
        from .captions import for_output

        cues = for_output(captions, trim[0] if trim else 0.0, (trim[1] - trim[0]) if trim else None)
    burn = burn_plan(
        info, s, (fw, fh) if p.key == "gif" else out_size, area, doubled, src, notes, start_tc,
        trim[0] if trim else 0.0, cues, marks,
    )  # fmt: skip
    burn_at = len(vf) if p.key == "gif" else -1  # GIF: burn in before the frame-rate drop

    if p.key == "proxy":
        vf.append("scale=trunc(iw/4)*2:trunc(ih/4)*2")
    elif p.key == "gif":
        width = int(variant)
        length = (trim[1] - trim[0]) if trim else info.duration
        if length > 30 and not trim:
            args += ["-t", "30"]
            notes.append("GIFs are capped at 30 seconds — trim the clip to pick the part you want.")
        elif length > 30:
            args[args.index("-t") + 1] = "30.000"
            notes.append("GIFs are capped at 30 seconds.")
        vf.append(f"fps=15,scale='min({width},iw)':-2:flags=lanczos")
    elif s.video_resize != "orig":
        if fw and fh:
            rw, rh = resized(fw, fh, s.video_resize)
            if (rw, rh) != (fw, fh):
                vf.append(f"scale={rw}:{rh}:flags=lanczos")
                if rh * rw > fh * fw:
                    notes.append(f"Upscaled from {fw}×{fh} to {rw}×{rh}.")
        elif s.video_resize == "half":
            vf.append("scale=trunc(iw/4)*2:trunc(ih/4)*2")
        else:
            vf.append(f"scale=-2:{int(s.video_resize)}:flags=lanczos")
    # 4:2:0 encoders need even dimensions (screen recordings and crops often aren't).
    if p.key not in ("gif",):
        vf.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    if burn_at < 0:
        burn_at = len(vf)
    if conform is not None and conform.width and p.key != "gif":
        W, H = conform.width, conform.height
        if out_size != (W, H):
            notes.append(f"Fitted into {W}×{H} to match the first clip.")
        vf.append(
            f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
        )
        if conform.rate:
            if _out_rate(info, s, doubled) != conform.rate:
                notes.append("Frame rate changed to match the first clip.")
            vf.append(f"fps={conform.rate}")

    ten_bit_hdr = info.hdr and p.key in ("hevc", "av1")
    hw_enc = ""
    if p.hw_codec and s.hardware and not ten_bit_hdr:
        hw_enc = caps.hw.get(p.hw_codec, "")

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
            vargs = [
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                str(H264_CRF[variant]),
                "-profile:v",
                "high",
                "-pix_fmt",
                "yuv420p",
            ]
    elif p.key == "hevc":
        pix = "yuv420p10le" if (info.bit_depth > 8 or info.hdr) else "yuv420p"
        if hw_enc:
            hw_pix = "p010le" if pix.endswith("10le") else "yuv420p"
            vargs = [
                "-c:v",
                hw_enc,
                *_hw_rate(hw_enc, info, variant, out_size),
                "-pix_fmt",
                hw_pix,
                "-tag:v",
                "hvc1",
            ]
            notes.append("Encoded with hardware acceleration.")
        else:
            vargs = [
                "-c:v",
                "libx265",
                "-preset",
                "medium",
                "-crf",
                str(HEVC_CRF[variant]),
                "-pix_fmt",
                pix,
                "-tag:v",
                "hvc1",
                "-x265-params",
                "log-level=error",
            ]
    elif p.key == "av1":
        pix = "yuv420p10le" if (info.bit_depth > 8 or info.hdr) else "yuv420p"
        vargs = ["-c:v", "libsvtav1", "-preset", "8", "-crf", str(AV1_CRF[variant]), "-pix_fmt", pix]
    elif p.key == "webm":
        vargs = [
            "-c:v",
            "libvpx-vp9",
            "-crf",
            str(VP9_CRF[variant]),
            "-b:v",
            "0",
            "-row-mt",
            "1",
            "-deadline",
            "good",
            "-cpu-used",
            "4",
            "-pix_fmt",
            "yuv420p",
        ]
    elif p.key == "gif":
        vf[-1] += (
            ",split[a][b];[a]palettegen=stats_mode=diff[pal];[b][pal]paletteuse=dither=bayer:bayer_scale=4"
        )
        vargs = ["-loop", "0"]

    if ten_bit_hdr:
        vargs += [
            "-color_primaries",
            info.color_primaries or "bt2020",
            "-color_trc",
            info.color_transfer,
            "-colorspace",
            info.color_space or "bt2020nc",
        ]
        notes.append(f"Kept {info.hdr_label}.")
    elif tonemap and caps.has_filter("zscale"):
        vargs += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]

    windows = tape.glitch_windows(s, src, info, trim, glitch_cut) if p.key != "gif" else []
    if windows:
        notes.append(f"Tape glitches: {len(windows)}.")
    if not burn.empty or windows:
        if not burn.empty:
            # Burn-in / caption images are extra inputs, so the picture goes through a filter graph.
            first = args.index("-i") + 2
            length = (trim[1] - trim[0]) if trim else info.duration
            args[first:first] = burn.input_args(_out_rate(info, s, doubled) or "25", length)
            # Start the picture's clock at exactly 0 so the burned-in timecode / clock begin on the first
            # frame (MPEG program streams like .MOD / .VOB otherwise keep a start offset after a seek).
            pre, post = ",".join(["setpts=PTS-STARTPTS", *vf[:burn_at]]), ",".join(vf[burn_at:])
            graph = f"[0:{info.video_index}]{pre}[bin];" + burn.graph(1, "bin", "bout" if post else "vout")
            if post:
                graph += f";[bout]{post}[vout]"
        else:
            graph = f"[0:{info.video_index}]" + ",".join(["setpts=PTS-STARTPTS", *vf]) + "[vout]"
        if windows:  # tape glitches go over everything (they happen to the whole picture on tape)
            cut_at = graph.rfind("[vout]")
            graph = graph[:cut_at] + "[gin]" + graph[cut_at + len("[vout]") :]
            size = (conform.width, conform.height) if conform and conform.width else out_size
            graph += ";" + tape.video_graph(windows, size, "gin", "vout")
        args += ["-filter_complex", graph]
        args[args.index(f"0:{info.video_index}")] = "[vout]"
    elif vf:
        args += ["-vf", ",".join(vf)]
    args += vargs

    # ---- audio codec
    af = []
    if tracks and (not burn.empty or windows):
        af.append("asetpts=PTS-STARTPTS")  # keep in step with the picture (see above)
    if tracks and windows:
        af += tape.audio_filters(windows)
    if af:
        args += ["-af", ",".join(af)]
    if conform is not None and not tracks and p.key != "gif":
        # A silent clip in a joined video still needs a sound track, or the parts won't line up.
        last_i = max(i for i, a in enumerate(args) if a == "-i")
        index = args.count("-i")
        length = (trim[1] - trim[0]) if trim else info.duration
        args[last_i + 2 : last_i + 2] = [
            "-f", "lavfi", "-t", f"{max(0.05, length):.3f}",
            "-i", f"anullsrc=r={conform.sample_rate}:cl={'mono' if conform.channels == 1 else 'stereo'}",
        ]  # fmt: skip
        args += ["-map", f"{index}:a"]
        tracks = [None]  # (codec choice below)
    if tracks:
        if p.edit_format:
            args += ["-c:a", "pcm_s24le" if conform is not None else _pcm_for(info)]
        elif p.key == "webm":
            args += ["-c:a", "libopus" if caps.has_encoder("libopus") else "libvorbis", "-b:a", "160k"]
        else:
            args += ["-c:a", "aac", "-b:a", "256k"]
        if conform is not None:
            args += ["-ar", str(conform.sample_rate), "-ac", str(conform.channels)]
        elif not p.edit_format and tracks[0].channels != 2:
            # Share formats: stereo plays everywhere (and Opus/AAC reject odd camera layouts).
            args += ["-ac", "2" if tracks[0].channels != 1 else "1"]
        if len(info.audio) > len(tracks) and p.key != "gif":
            notes.append(f"Kept the first of {len(info.audio)} audio tracks.")
    else:
        args += ["-an"]

    muxer = {"mov": "mov", "mp4": "mp4", "webm": "webm", "gif": "gif"}[p.ext]
    if muxer in ("mov", "mp4") and start_tc:
        args += ["-timecode", start_tc]
    if muxer == "mp4":
        args += ["-movflags", "+faststart"]
    args += ["-map_metadata", "0", "-f", muxer, out]
    return Plan(args, muxer, notes, burn)


def _hw_rate(enc: str, info: MediaInfo, variant: str, size: tuple[int, int]) -> list[str]:
    fps = info.fps or 30.0
    w, h = size if size[0] else (info.width, info.height)
    bitrate = int(max(w * h, 640 * 360) * min(fps, 120) * HW_BPP[variant])
    bitrate = max(bitrate, 1_500_000)
    if enc.endswith("_nvenc"):
        cq = {"high": 19, "standard": 23, "small": 28}[variant]
        return [
            "-preset",
            "p5",
            "-rc",
            "vbr",
            "-cq",
            str(cq),
            "-b:v",
            str(bitrate),
            "-maxrate",
            str(int(bitrate * 1.5)),
        ]
    return ["-b:v", str(bitrate), "-maxrate", str(int(bitrate * 1.5))]


def preview_plan(
    src: str,
    info: MediaInfo,
    s: Settings,
    caps: Capabilities,
    at: float,
    out_png: str,
    captions: list | None = None,
) -> tuple[list[str], Plan]:
    """ffmpeg args that save ONE frame at `at` seconds, with exactly the picture steps the real
    conversion would use (LUT, frame, size, burn-ins). Call plan.cleanup() afterwards."""
    if s.video_preset in ("gif", "audio"):
        s = s.copy()
        s.video_preset = "h264"  # same look; a GIF's palette step needs the whole clip
    length = max(info.duration, 0.1)
    # Stay half a second clear of the end: camera files often hold sound past their last picture
    # (MPEG program streams start the picture later), so "the last moment" can have no frame.
    at = min(max(0.0, at), max(0.0, length - min(0.5, length / 4)))
    plan = build(src, out_png, info, s, caps, trim=(at, min(length, at + 1.0)), captions=captions)
    a = plan.args
    first_map = a.index("-map")
    args = [*a[:first_map], "-map", a[first_map + 1]]
    for flag in ("-filter_complex", "-vf"):
        if flag in a:
            args += [flag, a[a.index(flag) + 1]]
            break
    args += ["-frames:v", "1", "-an", "-update", "1", "-f", "image2", "-c:v", "png", "-y", out_png]
    return args, plan


def original_frame_args(src: str, info: MediaInfo, at: float, out_png: str) -> list[str]:
    """One untouched frame at `at` seconds (pixels made square so it looks like the real thing)."""
    vf = "scale='trunc(iw*sar/2)*2':ih,setsar=1" if abs(info.sar - 1) > 1e-3 else "null"
    return [
        "-hide_banner", "-v", "error", "-ss", f"{max(0.0, at):.3f}", "-i", src,
        "-map", f"0:{info.video_index}", "-vf", vf, "-frames:v", "1", "-an",
        "-update", "1", "-f", "image2", "-c:v", "png", "-y", out_png,
    ]  # fmt: skip
