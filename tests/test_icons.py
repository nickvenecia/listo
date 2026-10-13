"""Every icon the code names exists (a missing one only shows up as a crash when its button is drawn), and every
icon drawn is still named somewhere (no leftovers from older designs)."""

from __future__ import annotations

import re
from pathlib import Path

from listo.ui.style import theme

ROOT = Path(__file__).resolve().parent.parent / "listo"
CALLS = re.compile(
    r'(?:icon|menu_icon|pixmap|IconLabel|circle_button|header_icon|set_icon)\(\s*"([a-z0-9-]+)"'
)


def _code() -> str:
    return "\n".join(f.read_text() for f in ROOT.rglob("*.py") if f.name != "theme.py")


def test_every_named_icon_exists():
    missing = sorted(n for n in set(CALLS.findall(_code())) if n not in theme._SVG)
    assert not missing, missing


def test_every_icon_is_used():
    code = _code()
    unused = sorted(n for n in theme._SVG if f'"{n}"' not in code)
    assert not unused, unused
