"""Burn-ins: clean and VHS styles, the clip's own date and a running clock.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from listo.core.engine import Conversion
from listo.core.presets import Settings
from listo.core.probe import _shot_time, file_date, probe
from listo.core.tools import capabilities
from listo.core.video import burn_filters, clock_text

from .helpers import HAS_FFMPEG, ff


def test_apple_local_time_wins_over_utc():
    t = _shot_time(
        {
            "creation_time": "2026-10-09T03:54:12Z",
            "com.apple.quicktime.creationdate": "2026-10-08T21:54:12-0600",
        },
        [],
    )
    assert t.isoformat() == "2026-10-08T21:54:12-06:00"


def test_placeholder_dates_are_ignored():
    assert (
        _shot_time({"creation_time": "1970-01-01T00:00:00Z"}, [{"creation_time": "1904-01-01T00:00:00Z"}])
        is None
    )


def test_clock_runs_from_the_wall_time():
    assert clock_text(datetime(1970, 1, 1, 0, 1, 40), "%H:%M") == "%{pts:gmtime:100:%H\\:%M}"


def test_vhs_layout_has_play_date_and_clock():
    from listo.core.probe import MediaInfo

    info = MediaInfo(
        kind="video", width=1920, height=1080, fps=24, rate="24/1", created=datetime(2026, 10, 8, 21, 54, 12)
    )
    s = Settings(burn_style="vhs", burn_datetime=True, burn_timecode=True, burn_filename=True)
    notes: list[str] = []
    joined = ",".join(burn_filters(info, s, (1920, 1080), False, "/x/IMG_3628.MOV", notes))
    assert "VCR_OSD_Mono" in joined and "PLAY" in joined and "OCT. 08 2026" in joined
    assert "gmtime" in joined and "timecode=" in joined and "IMG_3628.MOV" in joined


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("style", ["clean", "vhs"])
def test_burn_in_conversion_with_awkward_name(tmp_path: Path, style):
    src = tmp_path / "Nick's clip, take 2 [A].mov"
    ff(
        "-f", "lavfi", "-i", "testsrc2=s=640x360:r=24:d=0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-metadata", "creation_time=2026-10-09T03:54:12Z", str(src),
    )  # fmt: skip
    info = probe(src)
    assert file_date(src, info).year == 2026
    s = Settings(
        video_preset="h264", burn_style=style, burn_timecode=True, burn_filename=True, burn_datetime=True,
        naming="{name}_burn",
    )  # fmt: skip
    r = Conversion(str(src), info, s, capabilities(), set()).run()
    assert r.status == "done", r.message
    assert any("Burn-ins added" in n for n in r.notes)


def test_burn_ins_stay_inside_cinema_bars():
    from listo.core.frame import frame_plan
    from listo.core.probe import MediaInfo

    s = Settings(burn_style="vhs", burn_filename=True, aspect="2.35:1", aspect_fit="matte")
    _, w, h, area = frame_plan(1920, 1080, 1.0, s)
    assert area[1] > 0.1  # bars take the top and bottom
    info = MediaInfo(kind="video", width=1920, height=1080, fps=24, rate="24/1")
    joined = ",".join(burn_filters(info, s, (w, h), False, "/x/a.mov", [], area=area))
    assert f"y=h*{area[1]:.5f}+" in joined  # PLAY starts below the top bar
    assert f"h*{area[1] + area[3]:.5f}-" in joined  # file name ends above the bottom bar
