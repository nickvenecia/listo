"""The accent color you pick: every choice gets a full, readable set of shades; Listo's own is marigold."""

from __future__ import annotations

import colorsys
import re

from listo.core import store
from listo.ui.style import tokens

COLOR = re.compile(r"^(#[0-9A-F]{6}|rgba\(\d+, \d+, \d+, [0-9.]+\))$")


def test_every_choice_has_every_shade_and_reads():
    keys = {k for k in tokens.DARK if k.startswith(("ACCENT", "DIVIDER", "CHIP")) or k == "ON_ACCENT"}
    for name, dark, light in tokens.ACCENTS.values():
        for base, scheme in ((dark, "dark"), (light, "light")):
            shades = tokens.accent_set(base, scheme)
            assert keys <= set(shades), name
            assert all(COLOR.match(v) for v in shades.values()), name
            assert tokens.contrast(shades["ON_ACCENT"], base) >= 3, (name, scheme)


def test_no_red_accent():
    for _name, dark, light in tokens.ACCENTS.values():
        for c in (dark, light):
            h, _l, sat = colorsys.rgb_to_hls(*(v / 255 for v in tokens._rgb(c)))
            assert sat < 0.25 or 18 <= h * 360 <= 340, c  # red means failed or delete


def test_marigold_is_listos_own():
    assert tokens.APP_ACCENT == "marigold"
    assert tokens.ACCENTS["marigold"][1:] == (tokens.DARK["ACCENT"], tokens.LIGHT["ACCENT"])


def test_use_switches_and_comes_back():
    try:
        tokens.use("dark", "green")
        assert tokens.ACCENTS["green"][1] == tokens.ACCENT and tokens.ON_ACCENT == tokens.DARK_ON_ACCENT
        tokens.use("light")  # keeps the accent
        assert tokens.ACCENTS["green"][2] == tokens.ACCENT
        tokens.use("dark", "")  # Listo's own: the hand-set shades, exactly
        assert tokens.DARK["ACCENT"] == tokens.ACCENT and tokens.DARK["DIVIDER"] == tokens.DIVIDER
        tokens.use("dark", "no-such-color")
        assert tokens.ACCENT_KEY == tokens.APP_ACCENT
    finally:
        tokens.use("dark", "")


def test_saved_look_and_accent_are_used_at_launch(qapp, data_folder):
    from listo.app import set_appearance, setup_app

    try:
        store.save_pref("appearance", "light")
        store.save_pref("accent", "purple")
        setup_app(qapp)
        assert tokens.SCHEME == "light" and tokens.ACCENTS["purple"][2] == tokens.ACCENT
        assert tokens.ACCENTS["purple"][2] in qapp.styleSheet()
    finally:
        set_appearance(qapp, "system", "")


def test_a_broken_settings_file_is_kept_aside(data_folder):
    data_folder.mkdir(parents=True, exist_ok=True)
    (data_folder / "settings.json").write_text("{ not json")
    assert store.prefs() == {}
    kept = [p.name for p in data_folder.iterdir() if p.name.startswith("settings.json.unreadable-")]
    assert kept  # never deleted
    store.save_pref("accent", "blue")
    assert store.prefs() == {"accent": "blue"}
