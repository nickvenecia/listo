"""Tape effects: blue screen at the start and end, glitches at joined cuts, random glitches."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from listo.core import join, tape
from listo.core.captions import Cue
from listo.core.engine import Conversion
from listo.core.presets import Settings
from listo.core.probe import MediaInfo, probe
from listo.core.tools import capabilities

from .helpers import HAS_FFMPEG, ff


def test_glitch_moments_are_steady_and_follow_the_settings():
    info = MediaInfo(kind="video", duration=600.0)
    rare = tape.glitch_windows(Settings(tape_glitches="rare"), "/x/MOV01A.MOD", info, None)
    often = tape.glitch_windows(Settings(tape_glitches="often"), "/x/MOV01A.MOD", info, None)
    assert 3 <= len(rare) <= 12 and len(often) > len(rare)  # ~every 90 s vs ~every 30 s
    assert rare == tape.glitch_windows(
        Settings(tape_glitches="rare"), "/x/MOV01A.MOD", info, None
    )  # same every time
    assert all(0.12 <= b - a <= 0.35 for a, b in rare)
    assert tape.glitch_windows(Settings(), "/x/a.mov", info, None) == []  # off by default
    cut = tape.glitch_windows(Settings(tape_cut_glitch=True), "/x/a.mov", info, None, cut=True)
    assert cut == [(0.0, tape.CUT_GLITCH_S)]
    assert tape.glitch_windows(Settings(tape_cut_glitch=True), "/x/a.mov", info, None, cut=False) == []
    trimmed = tape.glitch_windows(Settings(tape_glitches="often"), "/x/MOV01A.MOD", info, (100.0, 200.0))
    assert all(0 <= a < b <= 100 for a, b in trimmed)  # moved onto the trimmed clip's own clock
    assert (
        tape.glitch_windows(Settings(video_preset="rewrap", tape_glitches="often"), "/x/a", info, None) == []
    )


def _clip(path: Path, secs: int = 2) -> Path:
    ff("-f", "lavfi", "-i", f"testsrc2=s=320x240:r=30000/1001:d={secs}", "-f", "lavfi", "-i", f"sine=d={secs}",
       "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path))  # fmt: skip
    return path


def _frame(video: Path, at: float, out: Path) -> tuple[int, int, int]:
    ff("-ss", f"{at}", "-i", str(video), "-frames:v", "1", str(out))
    return Image.open(out).convert("RGB").getpixel((160, 120))


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_single_video_gets_blue_screen_and_glitches(tmp_path: Path):
    src = _clip(tmp_path / "a.mp4")
    s = Settings(video_preset="h264", tape_blue=True, tape_glitches="often", captions=True, caption_srt=True,
                 destination="folder", dest_folder=str(tmp_path / "out"))  # fmt: skip
    r = Conversion(str(src), probe(src), s, capabilities(), set(), captions=[Cue(0.5, 1.5, "Hi.")]).run()
    assert r.status == "done", (r.message, r.log)
    assert not r.warning, r.warning  # the length check knows about the blue screen
    got = probe(r.output)
    assert abs(got.duration - (2 + 2 * tape.BLUE_SECONDS)) < 0.3
    red, green, blue = _frame(r.output, 0.5, tmp_path / "f0.png")
    assert blue > 180 and red < 80 and green < 100  # VCR blue at the start
    assert _frame(r.output, got.duration - 0.5, tmp_path / "f1.png")[2] > 180  # and at the end
    assert "00:00:02,500" in r.output.with_suffix(".srt").read_text()  # captions moved past the blue
    assert not any(p.name.startswith(".listo-blue-") for p in r.output.parent.iterdir())


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_glitch_filters_go_on_picture_and_sound(tmp_path: Path):
    src = _clip(tmp_path / "a.mp4")
    s = Settings(video_preset="h264", tape_cut_glitch=True)
    r = Conversion(str(src), probe(src), s, capabilities(), set(), cut=True).run()
    assert r.status == "done", (r.message, r.log)
    cmd = " ".join(r.command)
    assert "rgbashift" in cmd and "noise=" in cmd and "acrusher" in cmd and "between(t,0.000,0.200)" in cmd


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_joined_video_gets_one_blue_screen_around_it(tmp_path: Path):
    a, b = _clip(tmp_path / "a.mp4"), _clip(tmp_path / "b.mp4")
    s = Settings(video_preset="prores", join=True, tape_blue=True, tape_cut_glitch=True)
    folder = join.parts_folder(str(a), s)
    folder.mkdir()
    conform = join.conform_for(probe(a), s)
    parts = []
    for n, c in enumerate((a, b), 1):
        target = join.part_path(folder, n, s)
        r = Conversion(
            str(c), probe(c), s, capabilities(), set(), target=target, conform=conform, cut=n > 1
        ).run()
        assert r.status == "done", r.message
        parts.append(target)
    r = join.Join(parts, str(a), probe(a), s, capabilities(), set(), last_src=str(b), conform=conform).run()
    assert r.status == "done", (r.message, r.log)
    assert abs(probe(r.output).duration - (4 + 2 * tape.BLUE_SECONDS)) < 0.3  # blue once, not per clip
    assert _frame(r.output, 0.5, tmp_path / "f.png")[2] > 180
    assert not folder.exists()
    out = subprocess.run([capabilities().ffprobe, "-v", "error", "-show_entries", "stream=codec_type",
                          "-of", "csv=p=0", str(r.output)], capture_output=True, text=True).stdout.split()  # fmt: skip
    assert out.count("video") == 1 and out.count("audio") == 1


def test_play_and_stop_marks_follow_the_vcr_badge():
    vcr = Settings(
        video_preset="h264", tape_blue=True, burn_timecode=True, burn_style="vhs", burn_badge="play"
    )
    m = tape.marks(vcr, 10.0, first=True, last=True)
    assert m.play_until == 4.0 - tape.BLUE_SECONDS  # PLAY blinks on the blue screen, then on into the footage
    assert abs(m.stop_at - (10.0 - tape.STOP_FRAMES_S)) < 1e-9  # STOP on the last frames
    middle = tape.marks(vcr, 10.0, first=False, last=False)
    assert middle.play_until == 0 and middle.stop_at is None  # joined clips in between: neither
    assert tape.blue_badge(vcr, "start") == "play" and tape.blue_badge(vcr, "end") == "stop"
    plain = vcr.copy()
    plain.burn_badge = "rec"
    assert tape.marks(plain, 10.0, True, True) is None and tape.blue_badge(plain, "end") == ""
    no_blue = vcr.copy()
    no_blue.tape_blue = False
    assert tape.marks(no_blue, 10.0, True, True) is None


def _bright_top_left(video: Path, at: float, out: Path) -> int:
    """How many near-white pixels sit in the top-left corner (where PLAY / STOP are drawn)."""
    ff("-ss", f"{at}", "-i", str(video), "-frames:v", "1", str(out))
    im = Image.open(out).convert("RGB")
    w, h = im.size
    corner = im.crop((0, 0, w // 3, h // 4))
    px = corner.tobytes()
    return sum(1 for i in range(0, len(px), 3) if px[i] > 200 and px[i + 1] > 200)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_play_on_the_blue_start_and_stop_into_the_blue_end(tmp_path: Path):
    src = _clip(tmp_path / "a.mp4")
    s = Settings(video_preset="h264", tape_blue=True, burn_timecode=True, burn_style="vhs", burn_badge="play")
    r = Conversion(str(src), probe(src), s, capabilities(), set()).run()
    assert r.status == "done", (r.message, r.log)
    d = probe(r.output).duration
    assert _bright_top_left(r.output, 0.2, tmp_path / "p.png") > 20  # PLAY on the blue screen
    assert (
        _bright_top_left(r.output, d - tape.BLUE_SECONDS + 0.5, tmp_path / "s.png") > 20
    )  # STOP on the blue end
    assert _bright_top_left(r.output, d - 0.2, tmp_path / "e.png") == 0  # then the blue is clean
