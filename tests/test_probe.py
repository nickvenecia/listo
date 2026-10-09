"""Reading files: frame rates and timecode math.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from listo.core.probe import probe

from .helpers import HAS_FFMPEG, ff


def test_nominal_rate():
    from listo.core.probe import nominal_rate

    assert nominal_rate("25/1", "50/1") == "25/1"  # AVCHD field rate reported
    assert nominal_rate("2997/100", "30000/1001") == "30000/1001"
    assert nominal_rate("621/30", "30/1") == "30/1"  # variable-rate phone clip


def test_tc_add():
    from listo.core.probe import tc_add

    assert tc_add("01:00:00:00", 2.0, "24000/1001") == "01:00:02:00"
    assert tc_add("00:00:59;29", 1 / 29.97, "30000/1001") == "00:01:00;02"
    assert tc_add("00:09:59;29", 1 / 29.97, "30000/1001") == "00:10:00;00"


def _moi(path: Path, when: tuple[int, int, int, int, int, int], aspect_byte: int) -> None:
    y, mo, d, h, mi, sec = when
    data = bytearray(0x100)
    data[0:2] = b"V6"
    data[6:8] = y.to_bytes(2, "big")
    data[8:12] = bytes([mo, d, h, mi])
    data[12:14] = (sec * 1000 + 250).to_bytes(2, "big")
    data[0x80] = aspect_byte
    path.write_bytes(bytes(data))


def test_read_jvc_moi(tmp_path: Path):
    from listo.core.probe import read_moi

    _moi(tmp_path / "MOV01A.MOI", (2007, 7, 14, 19, 22, 5), 0x44)
    m = read_moi(tmp_path / "MOV01A.MOI")
    assert m.recorded == datetime(2007, 7, 14, 19, 22, 5, 250000)
    assert m.widescreen is True and m.pal is False
    assert read_moi(tmp_path / "missing.MOI").recorded is None


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_mod_clip_uses_its_moi_for_date_and_widescreen(tmp_path: Path):
    from listo.core.frame import frame_filters
    from listo.core.presets import Settings

    clip = tmp_path / "MOV01A.MOD"
    ff("-f", "lavfi", "-i", "testsrc2=s=720x480:r=30000/1001:d=0.5", "-vf", "setsar=8/9", "-c:v", "mpeg2video",
       "-f", "vob", str(clip))  # fmt: skip
    assert probe(clip).created is None
    _moi(tmp_path / "mov01a.moi", (2007, 7, 14, 19, 22, 5), 0x45)  # 16:9, lower-case name on purpose
    info = probe(clip)
    assert info.created == datetime(2007, 7, 14, 19, 22, 5, 250000)
    _, w, h = frame_filters(info.width, info.height, info.sar, Settings(video_resize="1080"))
    assert abs(w / h - 16 / 9) < 0.01  # flagged 4:3 in the MPEG header, really widescreen
