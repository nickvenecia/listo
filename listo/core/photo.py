"""Photo conversion: JPEG/PNG/TIFF/WebP/HEIC in and out, plus camera RAW in."""

from __future__ import annotations

from datetime import datetime

from PIL import Image, ImageOps

from listo.core.log import get_logger
from listo.core.presets import PHOTO_BY_KEY, Settings
from listo.core.probe import RAW_EXTS, ext_of

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:
    HEIF_OK = False

try:
    import rawpy

    RAW_OK = True
except Exception:
    RAW_OK = False

log = get_logger(__name__)

Image.MAX_IMAGE_PIXELS = 400_000_000  # big panoramas are fine; still guards against bombs

EXIF_DATETIME_ORIGINAL = 0x9003
EXIF_DATETIME = 0x0132


def _exif_date(img: Image.Image) -> datetime | None:
    try:
        exif = img.getexif()
        raw = exif.get_ifd(0x8769).get(EXIF_DATETIME_ORIGINAL) or exif.get(EXIF_DATETIME)
        if raw:
            return datetime.strptime(str(raw).strip("\x00 "), "%Y:%m:%d %H:%M:%S")
    except Exception:
        log.debug("photo metadata step skipped", exc_info=True)
    return None


def peek(path: str) -> tuple[int, int, datetime | None]:
    """Size and capture date without decoding the whole image."""
    if ext_of(path) in RAW_EXTS:
        if not RAW_OK:
            raise RuntimeError("RAW support isn't installed")
        with rawpy.imread(path) as raw:
            s = raw.sizes
            w, h = s.width, s.height
            if s.flip in (5, 6):
                w, h = h, w
        created = None
        try:  # many RAWs are TIFF-based, so Pillow can read their EXIF
            with Image.open(path) as im:
                created = _exif_date(im)
        except Exception:
            log.debug("photo metadata step skipped", exc_info=True)
        return w, h, created
    with Image.open(path) as im:
        w, h = im.size
        try:
            orient = im.getexif().get(0x0112, 1)
            if orient in (5, 6, 7, 8):
                w, h = h, w
        except Exception:
            log.debug("photo metadata step skipped", exc_info=True)
        return w, h, _exif_date(im)


def thumbnail(path: str, size: int = 240) -> Image.Image | None:
    try:
        if ext_of(path) in RAW_EXTS and RAW_OK:
            with rawpy.imread(path) as raw:
                try:
                    th = raw.extract_thumb()
                    if th.format == rawpy.ThumbFormat.JPEG:
                        import io

                        im = Image.open(io.BytesIO(th.data))
                    else:
                        im = Image.fromarray(th.data)
                except Exception:
                    im = Image.fromarray(raw.postprocess(half_size=True, use_camera_wb=True))
        else:
            im = Image.open(path)
            im.draft("RGB", (size * 2, size * 2))
        im = ImageOps.exif_transpose(im)
        im.thumbnail((size, size))
        return im.convert("RGB")
    except Exception:
        return None


def _load(path: str) -> tuple[Image.Image, bytes | None, bytes | None, list[str]]:
    notes: list[str] = []
    if ext_of(path) in RAW_EXTS:
        if not RAW_OK:
            raise RuntimeError("RAW support isn't installed in this build.")
        with rawpy.imread(path) as raw:
            rgb = raw.postprocess(use_camera_wb=True, output_bps=8, no_auto_bright=False)
        img = Image.fromarray(rgb)
        exif = None
        try:
            with Image.open(path) as im:
                e = im.getexif()
                if e:
                    e[0x0112] = 1  # rawpy already rotated the pixels
                    exif = e.tobytes()
        except Exception:
            log.debug("photo metadata step skipped", exc_info=True)
        notes.append("RAW developed with the camera's white balance.")
        return img, exif, None, notes
    img = Image.open(path)
    img.load()
    if getattr(img, "n_frames", 1) > 1:
        notes.append("Only the first frame was kept.")
    exif = img.info.get("exif")
    icc = img.info.get("icc_profile")
    img = ImageOps.exif_transpose(img)  # bake in rotation; Pillow resets the orientation tag
    if exif:
        try:
            e = img.getexif()
            e[0x0112] = 1
            exif = e.tobytes()
        except Exception:
            log.debug("photo metadata step skipped", exc_info=True)
    return img, exif, icc, notes


