"""Draw the app icon (listo/assets/icon.png): "l." on a dark tile, the full stop in the accent.

    python scripts/make_icon.py

The build turns the PNG into the Mac .icns and Windows .ico (listo.spec). Colors come from the design
tokens and the letters from the bundled Inter Display Bold, so the icon always matches the app.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from listo.ui.style.tokens import ACCENT, TEXT  # noqa: E402

SIZE = 1024
TILE = 824  # Apple's icon grid: an 824 px rounded square centred on 1024 (room for the shadow)
RADIUS = 185
TILE_TOP = "#1E1E22"  # a soft top-to-bottom shade of the app background (BG #111113)
TILE_BOTTOM = "#121214"
FONT = ROOT / "listo" / "assets" / "fonts" / "InterDisplay-Bold.otf"


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def draw(size: int = SIZE) -> Image.Image:
    s = size / SIZE
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    off = round((SIZE - TILE) / 2 * s)
    tile = round(TILE * s)

    # the tile, with a gentle vertical shade
    top, bottom = _hex(TILE_TOP), _hex(TILE_BOTTOM)
    shade = Image.new("RGBA", (tile, tile))
    px = ImageDraw.Draw(shade)
    for y in range(tile):
        f = y / max(1, tile - 1)
        px.line(
            [(0, y), (tile, y)], fill=tuple(round(a + (b - a) * f) for a, b in zip(top, bottom, strict=True))
        )
    mask = Image.new("L", (tile, tile), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, tile - 1, tile - 1), round(RADIUS * s), fill=255)
    img.paste(shade, (off, off), mask)
    # a hairline edge so it holds up on dark docks
    ImageDraw.Draw(img).rounded_rectangle(
        (off, off, off + tile - 1, off + tile - 1),
        round(RADIUS * s),
        outline=(255, 255, 255, 22),
        width=max(1, round(3 * s)),
    )

    # "l." in the text color, the full stop in the accent; sized by the letter's height, centred on its ink
    letter, dot = "l", "."
    font = ImageFont.truetype(str(FONT), round(560 * s))
    d = ImageDraw.Draw(img)
    left, top_px, right, bottom_px = font.getbbox(letter + dot)
    w_letter = font.getlength(letter)
    x = (size - (right - left)) / 2 - left
    y = (size - (bottom_px - top_px)) / 2 - top_px
    d.text((x, y), letter, font=font, fill=_hex(TEXT))
    d.text((x + w_letter, y), dot, font=font, fill=_hex(ACCENT))
    return img


if __name__ == "__main__":
    out = ROOT / "listo" / "assets" / "icon.png"
    draw().save(out)
    print(f"wrote {out}")
