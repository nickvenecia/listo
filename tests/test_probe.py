"""Reading files: frame rates and timecode math.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from listo.core.probe import probe

from .helpers import HAS_FFMPEG, ff, write_moi


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


def test_read_jvc_moi(tmp_path: Path):
    from listo.core.probe import read_moi

    write_moi(tmp_path / "MOV01A.MOI", (2007, 7, 14, 19, 22, 5), 0x44)
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
    write_moi(tmp_path / "mov01a.moi", (2007, 7, 14, 19, 22, 5), 0x45)  # 16:9, lower-case name on purpose
    info = probe(clip)
    assert info.created == datetime(2007, 7, 14, 19, 22, 5, 250000)
    _, w, h = frame_filters(info.width, info.height, info.sar, Settings(video_resize="1080"))
    assert abs(w / h - 16 / 9) < 0.01  # flagged 4:3 in the MPEG header, really widescreen


@pytest.fixture
def in_new_york(monkeypatch):
    """This computer's clock set to New York: -05:00 in winter, -04:00 in summer (daylight saving)."""
    import time

    if not hasattr(time, "tzset"):
        pytest.skip("the time zone can't be switched here (Windows)")
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_camera_clock_gets_this_computers_offset_for_that_date(in_new_york):
    """A .MOI time has no zone: it gets this computer's offset on that date, daylight saving included.
    Whole seconds, like the Date & Time burn-in; a trim moves it to the new first frame."""
    from listo.core.probe import MediaInfo, recorded

    summer = recorded("MOV01A.MOD", MediaInfo(created=datetime(2007, 7, 14, 19, 22, 5, 250000)))
    assert summer.local.isoformat() == "2007-07-14T19:22:05-04:00"
    assert summer.utc.isoformat() == "2007-07-14T23:22:05+00:00"
    winter = recorded("MOV01A.MOD", MediaInfo(created=datetime(2007, 1, 14, 19, 22, 5, 250000)), start_s=2.5)
    assert winter.local.isoformat() == "2007-01-14T19:22:07-05:00"
    assert winter.utc.isoformat() == "2007-01-15T00:22:07+00:00"


def test_recording_time_keeps_the_clips_own_tags():
    """A phone clip: Apple's local time and its own creation_time are both kept (a trim shifts both)."""
    from datetime import UTC, timedelta, timezone

    from listo.core.probe import MediaInfo, recorded
    from listo.core.video import date_tags

    phone = MediaInfo(
        created=datetime(2019, 8, 11, 19, 13, 57, tzinfo=timezone(timedelta(hours=2))),
        creation_time=datetime(2019, 8, 11, 17, 14, 12, tzinfo=UTC),  # cameras often stamp the end
    )
    assert date_tags(recorded("IMG_0001.MOV", phone)) == {
        "creation_time": "2019-08-11T17:14:12Z",
        "com.apple.quicktime.creationdate": "2019-08-11T19:13:57+0200",
    }
    assert date_tags(recorded("IMG_0001.MOV", phone, start_s=10.0)) == {
        "creation_time": "2019-08-11T17:14:22Z",
        "com.apple.quicktime.creationdate": "2019-08-11T19:14:07+0200",
    }


def test_recording_time_falls_back_to_the_files_date(tmp_path: Path):
    from listo.core.probe import MediaInfo, file_date, recorded

    f = tmp_path / "screen.mp4"
    f.write_bytes(b"x")
    shot = recorded(f, MediaInfo())
    assert shot.local.replace(tzinfo=None) == file_date(f, MediaInfo()).replace(microsecond=0)
    assert shot.local.utcoffset() is not None and shot.utc == shot.local
    assert recorded(tmp_path / "gone.mp4", MediaInfo()) is None
