"""Picture shape: anamorphic desqueeze, aspect-ratio crop / black bars, and resizing.

One function decides the output frame so the converter (video.build) and the file-name
preview ({res}) always agree.
"""

from __future__ import annotations

from listo.core.presets import Settings

ASPECTS = {
    "16:9": 16 / 9,
    "8:5": 8 / 5,
    "4:3": 4 / 3,
    "1:1": 1.0,
    "4:5": 4 / 5,
    "9:16": 9 / 16,
    "1.85:1": 1.85,
    "2:1": 2.0,
    "2.35:1": 2.35,
    "2.39:1": 2.39,
}
MAX_W = 8192  # widest frame common encoders accept


def _even(x: float) -> int:
    return max(2, round(x / 2) * 2)


Area = tuple[float, float, float, float]  # x, y, width, height as fractions of the frame
FULL: Area = (0.0, 0.0, 1.0, 1.0)


def frame_filters(w: int, h: int, sar: float, s: Settings) -> tuple[list[str], int, int]:
    """(ffmpeg filters, width, height) for desqueeze + aspect ratio, before any resize."""
    filters, w, h, _ = frame_plan(w, h, sar, s)
    return filters, w, h


def frame_plan(w: int, h: int, sar: float, s: Settings) -> tuple[list[str], int, int, Area]:
    """(filters, width, height, picture area). The area is where the picture is inside the frame,
    leaving out black bars and cinema bars, so burn-ins can stay inside it.

    w, h are the picture as stored (after phone rotation); sar is its pixel shape."""
    filters: list[str] = []
    if not w or not h:
        return filters, w, h, FULL
    try:
        squeeze = float(s.desqueeze)
    except ValueError:
        squeeze = 1.0
    reshaping = squeeze != 1.0 or s.aspect in ASPECTS or s.video_resize != "orig"
    if reshaping and abs(sar - 1) > 1e-3:
        squeeze *= sar  # make pixels square first (DV / HDV), or every size and ratio below would be off
    if abs(squeeze - 1) > 1e-3:
        nw, nh = w * squeeze, float(h)
        if nw > MAX_W:  # too wide to encode: shrink the height instead of growing the width
            nw, nh = MAX_W, h * MAX_W / nw
        w, h = _even(nw), _even(nh)
        filters.append(f"scale={w}:{h}:flags=lanczos,setsar=1")
    ratio = ASPECTS.get(s.aspect)
    area = FULL
    if ratio and abs(w / h - ratio) > 0.01:
        if s.aspect_fit == "matte":  # cinema bars drawn over the picture; the frame keeps its size
            boxes, area = _matte(w, h, ratio, s.matte_opacity)
            return filters + boxes, w, h, area
        if s.aspect_fit == "bars":
            nw, nh = (w, _even(w / ratio)) if w / h > ratio else (_even(h * ratio), h)
            nw, nh = max(nw, w), max(nh, h)
            filters.append(f"pad={nw}:{nh}:(ow-iw)/2:(oh-ih)/2:color=black")
            area = ((nw - w) / 2 / nw, (nh - h) / 2 / nh, w / nw, h / nh)
        else:  # crop to fill, centered: the whole frame is picture
            nw, nh = (_even(h * ratio), h) if w / h > ratio else (w, _even(w / ratio))
            nw, nh = min(nw, w - w % 2), min(nh, h - h % 2)
            filters.append(f"crop={nw}:{nh}")
        w, h = nw, nh
    return filters, w, h, area


def _matte(w: int, h: int, ratio: float, opacity: int) -> tuple[list[str], Area]:
    alpha = max(0, min(100, int(opacity))) / 100
    color = f"black@{alpha:.2f}"
    if w / h < ratio:  # wider shape: bars top and bottom (letterbox)
        bar = round((h - w / ratio) / 2)
        boxes = [f"x=0:y=0:w=iw:h={bar}", f"x=0:y=ih-{bar}:w=iw:h={bar}"]
        area = (0.0, bar / h, 1.0, 1 - 2 * bar / h)
    else:  # narrower shape: bars left and right (pillarbox)
        bar = round((w - h * ratio) / 2)
        boxes = [f"x=0:y=0:w={bar}:h=ih", f"x=iw-{bar}:y=0:w={bar}:h=ih"]
        area = (bar / w, 0.0, 1 - 2 * bar / w, 1.0)
    if alpha <= 0 or bar <= 0:
        return [], FULL
    return [f"drawbox={b}:color={color}:t=fill" for b in boxes], area


def resized(w: int, h: int, resize: str) -> tuple[int, int]:
    """Apply a Size choice. Numbers mean the SHORT edge (1080 = 1920×1080 or 1080×1920),
    scaling down or up (e.g. 720×480 4:3 -> 1440×1080)."""
    if resize == "half":
        return _even(w / 2), _even(h / 2)
    if resize == "orig" or not w or not h:
        return w, h
    target = int(resize)
    short = min(w, h)
    if short == target:
        return w, h
    k = target / short
    return _even(w * k), _even(h * k)
