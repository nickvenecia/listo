"""Tape effects, part of the VHS Camcorder Look: a screen at the start and end (VCR blue, black,
color bars & tone, or any color), tracking glitches at joined cuts, and random glitches through a
video. All drawn by Listo's own ffmpeg; all off unless switched on, and only with the VHS look.

A glitch is a third of a second of lost tracking, modelled on ntsc-rs (an open-source VHS
emulator): the lines wave sideways, a band of torn lines and snow rolls up the picture, the bottom
bends (head switching), the picture hops, color slips and drops out, the sound flutters and
crunches. Random glitch moments come from the clip's name, so the preview and the finished file
glitch at exactly the same moments.

The screen is made as its own short piece with the same encoder settings as the video
(make_blue), then joined on without re-encoding (join.concat), like the parts of a joined video.
"""

from __future__ import annotations

import random
import re
import subprocess
import tempfile
import zlib
from pathlib import Path

from listo.core.presets import Settings
from listo.core.probe import MediaInfo
from listo.core.tools import Capabilities, popen_kwargs

BLUE = "0x1E2EE6"  # a VCR's blue screen
BLUE_SECONDS = 2.0
CUT_GLITCH_S = 0.33  # the glitch at each cut of a joined video (about 10 frames: the tape catching)
GLITCH_EVERY = {"rare": 90.0, "often": 30.0}  # random glitches: about one per this many seconds
NO_EFFECTS = ("rewrap", "gif", "audio")  # copies, palettes and sound-only can't take them


def applies(s: Settings) -> bool:
    """Tape effects belong to the VHS Camcorder Look (burn-ins on, VHS style) and to formats that
    re-encode the picture."""
    return s.video_preset not in NO_EFFECTS and s.burns and s.burn_style == "vhs"


def wants_blue(s: Settings) -> bool:
    return s.tape_blue and applies(s)


def glitch_windows(
    s: Settings, src: str, info: MediaInfo, trim: tuple[float, float] | None, cut: bool = False
) -> list[tuple[float, float]]:
    """When the picture glitches, in seconds of the output (after a trim). cut = this clip follows
    another one in a joined video."""
    if not applies(s):
        return []
    start = trim[0] if trim else 0.0
    length = (trim[1] - trim[0]) if trim else info.duration
    out: list[tuple[float, float]] = []
    if cut and s.tape_glitches != "off":  # every glitch setting also glitches at joined cuts
        out.append((0.0, min(CUT_GLITCH_S, max(0.05, length))))
    every = GLITCH_EVERY.get(s.tape_glitches)
    if every and info.duration > 0:
        rng = random.Random(zlib.crc32(Path(src).name.encode("utf-8")))  # noqa: S311 — looks, not security
        t = rng.uniform(every * 0.3, every)
        while t < info.duration:
            d = rng.uniform(0.25, 0.5)
            a, b = t - start, t + d - start
            if b > 0 and a < length:
                out.append((max(0.0, a), min(length, b)))
            t += rng.uniform(every * 0.5, every * 1.5)
    return out


def _when(windows: list[tuple[float, float]]) -> str:
    return "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in windows)


def _hash(x: str) -> str:
    """A steady 0..1 random number from x (the same frame and row always give the same value)."""
    return f"mod(abs(sin({x}))*43758.5453,1)"


