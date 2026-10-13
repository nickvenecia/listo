"""Light and dark: Listo follows the computer's setting (or the one picked in Settings), even while it's open."""

from __future__ import annotations

import re

import pytest

from listo.ui.style import theme, tokens

COLOR = re.compile(r"^(#[0-9A-F]{6}|rgba\(\d+, \d+, \d+, [0-9.]+\))$")


@pytest.fixture
def back_to_dark():
    yield
    theme.use("dark", "")  # other tests expect the default look


def test_both_looks_name_every_color():
    assert set(tokens.DARK) == set(tokens.LIGHT) == set(tokens.COLORS)
    for name in tokens.COLORS:
        for look in (tokens.DARK, tokens.LIGHT):
            assert COLOR.match(look[name]), (name, look[name])
    # pictures sit on black in both looks (a monitor, not a page)
    for name in ("SCREEN", "SCREEN_TEXT", "SCREEN_FAINT"):
        assert tokens.DARK[name] == tokens.LIGHT[name], name


@pytest.mark.parametrize("look", ["dark", "light"])
def test_words_stay_readable_in_both_looks(look: str):
    c = tokens.LIGHT if look == "light" else tokens.DARK
    for fg, minimum in (("TEXT", 7.0), ("MUTED", 4.5), ("ACCENT", 3.0), ("BAD", 4.0), ("WARN", 3.0),
                        ("GOOD", 3.0), ("FAINT", 2.2)):  # fmt: skip
        for bg in ("PANEL", "CARD"):
            assert tokens.contrast(c[fg], c[bg]) >= minimum, (look, fg, bg)
    assert tokens.contrast(c["ON_ACCENT"], c["ACCENT"]) >= 3.0
    assert tokens.contrast(c["SCREEN_TEXT"], c["SCREEN"]) >= 4.5


def test_switching_rebuilds_the_look(tmp_path, back_to_dark):
    theme.use("light", "")
    assert tokens.SCHEME == "light" and theme.PANEL == tokens.LIGHT["PANEL"] == tokens.PANEL
    qss = theme.stylesheet(tmp_path)
    assert tokens.LIGHT["PANEL"] in qss and tokens.DARK["PANEL"] not in qss
    assert (
        tmp_path / f"chevron-light-{tokens.APP_ACCENT}.svg"
    ).exists()  # its own file (Qt keeps images by path)
    theme.use("dark")
    assert tokens.DARK["PANEL"] in theme.stylesheet(tmp_path) and tokens.DARK["MUTED"] == theme.MUTED


def test_icons_follow_the_look(qapp, back_to_dark):
    from PySide6.QtGui import QColor

    theme.use("dark")
    ic = theme.icon("plus", theme.TEXT)  # made once, drawn in whatever look is in use

    def drawn() -> QColor:
        img = ic.pixmap(32, 32).toImage()
        return img.pixelColor(img.width() // 2, img.height() // 2)  # the middle of the +

    assert drawn().lightness() > 200
    theme.use("light")
    assert drawn().lightness() < 60
    assert ic.pixmap(16, 16).deviceIndependentSize().width() == 16  # the size asked for


def test_window_follows_the_computer(qapp, tmp_path, monkeypatch, back_to_dark):
    from PySide6.QtCore import QSettings

    import listo.ui.panels.convert as sb
    import listo.ui.panels.export as ep
    import listo.ui.window.main_window as mw
    from listo import app as appmod

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb, ep):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    appmod.set_appearance(qapp, "system")
    w = mw.MainWindow()
    monkeypatch.setenv("LISTO_LOOK", "light")  # the computer switched to light mode
    appmod._system_changed(qapp)
    assert tokens.SCHEME == "light" and tokens.LIGHT["PANEL"] in qapp.styleSheet()
    w.sidebar.g_text.set_open(True)
    w.grab()  # everything repaints in the new look without errors
    monkeypatch.setenv("LISTO_LOOK", "dark")
    appmod._system_changed(qapp)
    assert tokens.SCHEME == "dark" and tokens.DARK["PANEL"] in qapp.styleSheet()
    appmod.set_appearance(qapp, "light")  # picked in Settings: the computer switching no longer changes it
    appmod._system_changed(qapp)
    assert tokens.SCHEME == "light"
    appmod.set_appearance(qapp, "system")
    w.close()
