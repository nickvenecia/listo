"""Burn-ins drawn by Listo itself (Pillow), so they work with ANY copy of ffmpeg.

Each line of text becomes a small transparent PNG laid over the video with ffmpeg's `overlay`
filter. Text that changes while the clip plays (timecode, the running clock) uses a "digit strip":
one PNG with the glyphs 0-9 stacked vertically, and a `crop` per digit position whose y-offset is
an expression of the frame's time, so ffmpeg picks the right digit on every frame.
`overlay` and `crop` are built into every ffmpeg, unlike `drawtext` (which needs FreeType and
HarfBuzz and is missing from e.g. Homebrew's ffmpeg).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from listo.core.frame import FULL, Area
from listo.core.presets import Settings
from listo.core.probe import MediaInfo

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
CLEAN_FONT = FONTS / "Inter-SemiBold.otf"
VHS_FONT = FONTS / "VCR_OSD_Mono.ttf"


# ---------------------------------------------------------------------------- plan
@dataclass
class Layer:
    """One image placed at (x, y). With `expr`, the image is a strip of equal cells and the
    cell shown is chosen per frame: crop y = cell_h * expr."""

    image: Path
    x: int
    y: int
    cell: tuple[int, int] | None = None
    expr: str = ""
    enable: str = ""  # ffmpeg expression: show only while true (blinking, first seconds)
    vcr: bool = (
        False  # drawn by the VCR (PLAY / STOP), not recorded on the tape: tape glitches don't touch it
    )


@dataclass
class BurnPlan:
    layers: list[Layer] = field(default_factory=list)
    folder: Path | None = None  # temp folder holding the PNGs (delete after the conversion)
    captions: Path | None = None  # ffconcat list: one image per caption, timed; drawn on top of everything
    caption_xy: tuple[int, int] = (0, 0)

    @property
    def empty(self) -> bool:
        return not self.layers and self.captions is None

    def input_args(self, rate: str, length: float = 0.0) -> list[str]:
        """ffmpeg input options for the images (in the order graph() numbers them). `length` = how long
        the picture runs: the looped images stop a second after it, so ffmpeg can never run forever
        (it did when a seek landed after the last frame: no picture, endless images)."""
        args: list[str] = []
        stop = ["-t", f"{length + 1:.3f}"] if length > 0 else []
        for img in self.images():
            args += ["-framerate", rate, "-loop", "1", *stop, "-i", str(img)]
        if self.captions:
            args += ["-f", "concat", "-safe", "0", "-i", str(self.captions)]
        return args

    def images(self) -> list[Path]:
        seen: list[Path] = []
        for layer in self.layers:
            if layer.image not in seen:
                seen.append(layer.image)
        return seen

    def graph(self, first_input: int, src_label: str, out_label: str, between=None) -> str:
        """Filtergraph text that lays every layer over [src_label] and names the result [out_label].
        Images are ffmpeg inputs first_input, first_input+1, ... in images() order.
        between(in_label, out_label) -> graph text, run after the tape's own layers (timecode, date,
        REC) and before the VCR's (PLAY / STOP) and the captions: tape glitches go there, so they
        tear what's on the tape but not what the VCR draws on top."""
        images = self.images()
        index = {img: first_input + i for i, img in enumerate(images)}
        uses: dict[Path, int] = {img: sum(1 for la in self.layers if la.image == img) for img in images}
        parts: list[str] = []
        pads: dict[Path, list[str]] = {}
        for img in images:
            n = uses[img]
            names = [f"i{index[img]}_{k}" for k in range(n)]
            pads[img] = names
            if n == 1:
                parts.append(f"[{index[img]}:v]format=rgba[{names[0]}]")
            else:
                parts.append(f"[{index[img]}:v]format=rgba,split={n}" + "".join(f"[{x}]" for x in names))
        cur = src_label
        n = 0

        def lay(la: Layer) -> None:
            nonlocal cur, n
            pad = pads[la.image].pop(0)
            if la.cell:
                cw, ch = la.cell
                parts.append(f"[{pad}]crop={cw}:{ch}:0:'{ch}*({la.expr})'[c{n}]")
                pad = f"c{n}"
            when = f":enable='{la.enable}'" if la.enable else ""
            parts.append(f"[{cur}][{pad}]overlay={la.x}:{la.y}:format=auto:shortest=1{when}[b{n}]")
            cur = f"b{n}"
            n += 1

        for la in self.layers:
            if not la.vcr:
                lay(la)
        if between is not None:
            parts.append(between(cur, "tape"))
            cur = "tape"
        for la in self.layers:
            if la.vcr:
                lay(la)
        if self.captions:
            return self._caption_graph(first_input + len(images), cur, out_label, parts)
        if cur == src_label:
            parts.append(f"[{cur}]null[{out_label}]")
        else:  # the last step writes straight to out_label
            last = parts.pop()
            parts.append(last[: last.rindex("[")] + f"[{out_label}]")
        return ";".join(p for p in parts if p)

    def _caption_graph(self, index: int, cur: str, out_label: str, parts: list[str]) -> str:
        x, y = self.caption_xy
        parts.append(f"[{index}:v]format=rgba[cap]")
        parts.append(f"[{cur}][cap]overlay={x}:{y}:format=auto:eof_action=pass[{out_label}]")
        return ";".join(parts)

    def cleanup(self) -> None:
        if self.folder and self.folder.exists():
            for p in self.folder.iterdir():
                p.unlink(missing_ok=True)
            self.folder.rmdir()