def _glitch_geq(a: float, b: float, n: int, top: int, seed: int = 0) -> str:
    """One tracking glitch from a to b, after ntsc-rs (an open-source VHS emulator) and real tape:
    the lines drift sideways in an uneven wave and jitter one by one; a band of lost tracking rolls
    through the picture, its lines torn sideways and washed with streaky analog noise (every line
    different, ragged edges); a few lines carry a bright streak of snow that fades along the line;
    the bottom lines bend (head switching); sometimes the picture hops; color slips right and drops
    out on some lines. It hits at once and settles (env). Every glitch is different (its own
    shape, speed, band and strength from `seed` + which glitch it is); the same file always glitches
    the same way, so the preview matches the result."""
    rng = random.Random(seed * 7919 + n * 104729 + round(a * 1000))  # noqa: S311 — looks, not security
    r = rng.uniform
    s = r(0, 1000)
    strength = r(0.7, 1.0)
    wave = r(0.002, 0.0045)
    f1, f2, f3 = r(18, 45), r(60, 120), r(150, 260)
    v1, v2, v3 = r(8, 25), r(15, 40), r(30, 60)
    p1, p2 = r(0, 6.3), r(0, 6.3)
    band_at, band_h = r(0.3, 1.0), r(0.05, 0.14)
    band_speed = r(0.4, 1.8) * (-1 if rng.random() < 0.7 else 1)  # mostly rolls up
    tear = r(0.025, 0.06)
    bend = r(0.02, 0.045)
    hop = r(0.008, 0.02) if rng.random() < 0.6 else 0.0
    mid = (top + 1) // 2
    d = max(b - a, 0.01)
    common = (
        f"st(0,clip((T-{a:.3f})/{d:.3f},0,1));"
        f"st(0,{strength:.2f}*min(1,ld(0)*6)*pow(1-ld(0),0.6));"  # strength: hits at once, then settles
        "st(1,Y/H);"  # how far down the picture (0 top, 1 bottom; W and H are this plane's size)
        "st(2,floor(Y/SH));"  # the picture line
        f"st(3,{_hash(f'ld(2)*12.9898+N*78.233+{s:.2f}')});"  # this line's random number
        f"st(4,mod({band_at:.3f}+(T-{a:.3f})*{band_speed:.3f},1.3)-0.15);"  # where the band is
        f"st(4,between(ld(1),ld(4)-0.012*ld(3),ld(4)+{band_h:.3f}"
        f"+0.012*{_hash(f'ld(2)*3.71+N*1.3+{s:.2f}')}));"  # inside it (ragged edges)?
        f"st(6,ld(0)*W*({wave:.4f}*(0.6*sin(ld(1)*{f1:.1f}+T*{v1:.1f}+{p1:.2f})"  # uneven sideways drift
        f"+0.3*sin(ld(1)*{f2:.1f}-T*{v2:.1f}+{p2:.2f})+0.1*sin(ld(1)*{f3:.1f}+T*{v3:.1f}))"
        "+0.0025*(ld(3)-0.5)"  # every line a little unsteady
        f"+ld(4)*{tear:.3f}*(ld(3)-0.3)*(0.4+ld(3))"  # torn lines in the band
        f"+{bend:.3f}*pow(max(0,ld(1)-0.955)/0.045,1.5)*(0.7+0.6*ld(3))));"  # head switching
        f"st(7,H*{hop:.3f}*ld(0)*gt({_hash(f'N*91.7+{s:.2f}')},0.8));"  # the picture hops
        # a streak of snow on this line? (more in the band and at the bottom): length 8, start 5
        f"st(5,{_hash(f'ld(2)*7.77+N*1.913+{s:.2f}')});"
        "st(8,gt(ld(0)*(0.03+0.45*ld(4)+0.2*gt(ld(1),0.95)),ld(5))*W*(0.004+0.035*ld(3)*ld(3)));"
        f"st(5,W*{_hash(f'ld(2)*3.33+N*7.1+{s:.2f}')})"
    )
    # The per-line numbers are worked out once per line, not for every pixel (vars 0-8 keep them;
    # 9 remembers which line of which frame they belong to): about 4x faster.
    once = "if(not(eq(ld(9),Y+N*65536+1)),st(9,Y+N*65536+1);" + common
    # How much of a band line is noise: lines differ a lot (some clean but torn, some all noise).
    wash = "min(0.9,ld(4)*ld(0)*1.2*pow(ld(3),1.3))"
    # The band's noise: value noise along the line (random every 4 pixels, blended), so it streaks
    # like analog noise instead of making a pattern; every line, every frame its own.
    g = f"floor(X/4)*17.13+ld(2)*311.7+N*3.1+{s:.2f}"
    g1 = f"(floor(X/4)+1)*17.13+ld(2)*311.7+N*3.1+{s:.2f}"
    fr = "(X/4-floor(X/4))"
    noise = f"({_hash(g)}*(1-{fr})+{_hash(g1)}*{fr})"
    luma = (
        once
        + ");"
        # a shifted line leaves the blanking (black) behind at the left edge, like a real VCR
        + f"clip(if(lt(X-ld(6),0),{round(16 * top / 255)},lum(X-ld(6),Y+ld(7)))*(1-{wash})"
        + f"+if(ld(4),{wash}*{top}*(0.15+0.85*{noise}*(0.65+0.35*sin(X/W*(9+15*ld(3))+N*0.7))),0)"
        # snow streak: bright where it starts, fading along the line
        + f"+if(ld(8)*between(X,ld(5),ld(5)+ld(8)),{top}*0.8*pow(1-(X-ld(5))/(ld(8)+1),2),0)"
        + f",0,{top})"
    )

    def chroma(plane: str) -> str:
        return (
            once
            + f";st(8,gt(0.12*ld(0),{_hash(f'ld(2)*57.31+N*1.37+{s:.2f}')})));"  # lines that lose color
            + f"{mid}+({plane}(X-ld(6)-W*0.006*ld(0),Y+ld(7))-{mid})*(1-ld(8))*(1-0.8*ld(4)*ld(0))"
        )

    return f"geq=lum='{luma}':cb='{chroma('cb')}':cr='{chroma('cr')}':enable='between(t,{a:.3f},{b:.3f})'"


