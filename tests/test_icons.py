"""Every icon the code names exists (a missing one only shows up as a crash when its button is drawn)."""

from __future__ import annotations

import re
from pathlib import Path

from listo.ui.style import theme

ROOT = Path(__file__).resolve().parent.parent / "listo"
CALLS = re.compile(
    r'(?:icon|menu_icon|pixmap|IconLabel|circle_button|icon_button|header_icon|set_icon|add_chip)\(\s*"([a-z0-9-]+)"'
)


def test_every_named_icon_exists():
    names = set()
    for f in ROOT.rglob("*.py"):
        names |= set(CALLS.findall(f.read_text()))
    missing = sorted(n for n in names if n not in theme._SVG)
    assert not missing, missing
