"""Tape effects: VCR blue screen at the start and end, tracking glitches at joined cuts, and rare
random glitches through a video. All drawn by Listo's own ffmpeg; all off unless switched on.

A glitch is about half a second where the picture jitters sideways, a noise band rolls down it, the
colors split and grain spikes, and the sound dips and crunches, like a camcorder tape restarting.
Random glitch moments come from the clip's name, so the preview and the finished file glitch at
exactly the same moments.

The blue screen is made as its own short piece with the same encoder settings as the video
(make_blue), then joined on without re-encoding (join.concat), like the parts of a joined video.
"""

from __future__ import annotations

import random
import subprocess
import tempfile
import zlib
from pathlib import Path

from .presets import Settings
from .probe import MediaInfo
from .tools import Capabilities, popen_kwargs

BLUE = "0x1E2EE6"  # a VCR's blue screen
BLUE_SECONDS = 2.0
CUT_GLITCH_S = 0.45  # the glitch at each cut of a joined video
GLITCH_EVERY = {"rare": 90.0, "often": 30.0}  # random glitches: about one per this many seconds
NO_EFFECTS = ("rewrap", "gif", "audio")  # copies, palettes and sound-only can't take them


def applies(s: Settings) -> bool:
    return s.video_preset not in NO_EFFECTS


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
    if cut and s.tape_cut_glitch:
        out.append((0.0, min(CUT_GLITCH_S, max(0.05, length))))
    every = GLITCH_EVERY.get(s.tape_glitches)
    if every and info.duration > 0:
        rng = random.Random(zlib.crc32(Path(src).name.encode("utf-8")))  # noqa: S311 — looks, not security
        t = rng.uniform(every * 0.3, every)
        while t < info.duration:
            d = rng.uniform(0.2, 0.6)
            a, b = t - start, t + d - start
            if b > 0 and a < length:
                out.append((max(0.0, a), min(length, b)))
            t += rng.uniform(every * 0.5, every * 1.5)
    return out


def _when(windows: list[tuple[float, float]]) -> str:
    return "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in windows)


def video_graph(windows: list[tuple[float, float]], size: tuple[int, int], src: str, out: str) -> str:
    """Filter-graph text that glitches [src] into [out] during the windows (the picture's clock
    must start at 0, as it does on the burn-in path)."""
    W, H = size
    on = _when(windows)
    band = max(2, round(H / 7) // 2 * 2)
    shift = max(2, round(W / 180))
    jitter = f"{W / 70:.1f}*sin(t*71)+{W / 160:.1f}*sin(t*23)"
    return (
        f"[{src}]split=3[gA][gB][gC];"
        f"[gC]crop=iw:{band}:0:0,noise=alls=100:allf=t+u,avgblur=sizeX={max(2, W // 60)}:sizeY=1,"
        f"eq=brightness=0.18:contrast=1.6[gBand];"
        f"[gA][gB]overlay=x='{jitter}':y=0:enable='{on}'[gJ];"
        f"[gJ][gBand]overlay=x=0:y='mod(t*{H * 1.7:.0f},{H})':enable='{on}'[gN];"
        f"[gN]noise=alls=35:allf=t+u:enable='{on}',rgbashift=rh=-{shift}:bh={shift}:enable='{on}',"
        f"eq=saturation=1.35:enable='{on}'[{out}]"
    )


def audio_filters(windows: list[tuple[float, float]]) -> list[str]:
    """The sound dips and crunches while the picture glitches."""
    on = _when(windows)
    return [f"volume=volume='if({on},0.5,1)':eval=frame", f"acrusher=bits=7:mix=0.7:enable='{on}'"]


# ---------------------------------------------------------------------------- blue screen
def blue_settings(s: Settings) -> Settings:
    """The video's own encoder settings, nothing drawn on it."""
    b = s.copy()
    b.burn_timecode = b.burn_filename = b.burn_datetime = b.captions = False
    b.lut_path, b.desqueeze, b.aspect, b.video_resize, b.deinterlace = "", "1", "orig", "orig", "off"
    b.tape_glitches, b.tape_cut_glitch, b.tape_blue, b.join, b.caption_srt = "off", False, False, False, False
    b.verify = False
    return b


def make_blue(out: Path, conform, s: Settings, caps: Capabilities, seconds: float = BLUE_SECONDS):
    """A short blue-screen piece that matches the video exactly (size, frame rate, sound, encoder),
    so it can be joined on without re-encoding. Returns the engine Result."""
    from .engine import Conversion
    from .probe import probe

    with tempfile.TemporaryDirectory(prefix="listo-blue-") as d:
        src = Path(d) / "blue.mkv"
        rate = conform.rate or "30000/1001"
        layout = "mono" if conform.channels == 1 else "stereo"
        subprocess.run(
            [caps.ffmpeg, "-hide_banner", "-v", "error", "-y",
             "-f", "lavfi", "-i", f"color=c={BLUE}:s={conform.width}x{conform.height}:r={rate}:d={seconds}",
             "-f", "lavfi", "-i", f"anullsrc=r={conform.sample_rate}:cl={layout}",
             "-t", f"{seconds}", "-c:v", "ffv1", "-c:a", "pcm_s16le", str(src)],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=120, check=True, **popen_kwargs(),
        )  # fmt: skip
        return Conversion(
            str(src), probe(src), blue_settings(s), caps, set(), target=out, conform=conform
        ).run()
