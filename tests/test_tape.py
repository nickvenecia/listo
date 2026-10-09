"""Tape effects (VHS look only): a screen at the start and end, glitches at joined cuts, random
glitches, PLAY / STOP."""

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


def _vhs(**kw) -> Settings:
    """Tape effects belong to the VHS Camcorder Look (burn-ins on, VHS style)."""
    return Settings(burn_timecode=True, burn_style="vhs", **kw)


def test_glitch_moments_are_steady_and_follow_the_settings():
    info = MediaInfo(kind="video", duration=600.0)
    rare = tape.glitch_windows(_vhs(tape_glitches="rare"), "/x/MOV01A.MOD", info, None)
    often = tape.glitch_windows(_vhs(tape_glitches="often"), "/x/MOV01A.MOD", info, None)
    assert 3 <= len(rare) <= 12 and len(often) > len(rare)  # ~every 90 s vs ~every 30 s
    assert rare == tape.glitch_windows(
        _vhs(tape_glitches="rare"), "/x/MOV01A.MOD", info, None
    )  # same every time
    assert all(0.25 <= b - a <= 0.5 for a, b in rare)
    assert tape.glitch_windows(_vhs(), "/x/a.mov", info, None) == []  # off by default
    cut = tape.glitch_windows(_vhs(tape_glitches="cuts"), "/x/a.mov", info, None, cut=True)
    assert cut == [(0.0, tape.CUT_GLITCH_S)]
    assert tape.glitch_windows(_vhs(tape_glitches="cuts"), "/x/a.mov", info, None, cut=False) == []
    rare_cut = tape.glitch_windows(_vhs(tape_glitches="rare"), "/x/MOV01A.MOD", info, None, cut=True)
    assert rare_cut[0] == (0.0, tape.CUT_GLITCH_S) and rare_cut[1:] == rare  # random ones glitch the cuts too
    trimmed = tape.glitch_windows(_vhs(tape_glitches="often"), "/x/MOV01A.MOD", info, (100.0, 200.0))
    assert all(0 <= a < b <= 100 for a, b in trimmed)  # moved onto the trimmed clip's own clock
    assert tape.glitch_windows(_vhs(video_preset="rewrap", tape_glitches="often"), "/x/a", info, None) == []
    # only with the VHS look: the clean look, or no burn-ins, means no tape effects at all
    assert tape.glitch_windows(Settings(tape_glitches="often"), "/x/a", info, None) == []
    clean = _vhs(tape_glitches="often", tape_blue=True)
    clean.burn_style = "clean"
    assert tape.glitch_windows(clean, "/x/a", info, None) == [] and not tape.wants_blue(clean)


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
    s = _vhs(video_preset="h264", tape_blue=True, tape_glitches="often", captions=True, caption_srt=True,
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
    s = _vhs(video_preset="h264", tape_glitches="cuts")
    r = Conversion(str(src), probe(src), s, capabilities(), set(), cut=True).run()
    assert r.status == "done", (r.message, r.log)
    cmd = " ".join(r.command)
    assert "geq=" in cmd and "acrusher" in cmd and "tremolo" in cmd
    assert f"between(t,0.000,{tape.CUT_GLITCH_S:.3f})" in cmd
    # the picture really changes during the glitch, and is untouched after it
    plain = Conversion(str(src), probe(src), _vhs(video_preset="h264"), capabilities(), set()).run()
    hit = _diff(r.output, plain.output, 0.12, tmp_path)
    after = _diff(r.output, plain.output, 1.2, tmp_path)
    assert hit > 3 and hit > 3 * after and after < 2, (hit, after)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_glitch_keeps_ten_bit_pictures_in_range(tmp_path: Path):
    """ProRes is 10-bit: the glitch works in the encoder's own pixel format (0-1023, not 0-255)."""
    src = _clip(tmp_path / "a.mp4")
    s = _vhs(video_preset="prores", tape_glitches="cuts")
    r = Conversion(str(src), probe(src), s, capabilities(), set(), cut=True).run()
    assert r.status == "done", (r.message, r.log)
    assert "format=yuv422p10le" in " ".join(r.command)
    plain = Conversion(str(src), probe(src), _vhs(video_preset="prores"), capabilities(), set()).run()
    assert _diff(r.output, plain.output, 1.2, tmp_path) < 2  # same brightness once it's over


def _diff(a: Path, b: Path, at: float, tmp: Path) -> float:
    """Average difference (0-255) between two videos' frames at `at`."""
    fa, fb = tmp / "da.png", tmp / "db.png"
    ff("-ss", f"{at}", "-i", str(a), "-frames:v", "1", str(fa))
    ff("-ss", f"{at}", "-i", str(b), "-frames:v", "1", str(fb))
    x, y = Image.open(fa).convert("L").tobytes(), Image.open(fb).convert("L").tobytes()
    return sum(abs(p - q) for p, q in zip(x, y, strict=True)) / len(x)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_joined_video_gets_one_blue_screen_around_it(tmp_path: Path):
    a, b = _clip(tmp_path / "a.mp4"), _clip(tmp_path / "b.mp4")
    s = _vhs(video_preset="prores", join=True, tape_blue=True, tape_glitches="cuts")
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


def test_play_and_stop_marks():
    s = _vhs(video_preset="h264", tape_blue=True, burn_badge="play", burn_stop=True)
    m = tape.marks(s, 10.0, first=True, last=True)
    assert (
        m.play_until == 4.0 - tape.BLUE_SECONDS
    )  # PLAY blinks on the start screen, then on into the footage
    assert abs(m.stop_at - (10.0 - tape.STOP_FRAMES_S)) < 1e-9  # STOP on the last frames
    middle = tape.marks(s, 10.0, first=False, last=False)
    assert middle.play_until == 0 and middle.stop_at is None  # joined clips in between: neither
    assert tape.blue_badge(s, "start") == "play" and tape.blue_badge(s, "end") == "stop"

    no_stop = s.copy()
    no_stop.burn_stop = False  # STOP is its own switch
    assert tape.marks(no_stop, 10.0, True, True).stop_at is None and tape.blue_badge(no_stop, "end") == ""

    rec = s.copy()
    rec.burn_badge = "rec"  # REC and STOP go together fine; no PLAY on the start screen
    assert tape.blue_badge(rec, "start") == "" and tape.marks(rec, 10.0, True, True).stop_at is not None

    alone = s.copy()
    alone.tape_blue = False  # no screen: PLAY for 4 s, STOP for the last second
    m = tape.marks(alone, 10.0, True, True)
    assert m.play_until == 4.0 and abs(m.stop_at - (10.0 - tape.STOP_ALONE_S)) < 1e-9

    clean = s.copy()
    clean.burn_style = "clean"
    assert tape.marks(clean, 10.0, True, True) is None and tape.blue_badge(clean, "start") == ""


def test_screen_choices():
    from listo.core.video import Conform

    conform = Conform(1920, 1080, "25")
    s = _vhs(tape_blue=True)
    assert tape.screen_color(s) == tape.BLUE  # VCR blue by default
    s.tape_screen = "black"
    assert tape.screen_color(s) == "0x000000"
    s.tape_screen, s.tape_screen_color = "color", "#ff8800"
    assert tape.screen_color(s) == "0xFF8800"
    s.tape_screen_color = "nonsense"
    assert tape.screen_color(s) == tape.BLUE
    s.tape_screen = "bars"
    video, audio = tape.screen_sources(s, conform, 2.0)
    assert video.startswith("smptehdbars=") and "sine=f=1000" in audio and "pan=stereo" in audio
    sd, _ = tape.screen_sources(s, Conform(720, 480, "30000/1001"), 2.0)
    assert sd.startswith("smptebars=")  # 4:3 tapes get the classic bars


def _bright_top_left(video: Path, at: float, out: Path) -> int:
    """How many near-white pixels sit in the top-left corner (where PLAY / STOP are drawn)."""
    ff("-ss", f"{at}", "-i", str(video), "-frames:v", "1", str(out))
    im = Image.open(out).convert("RGB")
    w, h = im.size
    corner = im.crop((0, 0, w // 3, h // 4))
    px = corner.tobytes()
    return sum(1 for i in range(0, len(px), 3) if px[i] > 200 and px[i + 1] > 200)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_play_on_the_start_screen_and_stop_into_the_end_screen(tmp_path: Path):
    src = _clip(tmp_path / "a.mp4")
    s = _vhs(video_preset="h264", tape_blue=True, burn_badge="play", burn_stop=True)
    r = Conversion(str(src), probe(src), s, capabilities(), set()).run()
    assert r.status == "done", (r.message, r.log)
    d = probe(r.output).duration
    assert _bright_top_left(r.output, 0.2, tmp_path / "p.png") > 20  # PLAY on the blue screen
    assert _bright_top_left(r.output, d - tape.BLUE_SECONDS + 0.5, tmp_path / "s.png") > 20  # STOP on the end
    assert _bright_top_left(r.output, d - 0.2, tmp_path / "e.png") == 0  # then the screen is clean


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_stop_without_a_screen_and_off_by_default(tmp_path: Path):
    src = _clip(tmp_path / "a.mp4", secs=3)
    on = _vhs(video_preset="h264", burn_badge="none", burn_stop=True, naming="{name}_stop")
    off = _vhs(video_preset="h264", burn_badge="none", naming="{name}_plain")
    r_on = Conversion(str(src), probe(src), on, capabilities(), set()).run()
    r_off = Conversion(str(src), probe(src), off, capabilities(), set()).run()
    assert r_on.status == r_off.status == "done"
    assert _bright_top_left(r_on.output, 2.6, tmp_path / "a.png") > 20  # STOP for the last second
    assert _bright_top_left(r_on.output, 1.0, tmp_path / "b.png") < 5  # not before
    assert _bright_top_left(r_off.output, 2.6, tmp_path / "c.png") < 5  # and only when switched on


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_color_bars_and_tone_screen(tmp_path: Path):
    src = _clip(tmp_path / "a.mp4")
    s = _vhs(video_preset="h264", tape_blue=True, tape_screen="bars")
    r = Conversion(str(src), probe(src), s, capabilities(), set()).run()
    assert r.status == "done", (r.message, r.log)
    ff("-ss", "0.5", "-i", str(r.output), "-frames:v", "1", str(tmp_path / "bars.png"))
    im = Image.open(tmp_path / "bars.png").convert("RGB")
    w, h = im.size
    left, right = im.getpixel((w // 10, h // 3)), im.getpixel((w * 6 // 10, h // 3))
    assert left != right and max(left) > 150  # bars, not one flat color
    level = subprocess.run(
        [capabilities().ffmpeg, "-v", "info", "-t", "1", "-i", str(r.output), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr  # fmt: skip
    assert "mean_volume: -2" in level  # the 1 kHz tone at about -20 dBFS (sine RMS is 3 dB under its peak)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_glitch_tears_the_tape_but_not_play(tmp_path: Path):
    """PLAY / STOP are drawn by the VCR on top of the tape picture: a glitch never tears them.
    The timecode is on the tape, so it glitches with the picture."""
    from listo.core import burnin, video

    src = _clip(tmp_path / "a.mp4")
    s = _vhs(video_preset="h264", burn_badge="play", tape_glitches="cuts")
    plan = video.build(str(src), str(tmp_path / "o.mp4"), probe(src), s, capabilities(), glitch_cut=True)
    graph = plan.args[plan.args.index("-filter_complex") + 1]
    play = next(la for la in plan.burn.layers if la.vcr)  # the PLAY layer
    assert graph.index("geq=") < graph.index(f"overlay={play.x}:{play.y}")  # drawn after the glitch
    tc = next(la for la in plan.burn.layers if not la.vcr)
    assert graph.index(f"overlay={tc.x}:{tc.y}") < graph.index("geq=")  # timecode glitches with the tape
    plan.cleanup()
    assert burnin.Layer(Path("x"), 0, 0).vcr is False


def test_old_recipes_keep_their_cut_glitch():
    s = Settings.from_dict({"tape_cut_glitch": True})
    assert s.tape_glitches == "cuts"
    assert Settings.complete({"tape_cut_glitch": True, "tape_glitches": "often"})["tape_glitches"] == "often"
    assert "tape_cut_glitch" not in Settings.complete({"tape_cut_glitch": False})
