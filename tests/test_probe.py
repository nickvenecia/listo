"""Reading files: frame rates and timecode math.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations


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
