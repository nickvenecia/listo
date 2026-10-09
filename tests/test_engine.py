"""Run with: python -m pytest -q   (integration tests need ffmpeg on PATH)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from listo import naming
from listo.engine import Conversion
from listo.presets import Settings
from listo.probe import probe
from listo.tools import capabilities

HAS_FFMPEG = shutil.which("ffmpeg") is not None


# ---------- naming


def test_render_tokens_and_cleanup():
    ctx = {"name": "A001", "preset": "prores422", "date": "2026-10-08", "res": ""}
    assert naming.render("{name}_{preset}_{date}", ctx) == "A001_prores422_2026-10-08"
    assert naming.render("{name}_{res}", ctx) == "A001"  # empty token leaves no dangling "_"
    assert naming.render("{name}_{nope}", ctx) == "A001_{nope}"  # unknown tokens stay visible
    assert naming.render("a/b:c", ctx) == "a-b-c"


def test_never_overwrites_source_even_if_case_differs(tmp_path: Path):
    src = tmp_path / "IMG_0001.MOV"
    src.write_bytes(b"x")
    out, note = naming.resolve_output(src, tmp_path / "IMG_0001.mov", "replace", set())
    assert out is not None and out.name == "IMG_0001_2.mov"


def test_collision_policies(tmp_path: Path):
    src = tmp_path / "a.mts"
    src.write_bytes(b"x")
    existing = tmp_path / "a.mov"
    existing.write_bytes(b"y")
    assert naming.resolve_output(src, existing, "skip", set())[0] is None
    assert naming.resolve_output(src, existing, "replace", set())[0] == existing
    assert naming.resolve_output(src, existing, "number", set())[0].name == "a_2.mov"
    # reserved by another file in the same batch -> numbered even with "replace"
    fresh = tmp_path / "b.mov"
    assert naming.resolve_output(src, fresh, "replace", {naming.reserve_key(fresh)})[0].name == "b_2.mov"


def test_proxy_goes_in_proxy_folder(tmp_path: Path):
    s = Settings(video_preset="proxy")
    assert naming.output_dir(tmp_path / "x.mov", s, "video") == tmp_path / "Proxy"


# ---------- integration


def ff(*a: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *a], check=True)


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
    ff("-f", "lavfi", "-i", "color=s=641x361:d=1", "-vf", "scale=641:361,format=yuv444p", "-c:v", "ffv1", str(src))
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
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=1", "-f", "lavfi", "-i", "sine=d=1",
       "-f", "lavfi", "-i", "sine=f=600:d=1", "-map", "0", "-map", "1", "-map", "2",
       "-c:v", "libx264", "-c:a", "pcm_s24le", str(src))
    r = Conversion(str(src), probe(src), Settings(video_preset="prores"), capabilities(), set()).run()
    assert r.status == "done"
    assert len(probe(r.output).audio) == 2


def test_photo_jpeg_roundtrip(tmp_path: Path):
    from PIL import Image

    src = tmp_path / "p.png"
    Image.new("RGBA", (50, 40), (1, 2, 3, 100)).save(src)
    r = Conversion(str(src), probe(src), Settings(photo_format="jpeg"), capabilities(), set()).run()
    assert r.status == "done" and r.output.suffix == ".jpg"


def test_original_names_kept_exactly():
    ctx = {"name": "_DSC0001", "preset": "h264", "res": ""}
    assert naming.render("{name}", ctx) == "_DSC0001"
    assert naming.render("{name}_{res}_{preset}", ctx) == "_DSC0001_h264"
    assert naming.render("A__B-{res}", {"res": ""}) == "A__B"


def test_replace_never_hits_another_original(tmp_path: Path):
    from PIL import Image

    jpg, png = tmp_path / "IMG_1.jpg", tmp_path / "IMG_1.png"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(jpg)
    Image.new("RGB", (8, 8), (0, 0, 255)).save(png)
    before = jpg.read_bytes()
    reserved = {naming.reserve_key(jpg), naming.reserve_key(png)}
    s = Settings(photo_format="jpeg", collision="replace")
    r = Conversion(str(png), probe(png), s, capabilities(), reserved).run()
    assert r.status == "done" and r.output.name == "IMG_1_2.jpg"
    assert jpg.read_bytes() == before


def test_photo_16bit_gray_and_cmyk(tmp_path: Path):
    import numpy as np
    from PIL import Image

    g = tmp_path / "g16.png"
    Image.fromarray(np.full((10, 10), 32768, dtype=np.uint16)).save(g)
    r = Conversion(str(g), probe(g), Settings(photo_format="jpeg"), capabilities(), set()).run()
    assert r.status == "done"
    assert 120 < Image.open(r.output).convert("L").getpixel((5, 5)) < 136
    c = tmp_path / "c.jpg"
    Image.new("CMYK", (10, 10), (0, 255, 255, 0)).save(c)
    r = Conversion(str(c), probe(c), Settings(photo_format="png"), capabilities(), set()).run()
    assert r.status == "done" and Image.open(r.output).mode == "RGB"


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_share_formats_handle_quad_audio(tmp_path: Path):
    src = tmp_path / "quad.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=1", "-f", "lavfi", "-i", "sine=d=1",
       "-filter_complex", "[1:a]pan=4.0|FL=c0|FR=c0|FC=c0|BC=c0[a]", "-map", "0:v", "-map", "[a]",
       "-c:v", "libx264", "-c:a", "pcm_s24le", str(src))
    for preset in ("webm", "h264"):
        r = Conversion(str(src), probe(src), Settings(video_preset=preset), capabilities(), set()).run()
        assert r.status == "done", (preset, r.message, r.log[-500:])


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_rewrap_vp9_explains(tmp_path: Path):
    src = tmp_path / "v.webm"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=1", "-c:v", "libvpx-vp9", "-deadline", "realtime", str(src))
    r = Conversion(str(src), probe(src), Settings(video_preset="rewrap"), capabilities(), set()).run()
    assert r.status == "failed" and "rewrapped" in r.message


# ---------- recipes, per-file formats, look, verify, parallel


def test_recipe_apply_and_match():
    s = Settings()
    vals = {"video_preset": "h264", "video_variant": {"h264": "standard"}, "burn_timecode": True,
            "destination": "subfolder", "subfolder_name": "Review", "naming": "{name}_review"}
    assert not s.matches(vals)
    s.apply(vals)
    assert s.matches(vals) and s.video_preset == "h264" and s.burn_timecode
    s.naming = "{name}"
    assert not s.matches(vals)


def test_per_file_override_leaves_panel_alone():
    s = Settings(video_preset="prores")
    o = s.with_override({"video_preset": "dnxhr", "video_variant": {"dnxhr": "dnxhr_sq"}})
    assert o.video_preset == "dnxhr" and o.variant_for("dnxhr") == "dnxhr_sq"
    assert s.video_preset == "prores" and "dnxhr" not in s.video_variant


def test_filter_escaping():
    from listo.video import fesc

    assert fesc("C:\\Users\\me\\a.cube") == "C\\\\:/Users/me/a.cube"
    assert "\\\\\\'" in fesc("it's")


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_lut_and_burnins(tmp_path: Path):
    d = tmp_path / "odd: dir, with 'quotes'"
    d.mkdir()
    lut = d / "look.cube"
    lut.write_text("LUT_3D_SIZE 2\n" + "\n".join(f"{r} {g} {b}" for b in (0, 1) for g in (0, 1) for r in (0, 1)) + "\n")
    src = d / "A001.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=24:d=1", "-c:v", "libx264", "-timecode", "01:00:00:00", str(src))
    s = Settings(video_preset="h264", lut_path=str(lut), burn_timecode=True, burn_filename=True)
    r = Conversion(str(src), probe(src), s, capabilities(), set()).run()
    assert r.status == "done", r.message + r.log[-400:]
    assert "LUT applied: look.cube." in r.notes and "Burn-ins added." in r.notes
    assert "Checked — length matches." in r.notes


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_verify_catches_short_output(tmp_path: Path, monkeypatch):
    from listo import engine

    src = tmp_path / "a.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=3", "-c:v", "libx264", str(src))
    info = probe(src)
    info.duration = 60.0  # pretend the original was a minute long
    r = engine.Conversion(str(src), info, Settings(video_preset="h264"), capabilities(), set()).run()
    assert r.status == "done" and "doesn't match" in r.warning


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_two_at_once_never_share_a_name(tmp_path: Path):
    import threading

    srcs = []
    for sub in ("card1", "card2"):
        (tmp_path / sub).mkdir()
        p = tmp_path / sub / "00000.MTS"
        ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=1", "-c:v", "libx264", "-f", "mpegts", str(p))
        srcs.append(p)
    out = tmp_path / "out"
    s = Settings(video_preset="h264", destination="folder", dest_folder=str(out))
    reserved = {naming.reserve_key(p) for p in srcs}
    results = []
    ts = [threading.Thread(target=lambda p=p: results.append(
        Conversion(str(p), probe(p), s, capabilities(), reserved).run())) for p in srcs]
    [t.start() for t in ts]
    [t.join() for t in ts]
    names = sorted(r.output.name for r in results)
    assert names == ["00000.mp4", "00000_2.mp4"]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_audio_shorter_than_picture_no_false_alarm(tmp_path: Path):
    src = tmp_path / "v.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=4", "-f", "lavfi", "-i", "sine=d=2",
       "-c:v", "libx264", "-c:a", "pcm_s16le", str(src))
    r = Conversion(str(src), probe(src), Settings(video_preset="audio"), capabilities(), set()).run()
    assert r.status == "done" and not r.warning, r.warning


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_gif_burnin_timecode_runs_at_real_speed(tmp_path: Path):
    from listo.video import build

    src = tmp_path / "a.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=30000/1001:d=1", "-c:v", "libx264",
       "-timecode", "01:00:00;00", str(src))
    plan = build(str(src), str(tmp_path / "o.gif"), probe(src),
                 Settings(video_preset="gif", burn_timecode=True), capabilities())
    vf = plan.args[plan.args.index("-vf") + 1]
    assert vf.index("drawtext") < vf.index("fps=15")


def test_nominal_rate():
    from listo.probe import nominal_rate

    assert nominal_rate("25/1", "50/1") == "25/1"          # AVCHD field rate reported
    assert nominal_rate("2997/100", "30000/1001") == "30000/1001"
    assert nominal_rate("621/30", "30/1") == "30/1"         # variable-rate phone clip


# ---------- trim + links


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_trim_cuts_length_and_shifts_timecode(tmp_path: Path):
    src = tmp_path / "A001.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=24:d=6", "-f", "lavfi", "-i", "sine=d=6",
       "-c:v", "libx264", "-c:a", "aac", "-timecode", "01:00:00:00", str(src))
    for preset in ("prores", "h264", "audio", "gif"):
        r = Conversion(str(src), probe(src), Settings(video_preset=preset), capabilities(), set(),
                       trim=(2.0, 4.5)).run()
        assert r.status == "done" and not r.warning, (preset, r.message, r.warning)
        got = probe(r.output, as_media=True)
        assert abs(got.duration - 2.5) < 0.2, (preset, got.duration)
        if preset == "prores":
            assert got.timecode == "01:00:02:00"


def test_tc_add():
    from listo.probe import tc_add

    assert tc_add("01:00:00:00", 2.0, "24000/1001") == "01:00:02:00"
    assert tc_add("00:00:59;29", 1 / 29.97, "30000/1001") == "00:01:00;02"
    assert tc_add("00:09:59;29", 1 / 29.97, "30000/1001") == "00:10:00;00"


def test_is_link():
    from listo.links import is_link

    assert is_link("https://youtu.be/abc123xyz")
    assert not is_link("hello world") and not is_link("/Users/nick/a.mov")
