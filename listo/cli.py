"""Command-line Listo: `python -m listo cli FILES... [options]`.

Handy for scripting and for testing the engine without the window.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .engine import Conversion
from .presets import AUDIO_BY_KEY, PHOTO_BY_KEY, VIDEO_BY_KEY, Settings
from .probe import KNOWN_EXTS, ext_of, probe
from .tools import capabilities, detect_hardware


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="listo cli", description="Convert files with Listo's engine.")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--video", choices=sorted(VIDEO_BY_KEY), default="prores")
    ap.add_argument("--variant", help="flavor/quality for the video preset (e.g. 2, dnxhr_hq, high)")
    ap.add_argument("--audio", choices=sorted(AUDIO_BY_KEY), default="wav24")
    ap.add_argument("--photo", choices=sorted(PHOTO_BY_KEY), default="jpeg")
    ap.add_argument("--resize", default="orig", help="video: orig|2160|1080|720|540|half")
    ap.add_argument("--photo-resize", default="orig")
    ap.add_argument("--deinterlace", choices=["smooth", "film", "off"], default="smooth")
    ap.add_argument("--out", help="output folder (default: next to each original)")
    ap.add_argument("--naming", default="{name}")
    ap.add_argument("--collision", choices=["number", "skip", "replace"], default="number")
    ap.add_argument("--no-hardware", action="store_true")
    a = ap.parse_args(argv)

    s = Settings(
        video_preset=a.video, audio_format=a.audio, photo_format=a.photo,
        video_resize=a.resize, photo_resize=a.photo_resize, deinterlace=a.deinterlace,
        naming=a.naming, collision=a.collision, hardware=not a.no_hardware,
    )
    if a.variant:
        s.video_variant[a.video] = a.variant
    if a.out:
        s.destination, s.dest_folder = "folder", a.out

    caps = capabilities()
    if not caps.ok:
        print("ffmpeg/ffprobe not found", file=sys.stderr)
        return 2
    if s.hardware:
        detect_hardware(caps)

    files: list[str] = []
    for f in a.files:
        p = Path(f)
        if p.is_dir():
            files += [str(x) for x in sorted(p.rglob("*")) if x.is_file() and ext_of(x) in KNOWN_EXTS]
        else:
            files.append(str(p))

    from . import naming

    reserved: set[str] = {naming.reserve_key(Path(f)) for f in files}  # never replace another original
    failed = 0
    for n, f in enumerate(files, 1):
        info = probe(f)
        r = Conversion(f, info, s, caps, reserved, counter=n).run()
        out = f" -> {r.output}" if r.output else ""
        print(f"[{r.status}] {f}{out} {r.message} {' '.join(r.notes)}".rstrip())
        if r.status == "failed":
            failed += 1
            if r.log:
                print("    " + "\n    ".join(r.log.splitlines()[-8:]), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
