"""Light and dark: Listo follows the computer's setting, even while it's open."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from listo.ui.style import theme, tokens


@pytest.fixture
def back_to_dark():
    yield
    theme.use("dark")  # other tests expect the default look


def _lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    rgb = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_both_looks_name_every_color():
    assert set(tokens.DARK) == set(tokens.LIGHT) == set(tokens.COLORS)
    for name in tokens.COLORS:
        for look in (tokens.DARK, tokens.LIGHT):
            v = look[name]
            assert (v.startswith("#") and len(v) == 7) or v.startswith("rgba("), (name, v)
    # pictures sit on black in both looks (a monitor, not a page)
    for name in ("SCREEN", "SCREEN_TEXT", "SCREEN_FAINT", "ACCENT", "ON_ACCENT"):
        assert tokens.DARK[name] == tokens.LIGHT[name], name


@pytest.mark.parametrize("look", ["dark", "light"])
def test_words_stay_readable_in_both_looks(look: str):
    c = tokens.LIGHT if look == "light" else tokens.DARK
    for fg, minimum in (("TEXT", 7.0), ("MUTED", 4.5), ("ACCENT_INK", 4.5), ("BAD", 4.0), ("WARN", 4.0),
                        ("GOOD", 3.5), ("FAINT", 2.8)):  # fmt: skip
        for bg in ("BG", "PANEL", "CARD"):
            assert _contrast(c[fg], c[bg]) >= minimum, (look, fg, bg)
    assert _contrast(c["ON_ACCENT"], c["ACCENT"]) >= 7.0
    assert _contrast(c["SCREEN_TEXT"], c["SCREEN"]) >= 4.5
    assert _contrast(c["KNOB"], c["TRACK"]) >= 1.4  # an off switch's knob shows on its track


def test_switching_rebuilds_the_look(tmp_path, back_to_dark):
    theme.use("light")
    assert tokens.SCHEME == "light" and theme.BG == tokens.LIGHT["BG"] == tokens.BG
    qss = theme.stylesheet(tmp_path)
    assert tokens.LIGHT["BG"] in qss and tokens.DARK["BG"] not in qss
    assert (tmp_path / "chevron-light.svg").exists()  # its own image file (Qt keeps images by path)
    theme.use("dark")
    assert tokens.DARK["PANEL"] in theme.stylesheet(tmp_path) and tokens.DARK["MUTED"] == theme.MUTED


def test_icons_follow_the_look(back_to_dark):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    ic = theme.icon("plus", "TEXT")  # made once (cached), drawn in whatever look is in use

    def drawn() -> QColor:
        img = ic.pixmap(32, 32).toImage()
        return img.pixelColor(img.width() // 2, img.height() // 2)  # the middle of the +

    theme.use("dark")
    assert drawn().lightness() > 200
    theme.use("light")
    assert drawn().lightness() < 60
    assert ic.pixmap(16, 16).deviceIndependentSize().width() == 16  # the size asked for


def test_window_follows_the_computer(tmp_path, monkeypatch, back_to_dark):
    from PySide6.QtCore import QSettings

    import listo.ui.panels.convert as sb
    import listo.ui.panels.export as ep
    import listo.ui.window.main_window as mw
    from listo import app as appmod

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb, ep):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    monkeypatch.setattr(appmod, "data_dir", lambda: tmp_path)
    app = appmod.QApplication.instance() or appmod.QApplication([])
    w = mw.MainWindow()
    monkeypatch.setenv("LISTO_LOOK", "light")  # the computer switched to light mode
    appmod.follow_system(app)
    assert tokens.SCHEME == "light" and tokens.LIGHT["BG"] in app.styleSheet()
    w.sidebar.g_text.set_open(True)
    w.grab()  # everything repaints in the new look without errors
    monkeypatch.setenv("LISTO_LOOK", "dark")
    appmod.follow_system(app)
    assert tokens.SCHEME == "dark" and tokens.DARK["BG"] in app.styleSheet()
    w.close()
    app.setStyleSheet("")  # as the other tests expect
