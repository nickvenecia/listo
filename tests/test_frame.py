"""Picture shape: desqueeze, aspect-ratio crop / black bars, short-edge resizing.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from listo.core.engine import Conversion
from listo.core.frame import frame_filters, resized
from listo.core.presets import Settings
from listo.core.probe import probe
from listo.core.tools import capabilities

from .helpers import HAS_FFMPEG, ff


def shape(w, h, sar=1.0, **kw):
    _, ow, oh = frame_filters(w, h, sar, Settings(**kw))
    return ow, oh


def test_keep_original_does_nothing():
    assert frame_filters(1920, 1080, 1.0, Settings()) == ([], 1920, 1080)


def test_16x9_to_4x3_crops_the_sides():
    assert shape(1920, 1080, aspect="4:3") == (1440, 1080)


def test_4x3_to_16x9_with_bars_pillarboxes():
    assert shape(2880, 2160, aspect="16:9", aspect_fit="bars") == (3840, 2160)


def test_square_to_16x9_crop_and_bars():
    assert shape(1080, 1080, aspect="16:9") == (1080, 608)
    assert shape(1080, 1080, aspect="16:9", aspect_fit="bars") == (1920, 1080)


def test_vertical_and_scope():
    assert shape(1920, 1080, aspect="9:16") == (608, 1080)
    assert shape(3840, 2160, aspect="2.39:1") == (3840, 1606)


def test_desqueeze_widens_the_picture():
    assert shape(2880, 2160, desqueeze="2") == (5760, 2160)
    assert shape(1920, 1080, desqueeze="1.33") == (2554, 1080)


def test_desqueeze_too_wide_shrinks_height_instead():
    w, h = shape(4096, 3072, desqueeze="2")
    assert w == 8192 and h == 3072


def test_desqueeze_then_crop():
    assert shape(2880, 2160, desqueeze="2", aspect="2.39:1") == (5162, 2160)


def test_non_square_pixels_are_respected():
    # DV widescreen: 720×480 stored, pixels 32:27 wide -> really 16:9
    assert shape(720, 480, sar=32 / 27, aspect="16:9") == (854, 480)


def test_size_means_the_short_edge():
    assert resized(3840, 2160, "1080") == (1920, 1080)
    assert resized(1080, 1920, "720") == (720, 1280)  # vertical stays vertical
    assert resized(1280, 720, "1080") == (1280, 720)  # never upscales


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize(
    ("size", "kw", "want"),
    [
        ("640x360", {"aspect": "4:3"}, (480, 360)),
        ("480x360", {"aspect": "16:9", "aspect_fit": "bars"}, (640, 360)),
        ("360x360", {"aspect": "9:16"}, (202, 360)),
        ("320x360", {"desqueeze": "2"}, (640, 360)),
        ("1080x1920", {"video_resize": "720"}, (720, 1280)),
    ],
)
def test_real_conversion_sizes(tmp_path: Path, size, kw, want):
    src = tmp_path / "in.mov"
    ff("-f", "lavfi", "-i", f"testsrc2=s={size}:d=0.3", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src))
    s = Settings(video_preset="h264", naming="{name}_out", **kw)
    r = Conversion(str(src), probe(src), s, capabilities(), set()).run()
    assert r.status == "done", r.message
    out = probe(r.output)
    assert (out.width, out.height) == want


def test_cinema_bars_keep_the_frame_size():
    vf, w, h = frame_filters(1920, 1080, 1.0, Settings(aspect="2.35:1", aspect_fit="matte"))
    assert (w, h) == (1920, 1080)
    assert len(vf) == 2 and "h=131" in vf[0] and "black@1.00" in vf[0]


def test_cinema_bars_opacity_and_pillarbox():
    vf, _, _ = frame_filters(1920, 1080, 1.0, Settings(aspect="4:3", aspect_fit="matte", matte_opacity=40))
    assert "w=240" in vf[0] and "black@0.40" in vf[0]
    assert (
        frame_filters(1920, 1080, 1.0, Settings(aspect="4:3", aspect_fit="matte", matte_opacity=0))[0] == []
    )


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_cinema_bars_render(tmp_path: Path):
    src = tmp_path / "in.mov"
    ff(
        "-f",
        "lavfi",
        "-i",
        "color=c=white:s=640x360:d=0.3",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(src),
    )
    s = Settings(
        video_preset="h264", naming="{name}_m", aspect="2.35:1", aspect_fit="matte", matte_opacity=100
    )
    r = Conversion(str(src), probe(src), s, capabilities(), set()).run()
    assert r.status == "done", r.message
    png = tmp_path / "f.png"
    ff("-i", str(r.output), "-frames:v", "1", str(png))
    from PIL import Image

    im = Image.open(png).convert("L")
    assert im.size == (640, 360)
    assert im.getpixel((320, 10)) < 30 and im.getpixel((320, 180)) > 220  # black bar, white picture
