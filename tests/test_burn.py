"""Burn-ins: drawn by Listo (no drawtext needed), clean and VHS styles, clip date + running clock.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image

from listo.core import burnin
from listo.core.engine import Conversion
from listo.core.frame import frame_plan
from listo.core.presets import Settings
from listo.core.probe import MediaInfo, _shot_time, file_date, probe, tc_add
from listo.core.tools import capabilities

from .helpers import HAS_FFMPEG, ff


def test_apple_local_time_wins_over_utc():
    t = _shot_time(
        {
            "creation_time": "2026-10-09T03:54:12Z",
            "com.apple.quicktime.creationdate": "2026-10-08T21:54:12-0600",
        },
        [],
    )
    assert t.isoformat() == "2026-10-08T21:54:12-06:00"


def test_placeholder_dates_are_ignored():
    assert (
        _shot_time({"creation_time": "1970-01-01T00:00:00Z"}, [{"creation_time": "1904-01-01T00:00:00Z"}])
        is None
    )


def _layers(s: Settings, area=(0.0, 0.0, 1.0, 1.0)):
    info = MediaInfo(kind="video", width=1920, height=1080, fps=24, rate="24/1")
    bp = burnin.plan(
        info,
        s,
        (1920, 1080),
        area,
        "/x/IMG_3628.MOV",
        datetime(2026, 10, 8, 21, 54, 12),
        "01:00:00:00",
        Fraction(24),
    )
    try:
        return bp.layers, [Image.open(la.image).size for la in bp.layers]
    finally:
        bp.cleanup()
        assert not bp.folder.exists()


def test_vhs_draws_play_timecode_clock_date_and_name():
    s = Settings(burn_style="vhs", burn_datetime=True, burn_timecode=True, burn_filename=True)
    layers, _ = _layers(s)
    strips = [la for la in layers if la.cell]
    assert len(strips) == 8 + 1 + 6  # timecode digits, AM/PM, clock digits
    assert sum(1 for la in layers if not la.cell) == 5  # PLAY, timecode line, date, clock line, name


def test_burn_ins_stay_inside_cinema_bars():
    s = Settings(
        burn_style="vhs", burn_filename=True, burn_timecode=True, aspect="2.35:1", aspect_fit="matte"
    )
    _, _, h, area = frame_plan(1920, 1080, 1.0, s)
    top, bottom = area[1] * h, (area[1] + area[3]) * h
    layers, sizes = _layers(s, area)
    for la, (_, lh) in zip(layers, sizes, strict=True):
        height = la.cell[1] if la.cell else lh
        assert la.y >= top - 30 and la.y + height <= bottom + 30  # (glow padding may hang over a little)


def _digit_at(rate: str, tc: str, frame: int, slot: int) -> int:
    """Run the real ffmpeg crop expression for one timecode digit and read which cell it picked."""
    r = Fraction(rate)
    fields, _ = burnin.timecode_fields(tc, r)
    exprs = [e for f in fields for e in (burnin.tens(f), burnin.ones(f))]
    graph = f"crop=4:4:0:'4*({exprs[slot]})',select='eq(n\\,{frame})'"
    strip = Path(__file__).parent / "_strip.png"
    img = Image.new("L", (4, 40))
    for d in range(10):
        img.paste(d * 25, (0, d * 4, 4, d * 4 + 4))
    img.save(strip)
    try:
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-framerate", rate, "-loop", "1", "-t", str(frame / float(r) + 1), "-i", str(strip),
             "-vf", graph, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, check=True,
        ).stdout  # fmt: skip
    finally:
        strip.unlink()
    return round(out[5] / 25)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize(
    ("rate", "tc", "frame"),
    [
        ("24/1", "01:00:00:00", 37),
        ("30000/1001", "00:00:59;29", 1),  # drop-frame: skips ;00 and ;01
        ("30000/1001", "00:09:59;29", 1),  # ...except every tenth minute
        ("60000/1001", "00:00:59;59", 1),
        ("25/1", "10:59:59:24", 1),
    ],
)
def test_timecode_digits_match_the_timecode_math(rate, tc, frame):
    want = tc_add(tc, frame / float(Fraction(rate)) - 1e-6, rate).replace(";", ":").replace(":", "")
    got = "".join(str(_digit_at(rate, tc, frame, i)) for i in range(8))
    assert got == want


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("style", ["clean", "vhs"])
def test_burn_in_conversion_with_awkward_name(tmp_path: Path, style):
    src = tmp_path / "Nick's clip, take 2 [A] 100%.mov"
    ff(
        "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30000/1001:d=0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-timecode", "01:00:00;00", "-metadata", "creation_time=2026-10-09T03:54:12Z", str(src),
    )  # fmt: skip
    info = probe(src)
    assert file_date(src, info).year == 2026
    s = Settings(
        video_preset="prores", burn_style=style, burn_timecode=True, burn_filename=True, burn_datetime=True,
        aspect="2.39:1", aspect_fit="matte", naming="{name}_burn",
    )  # fmt: skip
    import tempfile

    before = set(Path(tempfile.gettempdir()).glob("listo-burn-*"))
    r = Conversion(str(src), info, s, capabilities(), set()).run()
    assert r.status == "done", r.message
    assert any("Burn-ins added" in n for n in r.notes)
    assert set(Path(tempfile.gettempdir()).glob("listo-burn-*")) == before  # temp images removed
    out = probe(r.output)
    assert (out.width, out.height, out.pix_fmt) == (640, 360, "yuv422p10le")  # 10-bit 4:2:2 kept


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_camcorder_mpeg_ps_trim_starts_timecode_and_sound_at_zero(tmp_path: Path):
    """.MOD / .VOB files start at ~0.5 s; burned-in timecode must still begin on the first frame."""
    src = tmp_path / "MOV01A.MOD"
    ff(
        "-f", "lavfi", "-i", "testsrc2=s=720x480:r=30000/1001:d=4", "-f", "lavfi", "-i", "sine=d=4",
        "-vf", "setsar=10/11", "-c:v", "mpeg2video", "-flags", "+ilme+ildct", "-c:a", "mp2", "-f", "vob", str(src),
    )  # fmt: skip
    s = Settings(video_preset="h264", burn_timecode=True, video_resize="1080", naming="{name}_tc")
    r = Conversion(str(src), probe(src), s, capabilities(), set(), trim=(1.0, 3.0)).run()
    assert r.status == "done", r.message
    starts = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=start_time", "-of", "csv=p=0", str(r.output)],
        capture_output=True, text=True, check=True,
    ).stdout.split()  # fmt: skip
    assert all(abs(float(x)) < 0.03 for x in starts)
    out = probe(r.output)
    assert (out.width, out.height) == (1440, 1080)  # true 4:3, upscaled


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_preview_at_the_very_end_never_hangs(tmp_path: Path):
    """The looped burn-in images have an end, and previews stay clear of the last moment
    (camera files can hold sound past their last picture: no frame there, endless images)."""
    import subprocess
    import time

    from listo.core.video import preview_plan

    clip = tmp_path / "end.mpg"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=30000/1001:d=2", "-f", "lavfi", "-i", "sine=d=3",
       "-c:v", "mpeg2video", "-c:a", "mp2", "-f", "vob", str(clip))  # fmt: skip
    info = probe(clip)
    s = Settings(video_preset="h264", burn_timecode=True, burn_datetime=True, burn_style="vhs")
    args, plan = preview_plan(str(clip), info, s, capabilities(), info.duration, str(tmp_path / "p.png"))
    try:
        for i, a in enumerate(args):
            if a == "-loop":
                assert "-t" in args[i : args.index("-i", i)]  # every looped image stops
        t = time.monotonic()
        subprocess.run([capabilities().ffmpeg, *args], capture_output=True, timeout=20)
        assert time.monotonic() - t < 10
    finally:
        plan.cleanup()
