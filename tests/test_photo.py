"""Photo conversion.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

from pathlib import Path

from listo.core.engine import Conversion
from listo.core.presets import Settings
from listo.core.probe import probe
from listo.core.tools import capabilities


def test_photo_jpeg_roundtrip(tmp_path: Path):
    from PIL import Image

    src = tmp_path / "p.png"
    Image.new("RGBA", (50, 40), (1, 2, 3, 100)).save(src)
    r = Conversion(str(src), probe(src), Settings(photo_format="jpeg"), capabilities(), set()).run()
    assert r.status == "done" and r.output.suffix == ".jpg"


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
