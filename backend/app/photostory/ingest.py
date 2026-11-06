"""Take in an uploaded photo: check it, turn it the right way up, drop its hidden data, save a clean copy.

This is the only part of the package that opens an image file. It checks the picture's size from
the file header BEFORE decoding it, so a huge image cannot use up the Mac's memory.

Hidden camera data can include where the photo was taken (GPS), so the saved copy has none of it.
"""
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELS = 50_000_000     # refuse anything bigger than this (width x height), before decoding it
MAX_SIDE = 4096             # a longer side is shrunk to this: more detail is invisible in a 1080-wide video
SUPPORTED = {"JPEG", "PNG", "WEBP"}
EXIF_ORIENTATION, EXIF_GPS = 0x0112, 0x8825


def normalize_image(source: Path | str | bytes, dest: Path | str) -> dict:
    """Save a clean JPEG copy of `source` at `dest`. Raises ValueError with a readable message.

    Returns what was done: {"width", "height", "original": (w, h), "rotated", "resized",
    "had_location", "had_camera_data"}.
    """
    try:
        img = Image.open(BytesIO(source) if isinstance(source, (bytes, bytearray)) else source)
        fmt = img.format
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("This file is not a photo CocoGenie can read. Please use a JPG, PNG or WebP.") from None
    if fmt not in SUPPORTED:
        raise ValueError("This file is not a photo CocoGenie can read. Please use a JPG, PNG or WebP.")
    width, height = img.size                      # from the header: nothing has been decoded yet
    if width * height > MAX_PIXELS:
        raise ValueError(f"This photo is too large ({width} x {height}). Please use one under "
                         f"{MAX_PIXELS // 1_000_000} megapixels.")

    exif = img.getexif()
    had_location = EXIF_GPS in exif
    orientation = exif.get(EXIF_ORIENTATION, 1)
    had_camera_data = len(exif) > 0

    img.load()
    img = ImageOps.exif_transpose(img)            # turn it the right way up, as the camera meant
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")                # see-through areas become white, not black
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.split()[3])
        img = flat
    else:
        img = img.convert("RGB")
    resized = max(img.size) > MAX_SIDE
    if resized:
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    img.save(dest, "JPEG", quality=92, optimize=True)     # no exif argument: nothing hidden is kept
    return {"width": img.width, "height": img.height, "original": (width, height),
            "rotated": orientation in (2, 3, 4, 5, 6, 7, 8), "resized": resized,
            "had_location": had_location, "had_camera_data": had_camera_data}
