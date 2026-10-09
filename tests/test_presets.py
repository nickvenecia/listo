"""Settings, recipes and per-file overrides.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

from listo.core.presets import Settings


def test_recipe_apply_and_match():
    s = Settings()
    vals = {
        "video_preset": "h264",
        "video_variant": {"h264": "standard"},
        "burn_timecode": True,
        "destination": "subfolder",
        "subfolder_name": "Review",
        "naming": "{name}_review",
    }
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
