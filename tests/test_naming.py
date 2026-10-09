"""Output names, folders and collision rules (never overwrite an original).

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

from pathlib import Path

from listo.core import naming
from listo.core.engine import Conversion
from listo.core.presets import Settings
from listo.core.probe import probe
from listo.core.tools import capabilities


def test_render_tokens_and_cleanup():
    ctx = {"name": "A001", "preset": "prores422", "date": "2026-10-08", "res": ""}
    assert naming.render("{name}_{preset}_{date}", ctx) == "A001_prores422_2026-10-08"
    assert naming.render("{name}_{res}", ctx) == "A001"  # empty token leaves no dangling "_"
    assert naming.render("{name}_{nope}", ctx) == "A001_{nope}"  # unknown tokens stay visible
    assert naming.render("a/b:c", ctx) == "a-b-c"


def test_never_overwrites_source_even_if_case_differs(tmp_path: Path):
    src = tmp_path / "IMG_0001.MOV"
    src.write_bytes(b"x")
    out, _note = naming.resolve_output(src, tmp_path / "IMG_0001.mov", "replace", set())
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
