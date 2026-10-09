"""Generate small, tricky sample files for testing (needs ffmpeg on PATH)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *args], check=True)


def make(dirpath: Path) -> dict[str, Path]:
    d = Path(dirpath)
    d.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}

    # iPhone-style uppercase extension, two audio tracks
    p = d / "IMG_0001.MOV"
    ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=2",
       "-f", "lavfi", "-i", "sine=f=440:d=2", "-f", "lavfi", "-i", "sine=f=660:d=2",
       "-map", "0", "-map", "1", "-map", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-metadata", "creation_time=2024-05-01T18:30:00Z", str(p))
    out["upper_mov"] = p

    # odd dimensions
    p = d / "odd.mkv"
    ff("-f", "lavfi", "-i", "color=c=red:s=641x361:r=24:d=1", "-vf", "scale=641:361,format=yuv444p", "-c:v", "ffv1", str(p))
    out["odd"] = p

    # interlaced MPEG-2 transport stream with AC-3 (camcorder-ish)
    p = d / "clip.mts"
    ff("-f", "lavfi", "-i", "testsrc2=s=720x480:r=30000/1001:d=2",
       "-f", "lavfi", "-i", "sine=f=300:d=2", "-c:v", "mpeg2video", "-flags", "+ilme+ildct",
       "-top", "1", "-b:v", "6M", "-c:a", "ac3", "-f", "mpegts", str(p))
    out["interlaced"] = p

    # same base name, different extension
    p = d / "clip.avi"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=1", "-c:v", "mpeg4", str(p))
    out["same_name"] = p

    # 24-bit WAV
    p = d / "tone.wav"
    ff("-f", "lavfi", "-i", "sine=f=1000:d=2", "-c:a", "pcm_s24le", str(p))
    out["wav"] = p

    # 10-bit HLG HEVC (like iPhone HDR)
    p = d / "hdr.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=1", "-c:v", "libx265", "-pix_fmt", "yuv420p10le",
       "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
       "-x265-params", "log-level=error", "-tag:v", "hvc1", str(p))
    out["hdr"] = p

    # photos
    img = Image.new("RGB", (400, 300), (200, 80, 40))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90
    exif[0x0132] = "2023:07:04 12:00:00"
    p = d / "rotated.JPG"
    img.save(p, "JPEG", exif=exif.tobytes())
    out["jpg"] = p

    p = d / "alpha.png"
    Image.new("RGBA", (300, 200), (0, 120, 255, 100)).save(p)
    out["png"] = p

    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
        p = d / "phone.HEIC"
        Image.new("RGB", (500, 400), (30, 160, 90)).save(p, "HEIF")
        out["heic"] = p
    except Exception:  # noqa: BLE001
        pass

    # not media at all
    p = d / "notes.txt"
    p.write_text("hi")
    out["txt"] = p
    return out


if __name__ == "__main__":
    import sys

    for k, v in make(Path(sys.argv[1] if len(sys.argv) > 1 else "samples")).items():
        print(k, v)
