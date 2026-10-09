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