def video_graph(
    windows: list[tuple[float, float]],
    size: tuple[int, int],
    src: str,
    out: str,
    pix_fmt: str = "",
    seed: int = 0,
) -> str:
    """Filter-graph text that glitches [src] into [out] during the windows (the picture's clock
    must start at 0, as it does on the burn-in path). The picture is put in the encoder's own pixel
    format first (no extra conversion), so the glitch knows its brightness range. `seed` makes each
    clip's glitches its own (glitch_seed)."""
    W, _H = size
    deep = "10" in pix_fmt or pix_fmt == "p010le"
    top = 1023 if deep else 255
    fmt = pix_fmt if pix_fmt.startswith("yuv") else ("yuv420p10le" if deep else "yuv420p")
    chain = [f"format={fmt}"]
    chain += [_glitch_geq(a, b, n, top, seed) for n, (a, b) in enumerate(windows)]
    chain.append(
        f"avgblur=sizeX={max(2, W // 160)}:sizeY=1:planes=6:enable='{_when(windows)}'"
    )  # color bleeds
    return f"[{src}]" + ",".join(chain) + f"[{out}]"


def glitch_seed(src: str, trim: tuple[float, float] | None) -> int:
    """Each clip (and each trim of it) glitches its own way; the same clip always the same way."""
    return zlib.crc32(f"{Path(src).name}:{trim[0] if trim else 0:.3f}".encode())


def audio_filters(windows: list[tuple[float, float]]) -> list[str]:
    """The sound drops, flutters, goes dull and crunches while the picture glitches."""
    on = _when(windows)
    return [
        f"volume=volume='if({on},0.6,1)':eval=frame",
        f"tremolo=f=11:d=0.5:enable='{on}'",  # (vibrato made NaNs on some camcorder sound)
        f"lowpass=f=3500:enable='{on}'",
        f"acrusher=bits=8:mix=0.4:enable='{on}'",
    ]


# ---------------------------------------------------------------------------- start / end screen
STOP_FRAMES_S = 0.1  # with a screen: STOP shows on the last couple of frames, then on the end screen
STOP_SHOWS_S = 1.6  # and stays on the end screen this long
STOP_ALONE_S = 1.0  # without a screen: STOP shows for the video's last second


def vhs(s: Settings) -> bool:
    """The VHS Camcorder Look is on (where PLAY / STOP and the tape effects live)."""
    return s.burns and s.burn_style == "vhs"


def marks(s: Settings, length: float, first: bool, last: bool):
    """PLAY / STOP timing for a clip (first / last = it starts / ends the video). PLAY blinks for 4
    seconds, the first 2 of them on the start screen if there is one; STOP comes up at the end."""
    from listo.core.burnin import Marks

    if not vhs(s):
        return None
    screen = wants_blue(s)
    play = 0.0
    if s.burn_badge == "play" and first:
        play = max(0.0, 4.0 - BLUE_SECONDS) if screen else 4.0
    stop = None
    if s.burn_stop and last:
        stop = max(0.0, length - (STOP_FRAMES_S if screen else STOP_ALONE_S))
    return Marks(play_until=play, stop_at=stop)


def blue_badge(s: Settings, which: str) -> str:
    """PLAY blinking on the start screen, STOP on the end one (when those badges are on)."""
    if not vhs(s):
        return ""
    if which == "start":
        return "play" if s.burn_badge == "play" else ""
    return "stop" if s.burn_stop else ""