# ---------------------------------------------------------------------------- expressions
def frame_index(rate: Fraction) -> str:
    """Frames since the start of the output, from the frame time t."""
    return f"floor(t*{float(rate):.10f}+0.5)"


def tc_to_frames(tc: str, nominal: int, drop: int) -> int:
    h, m, s, f = (int(x) for x in tc.replace(";", ":").split(":"))
    total_min = h * 60 + m
    return ((total_min * 60 + s) * nominal + f) - drop * (total_min - total_min // 10)


def timecode_fields(tc: str, rate: Fraction) -> tuple[list[str], bool]:
    """[hours, minutes, seconds, frames] as ffmpeg expressions, and whether it's drop-frame."""
    nominal = round(rate)
    drop = (nominal // 30) * 2 if ";" in tc and nominal in (30, 60) else 0
    start = tc_to_frames(tc, nominal, drop)
    f = f"({start}+{frame_index(rate)})"
    if drop:  # real frame count -> the frame number drop-frame timecode displays
        per10, per1 = nominal * 600 - drop * 9, nominal * 60 - drop
        r = f"mod({f},{per10})"
        f = f"({f}+{drop * 9}*floor({f}/{per10})+if(gte({r},{drop}),{drop}*floor(({r}-{drop})/{per1}),0))"
    n = nominal
    return [
        f"mod(floor({f}/{n * 3600}),24)",
        f"mod(floor({f}/{n * 60}),60)",
        f"mod(floor({f}/{n}),60)",
        f"mod({f},{n})",
    ], bool(drop)


def clock_fields(start: datetime) -> tuple[str, str, str, str]:
    """(hour 0-23, minute, second, is-PM) expressions for a clock starting at `start` (wall time)."""
    base = start.hour * 3600 + start.minute * 60 + start.second + start.microsecond / 1e6
    sec = f"floor({base:.3f}+t)"
    h24 = f"mod(floor({sec}/3600),24)"
    return h24, f"mod(floor({sec}/60),60)", f"mod({sec},60)", f"gte({h24},12)"


def tens(x: str) -> str:
    return f"floor(({x})/10)"


def ones(x: str) -> str:
    return f"mod({x},10)"


# ---------------------------------------------------------------------------- drawing
@dataclass
class Look:
    font: ImageFont.FreeTypeFont
    color: tuple[int, int, int, int]
    pad: int  # transparent margin around the text (room for outline / box)
    box: tuple[int, int, int, int] | None = None  # clean style: box behind the text
    outline: int = 0  # hard black edge around every letter
    soften: float = 0.0  # blur radius: tape and CRT softness
    fringe: int = 0  # colour fringing (chromatic aberration), in pixels

    @property
    def line_h(self) -> int:
        ascent, descent = self.font.getmetrics()
        return ascent + descent


def _look(style: str, size: int) -> Look:
    if style == "vhs":
        # Like a VCR / camcorder on-screen display: solid, outlined, a touch soft, slightly mis-registered.
        return Look(
            ImageFont.truetype(str(VHS_FONT), size), (242, 242, 236, 255), max(4, size // 5),
            outline=max(1, round(size / 18)), soften=max(0.5, size / 70), fringe=max(1, round(size / 90)),
        )  # fmt: skip
    return Look(
        ImageFont.truetype(str(CLEAN_FONT), size), (255, 255, 255, 255), max(4, size // 3), box=(0, 0, 0, 140)
    )


def _finish(text_layer: Image.Image, look: Look) -> Image.Image:
    """Add the style's fringe / softness / box under (and to) a layer of outlined text."""
    out = Image.new("RGBA", text_layer.size, (0, 0, 0, 0))
    if look.box:
        out.paste(Image.new("RGBA", text_layer.size, look.box), (0, 0))
    if look.fringe:
        alpha = text_layer.getchannel("A").point(
            lambda a: a * 0.3
        )  # a hint, like slightly mis-registered tape
        for color, dx in (((255, 70, 70), look.fringe), ((70, 150, 255), -look.fringe)):
            ghost = Image.new("RGBA", text_layer.size, (*color, 0))
            ghost.putalpha(alpha)
            out.alpha_composite(ghost, (max(0, dx), 0), (max(0, -dx), 0))
    out.alpha_composite(text_layer)
    if look.soften:
        out = out.filter(ImageFilter.GaussianBlur(look.soften))
    return out


def _text_image(parts: list[tuple[str, float]], width: int, look: Look) -> Image.Image:
    """Draw text pieces at x positions into one padded image."""
    layer = Image.new("RGBA", (width + 2 * look.pad, look.line_h + 2 * look.pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for text, x in parts:
        d.text(
            (look.pad + x, look.pad), text, font=look.font, fill=look.color,
            stroke_width=look.outline, stroke_fill=(0, 0, 0, 255),
        )  # fmt: skip
    return _finish(layer, look)


def _strip(glyphs: list[str], cell_w: int, look: Look) -> tuple[Image.Image, tuple[int, int]]:
    """Glyphs stacked vertically in equal cells (each centred), with no box (the line's box is under it)."""
    plain = Look(look.font, look.color, look.pad, None, look.outline, look.soften, look.fringe)
    cw, ch = cell_w + 2 * look.pad, look.line_h + 2 * look.pad
    strip = Image.new("RGBA", (cw, ch * len(glyphs)), (0, 0, 0, 0))
    for i, g in enumerate(glyphs):
        x = (cell_w - look.font.getlength(g)) / 2
        strip.alpha_composite(_text_image([(g, x)], cell_w, plain), (0, i * ch))
    return strip, (cw, ch)


@dataclass
class _Slot:
    glyphs: list[str]
    expr: str


Token = str | _Slot


class _Builder:
    def __init__(self, folder: Path, frame: tuple[int, int], area: Area):
        self.folder = folder
        self.W, self.H = frame
        ax, ay, aw, ah = area
        self.left, self.top = round(self.W * ax), round(self.H * ay)
        self.right, self.bottom = round(self.W * (ax + aw)), round(self.H * (ay + ah))
        self.layers: list[Layer] = []
        self._strips: dict[tuple, tuple[Path, tuple[int, int]]] = {}
        self._n = 0

    def _save(self, img: Image.Image) -> Path:
        self._n += 1
        p = self.folder / f"burn{self._n}.png"
        img.save(p)
        return p

    def line(self, tokens: list[Token], look: Look, anchor: str, mx: int, my: int) -> int:
        """Place one line in a corner of the picture ('tl', 'tr', 'bl', 'br'). Returns its height."""
        digit_w = max(look.font.getlength(str(d)) for d in range(10))
        x, parts, slots = 0.0, [], []
        for tok in tokens:
            if isinstance(tok, _Slot):
                w = digit_w if tok.glyphs[0].isdigit() else max(look.font.getlength(g) for g in tok.glyphs)
                slots.append((tok, x, w))
                x += w
            else:
                parts.append((tok, x))
                x += look.font.getlength(tok)
        width = round(x)
        bg = _text_image(parts, width, look)
        # Text edge sits mx / my inside the picture; the padding (glow / box) hangs outside it.
        ox = self.left + mx - look.pad if anchor[1] == "l" else self.right - mx - width - look.pad
        oy = self.top + my - look.pad if anchor[0] == "t" else self.bottom - my - look.line_h - look.pad
        self.layers.append(Layer(self._save(bg), ox, oy))
        for slot, sx, w in slots:
            key = (tuple(slot.glyphs), round(w), id(look))
            if key not in self._strips:
                img, cell = _strip(slot.glyphs, round(w), look)
                self._strips[key] = (self._save(img), cell)
            path, cell = self._strips[key]
            self.layers.append(Layer(path, ox + round(sx), oy, cell, slot.expr))
        return look.line_h

    def badge(self, kind: str, look: Look, mx: int, my: int, enable: str = "") -> None:
        """Top-left VCR / camcorder badge. PLAY ► blinks for the first seconds, then goes away (like
        a VCR after pressing play); ● REC stays, with its red dot blinking (like a camcorder);
        STOP ■ shows steady (like a VCR after pressing stop). `enable` overrides when it shows."""
        start = len(self.layers)
        if kind == "play":
            self.line(["PLAY ►"], look, "tl", mx, my)
            for la in self.layers[start:]:
                la.enable = enable or "lt(t,4)*lt(mod(t,1),0.7)"
                la.vcr = True
        elif kind == "stop":
            self.line(["STOP"], look, "tl", mx, my)
            ascent = look.font.getmetrics()[0]
            top = look.font.getbbox("S", anchor="ls")[1]  # cap height (negative, from the baseline)
            d = max(6, round(-top * 0.8))
            sq = Image.new("RGBA", (d + 2 * look.pad, d + 2 * look.pad), (0, 0, 0, 0))
            ImageDraw.Draw(sq).rectangle(
                (look.pad, look.pad, look.pad + d, look.pad + d),
                fill=look.color, outline=(0, 0, 0, 255), width=max(1, look.outline),
            )  # fmt: skip
            if look.soften:
                sq = sq.filter(ImageFilter.GaussianBlur(look.soften))
            x = self.left + mx + round(look.font.getlength("STOP ")) - look.pad
            y = self.top + my + ascent + top + (-top - d) // 2 - look.pad
            self.layers.append(Layer(self._save(sq), x, y))
            for la in self.layers[start:]:
                la.enable = enable
                la.vcr = True
        elif kind == "rec":
            ascent = look.font.getmetrics()[0]
            top = look.font.getbbox("R", anchor="ls")[1]  # cap height (negative, from the baseline)
            d = max(6, round(-top * 0.95))
            gap = round(d * 0.45)
            self.line(["REC"], look, "tl", mx + d + gap, my)
            dot = Image.new("RGBA", (d + 2 * look.pad, d + 2 * look.pad), (0, 0, 0, 0))
            ImageDraw.Draw(dot).ellipse(
                (look.pad, look.pad, look.pad + d, look.pad + d),
                fill=(230, 32, 40, 255), outline=(0, 0, 0, 255), width=max(1, look.outline),
            )  # fmt: skip
            if look.soften:
                dot = dot.filter(ImageFilter.GaussianBlur(look.soften))
            # centre the dot on the capital letters
            y = self.top + my + ascent + top + (-top - d) // 2 - look.pad
            self.layers.append(
                Layer(self._save(dot), self.left + mx - look.pad, y, enable="lt(mod(t,1),0.6)")
            )


DIGITS = [str(d) for d in range(10)]


def _two(expr: str) -> list[Token]:
    return [_Slot(DIGITS, tens(expr)), _Slot(DIGITS, ones(expr))]


@dataclass
class Marks:
    """VCR moments around a tape-style video: how long PLAY blinks from the start (the rest of it was
    on the blue screen before), and when STOP shows at the end (the last frames, then the blue screen)."""

    play_until: float = 4.0
    stop_at: float | None = None


def _vhs_metrics(frame: tuple[int, int], area: Area) -> tuple[Look, int, int]:
    W, H = frame
    _, _, aw, ah = area
    ref = min(W * aw, H * ah) or 1080
    size = max(12, round(ref / 15))
    return _look("vhs", size), round(ref * 0.09), round(ref * 0.07)


def badge_plan(kind: str, frame: tuple[int, int], area: Area, enable: str) -> BurnPlan:
    """Just the VCR badge (PLAY / STOP) in the VHS look, for the tape blue screen."""
    folder = Path(tempfile.mkdtemp(prefix="listo-burn-"))
    b = _Builder(folder, frame, area if area else FULL)
    look, mx, my = _vhs_metrics(frame, area if area else FULL)
    b.badge(kind, look, mx, my, enable)
    return BurnPlan(b.layers, folder)


def plan(
    info: MediaInfo,
    s: Settings,
    frame: tuple[int, int],
    area: Area,
    src: str,
    shot: datetime | None,
    tc: str,
    rate: Fraction | None,
    cues: list | None = None,
    marks: Marks | None = None,
) -> BurnPlan:
    """Render the burn-ins (and captions) for one conversion. `shot` is the wall-clock time of the
    first frame, `tc` the timecode of the first frame (with `rate` the output frame rate), `cues`
    the captions already shifted to the output's own timeline."""
    W, H = frame
    if not W or not H or not (s.burns or cues):
        return BurnPlan()
    folder = Path(tempfile.mkdtemp(prefix="listo-burn-"))
    b = _Builder(folder, frame, area if area else FULL)
    _, _, aw, ah = area
    ref = min(W * aw, H * ah) or 1080
    timecode: list[Token] = []
    if s.burn_timecode and tc and rate:
        (hh, mm, ss, ff), df = timecode_fields(tc, rate)
        timecode = [*_two(hh), ":", *_two(mm), ":", *_two(ss), ";" if df else ":", *_two(ff)]

    if s.burns and s.burn_style == "vhs":
        size = max(12, round(ref / 15))
        look = _look("vhs", size)
        mx, my = round(ref * 0.09), round(ref * 0.07)
        gap = round(size * 0.25)
        marks = marks or Marks()
        if s.burn_badge == "play":
            if marks.play_until > 0:
                b.badge("play", look, mx, my, f"lt(t,{marks.play_until:.3f})*lt(mod(t,1),0.7)")
        else:
            b.badge(s.burn_badge, look, mx, my)
        if marks.stop_at is not None:
            b.badge("stop", look, mx, my, f"gte(t,{marks.stop_at:.3f})")
        if timecode:
            b.line(timecode, look, "tr", mx, my)
        if s.burn_datetime and shot:
            h24, m, sec, pm = clock_fields(shot)
            h12 = f"(mod({h24}+11,12)+1)"
            date_h = b.line([shot.strftime("%b. %d %Y").upper()], look, "bl", mx, my)
            b.line(
                [_Slot(["AM", "PM"], pm), " ", *_two(h12), ":", *_two(m), ":", *_two(sec)],
                look,
                "bl",
                mx,
                my + date_h + gap,
            )
        if s.burn_filename:
            b.line([Path(src).name], _look("vhs", max(10, round(size * 0.6))), "br", mx, my)
    elif s.burns:
        size = max(12, round(ref / 26))
        look = _look("clean", size)
        pad = max(8, size)
        if s.burn_filename:
            b.line([Path(src).name], look, "bl", pad, pad)
        if timecode:
            b.line(timecode, look, "br", pad, pad)
        if s.burn_datetime and shot:
            h24, m, sec, _ = clock_fields(shot)
            b.line(
                [shot.strftime("%Y-%m-%d  "), *_two(h24), ":", *_two(m), ":", *_two(sec)],
                look,
                "tl",
                pad,
                pad,
            )
    bp = BurnPlan(b.layers, folder)
    if cues:
        bp.captions, bp.caption_xy = caption_track(cues, s, frame, folder)
    return bp


# ---------------------------------------------------------------------------- captions
CAPTION_SIZE = {"small": 24, "medium": 19, "large": 15}  # short edge / n


def _caption_look(s: Settings, size: int) -> Look:
    if s.caption_style == "vhs":
        look = _look("vhs", size)
        if s.caption_box:  # closed-caption look: solid black behind each line, crisp letters
            look.outline = 0
        return look
    font = ImageFont.truetype(str(CLEAN_FONT), size)
    return Look(
        font, (255, 255, 255, 255), max(4, size // 3), outline=0 if s.caption_box else max(2, size // 12)
    )


def _caption_image(
    lines: list[str], look: Look, box: bool, band: tuple[int, int], line_step: int
) -> Image.Image:
    """Lines centred and stacked from the bottom of a fixed-size transparent band."""
    bw, bh = band
    layer = Image.new("RGBA", band, (0, 0, 0, 0))
    plain = Look(look.font, look.color, look.pad, None, look.outline, 0.0, 0)
    y = bh - look.pad - len(lines) * line_step
    for text in lines:
        w = look.font.getlength(text)
        x = (bw - w) / 2
        if box:
            bpad = max(4, look.font.size // 4)
            ImageDraw.Draw(layer).rectangle(
                (round(x - bpad), y - bpad // 3, round(x + w + bpad), y + line_step - bpad // 3),
                fill=(0, 0, 0, 255 if look.fringe else 190),
            )  # fmt: skip
        line_img = _text_image([(text, 0.0)], round(w), plain)
        layer.alpha_composite(line_img, (round(x) - look.pad, y - look.pad))
        y += line_step
    look_fx = Look(look.font, look.color, 0, None, 0, look.soften, look.fringe)
    return _finish(layer, look_fx) if (look.soften or look.fringe) else layer


def caption_track(
    cues: list, s: Settings, frame: tuple[int, int], folder: Path
) -> tuple[Path, tuple[int, int]]:
    """One image per caption plus an ffconcat list that shows each for its time.
    Returns (list file, where the band goes). Captions sit bottom-centre of the whole frame,
    over bars and burn-ins."""
    W, H = frame
    look, line_step = _caption_setup(s, frame)
    wrapped = [caption_lines(c.text, s) for c in cues]
    widest = max((look.font.getlength(t) for ls in wrapped for t in ls), default=0)
    most = max((len(ls) for ls in wrapped), default=1)
    band = (min(W, round(widest) + 4 * look.pad), most * line_step + 2 * look.pad)
    blank = folder / "cap_blank.png"
    Image.new("RGBA", band, (0, 0, 0, 0)).save(blank)

    def q(p: Path) -> str:
        return "'" + str(p).replace("'", "'\\''") + "'"

    entries: list[tuple[Path, float]] = []
    t = 0.0
    for i, (c, ls) in enumerate(zip(cues, wrapped, strict=True)):
        if c.start > t + 0.001:
            entries.append((blank, c.start - t))
        img = folder / f"cap{i}.png"
        _caption_image(ls, look, s.caption_box, band, line_step).save(img)
        entries.append((img, max(0.04, c.end - max(c.start, t))))
        t = max(t, c.end)
    entries.append((blank, 1.0))
    lst = folder / "captions.ffconcat"
    lines = ["ffconcat version 1.0"]
    for path, dur in entries:
        lines += [f"file {q(path)}", f"duration {dur:.3f}"]
    lines.append(f"file {q(blank)}")  # (the concat reader needs the last file twice)
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    margin = round(H * 0.06)
    return lst, ((W - band[0]) // 2, H - margin - band[1])


def _caption_setup(s: Settings, frame: tuple[int, int]) -> tuple[Look, int]:
    size = max(12, round(min(frame) / CAPTION_SIZE.get(s.caption_size, 19)))
    look = _caption_look(s, size)
    return look, round(look.line_h * 1.08)


def caption_lines(text: str, s: Settings) -> list[str]:
    """How a caption reads on screen. Closed captions on tape were ALL CAPS (white on black);
    the clean look keeps the words as spoken."""
    from listo.core.captions import wrap

    return wrap(text.upper() if s.caption_style == "vhs" else text, s.caption_words)


def caption_still(text: str, s: Settings, frame: tuple[int, int]) -> tuple[Image.Image, tuple[int, int]]:
    """One caption exactly as it's burned in, and where it goes on a frame of this size
    (the caption check draws it over the playing clip)."""
    W, H = frame
    look, line_step = _caption_setup(s, frame)
    lines = caption_lines(text, s)
    widest = max((look.font.getlength(t) for t in lines), default=0)
    band = (min(W, round(widest) + 4 * look.pad), max(1, len(lines)) * line_step + 2 * look.pad)
    img = _caption_image(lines, look, s.caption_box, band, line_step)
    return img, ((W - band[0]) // 2, H - round(H * 0.06) - band[1])


def shot_start(src: str, info: MediaInfo, start_s: float) -> datetime:
    from listo.core.probe import file_date

    return file_date(src, info) + timedelta(seconds=start_s)
