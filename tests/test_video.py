"""ffmpeg command building and video/audio conversions.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from listo.core.engine import Conversion
from listo.core.presets import Settings
from listo.core.probe import probe
from listo.core.tools import capabilities
from tests.helpers import HAS_FFMPEG, ff


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_uppercase_mov_to_prores_keeps_original(tmp_path: Path):
    src = tmp_path / "IMG_0001.MOV"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src))
    before = src.read_bytes()
    r = Conversion(str(src), probe(src), Settings(video_preset="prores"), capabilities(), set()).run()
    assert r.status == "done", r.message
    assert src.read_bytes() == before
    assert r.output and r.output.exists() and r.output != src


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_odd_dimensions_h264(tmp_path: Path):
    src = tmp_path / "odd.mkv"
    ff(
        "-f",
        "lavfi",
        "-i",
        "color=s=641x361:d=1",
        "-vf",
        "scale=641:361,format=yuv444p",
        "-c:v",
        "ffv1",
        str(src),
    )
    r = Conversion(str(src), probe(src), Settings(video_preset="h264"), capabilities(), set()).run()
    assert r.status == "done", r.message + r.log


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_wav_input_converts(tmp_path: Path):
    src = tmp_path / "tone.wav"
    ff("-f", "lavfi", "-i", "sine=d=1", "-c:a", "pcm_s24le", str(src))
    s = Settings(audio_format="flac")
    r = Conversion(str(src), probe(src), s, capabilities(), set()).run()
    assert r.status == "done" and r.output.suffix == ".flac"


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_all_audio_tracks_kept_for_prores(tmp_path: Path):
    src = tmp_path / "multi.mov"
    ff(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x240:d=1",
        "-f",
        "lavfi",
        "-i",
        "sine=d=1",
        "-f",
        "lavfi",
        "-i",
        "sine=f=600:d=1",
        "-map",
        "0",
        "-map",
        "1",
        "-map",
        "2",
        "-c:v",
        "libx264",
        "-c:a",
        "pcm_s24le",
        str(src),
    )
    r = Conversion(str(src), probe(src), Settings(video_preset="prores"), capabilities(), set()).run()
    assert r.status == "done"
    assert len(probe(r.output).audio) == 2


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_share_formats_handle_quad_audio(tmp_path: Path):
    src = tmp_path / "quad.mov"
    ff(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x240:d=1",
        "-f",
        "lavfi",
        "-i",
        "sine=d=1",
        "-filter_complex",
        "[1:a]pan=4.0|FL=c0|FR=c0|FC=c0|BC=c0[a]",
        "-map",
        "0:v",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-c:a",
        "pcm_s24le",
        str(src),
    )
    for preset in ("webm", "h264"):
        r = Conversion(str(src), probe(src), Settings(video_preset=preset), capabilities(), set()).run()
        assert r.status == "done", (preset, r.message, r.log[-500:])


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_rewrap_vp9_explains(tmp_path: Path):
    src = tmp_path / "v.webm"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=1", "-c:v", "libvpx-vp9", "-deadline", "realtime", str(src))
    r = Conversion(str(src), probe(src), Settings(video_preset="rewrap"), capabilities(), set()).run()
    assert r.status == "failed" and "rewrapped" in r.message


def test_filter_escaping():
    from listo.core.video import fesc

    assert fesc("C:\\Users\\me\\a.cube") == "C\\\\:/Users/me/a.cube"
    assert "\\\\\\'" in fesc("it's")


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_lut_and_burnins(tmp_path: Path):
    d = tmp_path / "odd: dir, with 'quotes'"
    d.mkdir()
    lut = d / "look.cube"
    lut.write_text(
        "LUT_3D_SIZE 2\n" + "\n".join(f"{r} {g} {b}" for b in (0, 1) for g in (0, 1) for r in (0, 1)) + "\n"
    )
    src = d / "A001.mov"
    ff(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x240:r=24:d=1",
        "-c:v",
        "libx264",
        "-timecode",
        "01:00:00:00",
        str(src),
    )
    s = Settings(video_preset="h264", lut_path=str(lut), burn_timecode=True, burn_filename=True)
    r = Conversion(str(src), probe(src), s, capabilities(), set()).run()
    assert r.status == "done", r.message + r.log[-400:]
    assert "LUT applied: look.cube." in r.notes and "Burn-ins added." in r.notes
    assert "Checked — length matches." in r.notes


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_gif_burnin_timecode_runs_at_real_speed(tmp_path: Path):
    from listo.core.video import build

    src = tmp_path / "a.mov"
    ff(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x240:r=30000/1001:d=1",
        "-c:v",
        "libx264",
        "-timecode",
        "01:00:00;00",
        str(src),
    )
    plan = build(
        str(src),
        str(tmp_path / "o.gif"),
        probe(src),
        Settings(video_preset="gif", burn_timecode=True),
        capabilities(),
    )
    graph = plan.args[plan.args.index("-filter_complex") + 1]
    plan.cleanup()
    assert graph.index("overlay") < graph.index("fps=15")  # burned in before the frame-rate drop
    from listo.core.engine import Conversion

    r = Conversion(str(src), probe(src), Settings(video_preset="gif", burn_timecode=True, burn_filename=True),
                   capabilities(), set()).run()  # fmt: skip
    assert r.status == "done", r.message


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_trim_cuts_length_and_shifts_timecode(tmp_path: Path):
    src = tmp_path / "A001.mov"
    ff(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x240:r=24:d=6",
        "-f",
        "lavfi",
        "-i",
        "sine=d=6",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-timecode",
        "01:00:00:00",
        str(src),
    )
    for preset in ("prores", "h264", "audio", "gif"):
        r = Conversion(
            str(src), probe(src), Settings(video_preset=preset), capabilities(), set(), trim=(2.0, 4.5)
        ).run()
        assert r.status == "done" and not r.warning, (preset, r.message, r.warning)
        got = probe(r.output, as_media=True)
        assert abs(got.duration - 2.5) < 0.2, (preset, got.duration)
        if preset == "prores":
            assert got.timecode == "01:00:02:00"


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_audio_shorter_than_picture_no_false_alarm(tmp_path: Path):
    src = tmp_path / "v.mov"
    ff(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x240:d=4",
        "-f",
        "lavfi",
        "-i",
        "sine=d=2",
        "-c:v",
        "libx264",
        "-c:a",
        "pcm_s16le",
        str(src),
    )
    r = Conversion(str(src), probe(src), Settings(video_preset="audio"), capabilities(), set()).run()
    assert r.status == "done" and not r.warning, r.warning