def screen_color(s: Settings) -> str:
    """The plain screen's color for ffmpeg (0xRRGGBB)."""
    if s.tape_screen == "black":
        return "0x000000"
    if s.tape_screen == "color" and re.fullmatch(r"#?[0-9A-Fa-f]{6}", s.tape_screen_color or ""):
        return "0x" + s.tape_screen_color.lstrip("#").upper()
    return BLUE


def screen_sources(s: Settings, conform, seconds: float) -> tuple[str, str]:
    """lavfi sources (picture, sound) for the start / end screen. Color bars are SMPTE bars (HD bars
    for wide pictures) with a 1 kHz tone at -20 dBFS, like the head of a broadcast tape."""
    W, H = conform.width, conform.height
    rate = conform.rate or "30000/1001"
    layout = "mono" if conform.channels == 1 else "stereo"
    if s.tape_screen == "bars":
        bars = "smptehdbars" if W / max(H, 1) > 1.5 else "smptebars"
        video = f"{bars}=s={W}x{H}:r={rate}:d={seconds}"
        audio = f"sine=f=1000:r={conform.sample_rate}:d={seconds},volume=-2dB"  # sine is -18 dBFS
        if layout == "stereo":
            audio += ",pan=stereo|c0=c0|c1=c0"
        return video, audio
    return (
        f"color=c={screen_color(s)}:s={W}x{H}:r={rate}:d={seconds}",
        f"anullsrc=r={conform.sample_rate}:cl={layout}",
    )


def picture_area(info: MediaInfo, s: Settings):
    """Where the picture sits in the frame (inside any bars), so the badges line up with the video's."""
    from listo.core.frame import frame_plan

    return frame_plan(info.width, info.height, info.sar, s)[3]


def blue_settings(s: Settings) -> Settings:
    """The video's own encoder settings, nothing drawn on it."""
    b = s.copy()
    b.burn_timecode = b.burn_filename = b.burn_datetime = b.captions = False
    b.lut_path, b.desqueeze, b.aspect, b.video_resize, b.deinterlace = "", "1", "orig", "orig", "off"
    b.tape_glitches, b.tape_blue, b.join, b.caption_srt = "off", False, False, False
    b.verify = False
    return b


def make_blue(
    out: Path,
    conform,
    s: Settings,
    caps: Capabilities,
    badge: str = "",
    area=None,
    seconds: float = BLUE_SECONDS,
):
    """A short start / end screen piece (blue, black, bars & tone or a color) that matches the
    video exactly (size, frame rate, sound, encoder),
    so it can be joined on without re-encoding; badge "play" (blinking) or "stop" (steady, then gone)
    drawn where the video's own badge sits. Returns the engine Result."""
    from listo.core.burnin import FULL, badge_plan
    from listo.core.engine import Conversion
    from listo.core.probe import probe

    with tempfile.TemporaryDirectory(prefix="listo-blue-") as d:
        src = Path(d) / "screen.mkv"
        rate = conform.rate or "30000/1001"
        size = (conform.width, conform.height)
        video_src, audio_src = screen_sources(s, conform, seconds)
        bp = None
        if badge:
            when = "lt(mod(t,1),0.7)" if badge == "play" else f"lt(t,{STOP_SHOWS_S})"
            bp = badge_plan(badge, size, area or FULL, when)
        try:
            args = [caps.ffmpeg, "-hide_banner", "-v", "error", "-y",
                    "-f", "lavfi", "-i", video_src]  # fmt: skip
            n_images = 0
            if bp is not None and not bp.empty:
                args += bp.input_args(rate, seconds)
                n_images = len(bp.images())
            args += ["-f", "lavfi", "-i", audio_src]
            if n_images:
                args += [
                    "-filter_complex",
                    bp.graph(1, "0:v", "vout"),
                    "-map",
                    "[vout]",
                    "-map",
                    f"{n_images + 1}:a",
                ]
            args += ["-t", f"{seconds}", "-c:v", "ffv1", "-c:a", "pcm_s16le", str(src)]
            subprocess.run(
                args, stdin=subprocess.DEVNULL, capture_output=True, timeout=120, check=True, **popen_kwargs()
            )
        finally:
            if bp is not None:
                bp.cleanup()
        return Conversion(
            str(src), probe(src), blue_settings(s), caps, set(), target=out, conform=conform
        ).run()