def _to_8bit(img: Image.Image) -> Image.Image:
    """16-bit / 32-bit / float grayscale -> 8-bit, scaling values instead of clipping them."""
    import numpy as np

    a = np.asarray(img).astype("float64")
    if img.mode == "F":
        hi = 1.0 if a.size and np.nanmax(a) <= 1.0 else 255.0
        a = a / hi * 255.0
    elif img.mode.startswith("I;16") or (a.size and a.max() > 255):
        a = a / 257.0
    return Image.fromarray(np.clip(a, 0, 255).round().astype("uint8"), "L")


def _cmyk_to_rgb(img: Image.Image, icc: bytes | None) -> tuple[Image.Image, bytes | None]:
    try:
        import io

        from PIL import ImageCms

        srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
        if icc:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            img = ImageCms.profileToProfile(img, src, srgb, outputMode="RGB")
            return img, srgb.tobytes()
    except Exception:
        log.debug("photo metadata step skipped", exc_info=True)
    return img.convert("RGB"), None  # the CMYK profile no longer applies


def convert(src: str, out: str, s: Settings) -> list[str]:
    fmt = PHOTO_BY_KEY[s.photo_format]
    img, exif, icc, notes = _load(src)

    if img.mode == "CMYK":
        img, icc = _cmyk_to_rgb(img, icc)
    if img.mode in ("I", "F") or (img.mode.startswith("I;16") and fmt.key not in ("png", "tiff")):
        img = _to_8bit(img)

    if s.photo_resize != "orig":
        target = int(s.photo_resize)
        if max(img.size) > target:
            img.thumbnail((target, target), Image.Resampling.LANCZOS)
            notes.append(f"Resized to {img.size[0]}×{img.size[1]}.")

    has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
    if fmt.key in ("jpeg", "heic") or (fmt.key == "tiff" and img.mode not in ("RGB", "RGBA", "L", "I;16")):
        if has_alpha and fmt.key in ("jpeg",):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            img = bg
            notes.append("Transparency filled with white (JPEG has no transparency).")
        elif img.mode not in ("RGB", "L") and not (fmt.key == "heic" and img.mode == "RGBA"):
            img = img.convert("RGBA" if has_alpha and fmt.key != "jpeg" else "RGB")
    elif fmt.key in ("png", "webp") and img.mode not in ("RGB", "RGBA", "L", "LA", "I;16"):
        img = img.convert("RGBA" if has_alpha else "RGB")

    kw: dict = {}
    if s.photo_keep_metadata:
        if exif:
            kw["exif"] = exif
        if icc:
            kw["icc_profile"] = icc
    q = max(1, min(100, int(s.photo_quality)))

    if fmt.key == "jpeg":
        img.save(out, "JPEG", quality=q, subsampling=0 if q >= 90 else 2, optimize=True, **kw)
    elif fmt.key == "png":
        img.save(out, "PNG", compress_level=6, **kw)
    elif fmt.key == "tiff":
        img.save(out, "TIFF", compression="tiff_lzw", **kw)
    elif fmt.key == "webp":
        img.save(out, "WEBP", quality=q, method=5, **kw)
    elif fmt.key == "heic":
        if not HEIF_OK:
            raise RuntimeError("HEIC support isn't installed in this build.")
        img.save(out, "HEIF", quality=q, **kw)
    if not s.photo_keep_metadata:
        notes.append("Metadata removed.")
    return notes


def is_heic_encodable() -> bool:
    return HEIF_OK
