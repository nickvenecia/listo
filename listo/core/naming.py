"""Output naming: templates like "{name}_{preset}_{date}" and never clobbering originals."""

from __future__ import annotations

import os
import re
from pathlib import Path

from listo.core.frame import frame_filters, resized
from listo.core.presets import Settings, output_ext, preset_tag
from listo.core.probe import MediaInfo, file_date

TOKENS: tuple[tuple[str, str], ...] = (
    ("name", "Original file name"),
    ("preset", "Output format, e.g. prores422"),
    ("date", "Shoot date, 2026-10-08"),
    ("time", "Shoot time, 143005"),
    ("res", "Output size, 1920x1080"),
    ("height", "Output height, 1080p"),
    ("fps", "Frame rate, 23.976"),
    ("n", "Counter, 001"),
    ("folder", "Name of the folder it came from"),
    ("ext", "Original extension, mov"),
)

_TOKEN_RE = re.compile(r"\{([a-zA-Z]+)\}")
_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize(name: str) -> str:
    name = _BAD_CHARS.sub("-", name).strip().rstrip(". ")
    return name[:200] or "untitled"


def render(template: str, ctx: dict[str, str]) -> str:
    empty = "\x00"

    def sub(m: re.Match) -> str:
        key = m.group(1).lower()
        if key not in ctx:
            return m.group(0)
        return str(ctx[key]) or empty

    out = _TOKEN_RE.sub(sub, template or "{name}")
    # An empty token (e.g. {res} on an audio file) takes one neighbouring separator with it,
    # so "{name}_{res}_{date}" doesn't become "name__date". The original name is never touched.
    out = re.sub(
        r"([_\-. ]*)\x00([_\-. ]*)",
        lambda m: m.group(1) if (m.group(1) and m.group(2)) else "",
        out,
    )
    out = sanitize(out)
    return out if out.strip("-_ .") else sanitize(ctx.get("name", "untitled"))


def output_size(info: MediaInfo | None, s: Settings, kind: str) -> tuple[int, int]:
    if not info or not info.width or not info.height:
        return 0, 0
    w, h = info.width, info.height
    if kind == "photo":
        r = s.photo_resize
        if r != "orig":
            target = int(r)
            long_edge = max(w, h)
            if long_edge > target:
                scale = target / long_edge
                w, h = round(w * scale), round(h * scale)
        return w, h
    preset = s.video_preset
    if preset == "rewrap":
        return w - (w % 2), h - (h % 2)
    _, w, h = frame_filters(w, h, info.sar, s)
    if preset == "proxy":
        w, h = w // 2, h // 2
    elif preset == "gif":
        target_w = int(s.variant_for("gif"))
        if w > target_w:
            h, w = round(h * target_w / w), target_w
    else:
        w, h = resized(w, h, s.video_resize)
    return w - (w % 2), h - (h % 2)


def make_context(
    src: str | Path, info: MediaInfo | None, s: Settings, kind: str, n: int = 1
) -> dict[str, str]:
    p = Path(src)
    try:
        d = file_date(p, info)
    except OSError:
        from datetime import datetime

        d = datetime.now()
    w, h = output_size(info, s, kind)
    fps = ""
    if info and info.fps:
        fps = f"{info.fps:.3f}".rstrip("0").rstrip(".")
        if info.interlaced and s.deinterlace == "smooth" and s.video_preset not in ("rewrap", "gif"):
            fps = f"{info.fps * 2:.3f}".rstrip("0").rstrip(".")
    return {
        "name": p.stem,
        "ext": p.suffix.lstrip("."),
        "preset": preset_tag(kind, s),
        "date": d.strftime("%Y-%m-%d"),
        "time": d.strftime("%H%M%S"),
        "res": f"{w}x{h}" if w else "",
        "height": f"{h}p" if h else "",
        "fps": fps,
        "n": f"{n:03d}",
        "folder": p.parent.name,
    }


def output_dir(src: str | Path, s: Settings, kind: str) -> Path:
    parent = Path(src).parent
    proxy = kind == "video" and s.video_preset == "proxy"
    if s.destination == "folder" and s.dest_folder:
        base = Path(s.dest_folder)
    elif s.destination == "subfolder":
        base = parent / sanitize(s.subfolder_name or "Listo")
    else:
        base = parent
    return base / "Proxy" if proxy and s.destination == "source" else base


def planned_name(src: str | Path, info: MediaInfo | None, s: Settings, kind: str, n: int = 1) -> str:
    base = render(s.naming, make_context(src, info, s, kind, n))
    return f"{base}.{output_ext(kind, s)}"


def _key(p: Path) -> str:
    # macOS and Windows disks ignore case, so compare case-insensitively everywhere.
    return os.path.normcase(os.path.abspath(str(p))).lower()


def _same_file(a: Path, b: Path) -> bool:
    if _key(a) == _key(b):
        return True
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except OSError:
        return False


def resolve_output(src: str | Path, target: Path, policy: str, reserved: set[str]) -> tuple[Path | None, str]:
    """Pick the final output path. Returns (path or None to skip, note for the UI).

    The original is never overwritten, whatever the policy says.
    """
    src = Path(src)

    def taken(p: Path) -> bool:
        return p.exists() or _key(p) in reserved

    extra: list[str] = []
    if _same_file(target, src):
        policy = "number"
    elif _key(target) in reserved:
        # Another file in this batch already has this name (e.g. two MOV01A.MOD from different
        # PRG folders, or the original itself): never skip or replace it. Its folder tells them apart.
        policy = "number"
        from_elsewhere = _key(src.parent) != _key(target.parent)
        if from_elsewhere and src.parent.name and src.parent.name.lower() not in target.stem.lower():
            extra.append(f"{target.stem}_{src.parent.name}")
    elif target.exists():
        if policy == "skip":
            return None, "Skipped — a file with that name already exists"
        if policy == "replace":
            return target, "Replaced the existing file"
    else:
        return target, ""

    stem, suffix = target.stem, target.suffix
    for name in extra:
        cand = target.with_name(f"{name}{suffix}")
        if not taken(cand) and not _same_file(cand, src):
            return cand, f"Saved as {cand.name} (another file has the same name)"
    i = 2
    while True:
        cand = target.with_name(f"{stem}_{i}{suffix}")
        if not taken(cand) and not _same_file(cand, src):
            return cand, f"Saved as {cand.name} (name was taken)"
        i += 1


def reserve_key(p: Path) -> str:
    return _key(p)
