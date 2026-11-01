"""Preview frames for a scene: the user's OWN photo, cropped and reframed.

These show composition and zoom. They are not new camera angles and not generated content: a flat
photo cannot show the product from a different side. All maths here is plain geometry.

A "box" is (left, top, right, bottom) as shares of the photo, 0..1.
"""
from io import BytesIO

from PIL import Image

OUT_SIZE = {"9:16": (1080, 1920), "16:9": (1920, 1080)}     # the size a generator would be asked for
ZOOM_RANGE = 0.35        # a push-in or pull-out changes the zoom by up to 35%
MIN_PAN_ZOOM = 1.1       # a pan needs spare picture to travel across
SHARP, OK = 1.0, 0.6     # crop width as a share of the output width


def _ratio(aspect: str) -> float:
    w, h = OUT_SIZE[aspect]
    return w / h


def window(photo_w: int, photo_h: int, aspect: str, zoom: float, cx: float, cy: float) -> tuple[float, float, float, float]:
    """The visible box: the biggest window of this shape that fits the photo, made `zoom` times
    smaller, centred on (cx, cy) but never leaving the photo."""
    ratio = _ratio(aspect)
    base_w, base_h = (photo_h * ratio, photo_h) if photo_w / photo_h > ratio else (photo_w, photo_w / ratio)
    w, h = base_w / zoom / photo_w, base_h / zoom / photo_h            # shares of the photo
    left = min(max(cx - w / 2, 0.0), 1.0 - w)
    top = min(max(cy - h / 2, 0.0), 1.0 - h)
    return left, top, left + w, top + h


def _travel(start: float, centre: float, free: float, intensity: float, window_share: float, forward: bool) -> tuple[float, float]:
    """Where a pan starts and ends along one axis (centre positions, as shares of the photo)."""
    shift = free * (0.4 + 0.6 * intensity)
    lo = max(window_share / 2, min(1 - window_share / 2 - shift, centre - shift / 2))
    hi = lo + shift
    return (lo, hi) if forward else (hi, lo)


def boxes(photo_w: int, photo_h: int, aspect: str, scene) -> tuple[tuple, tuple]:
    """(start box, end box) of a scene: where its movement begins and ends."""
    z, i, motion = scene.zoom, scene.intensity, scene.motion
    fx, fy = scene.focus
    if motion == "hold" or i <= 0:
        box = window(photo_w, photo_h, aspect, z, fx, fy)
        return box, box
    if motion == "push_in":
        return window(photo_w, photo_h, aspect, z, fx, fy), window(photo_w, photo_h, aspect, z * (1 + ZOOM_RANGE * i), fx, fy)
    if motion == "pull_out":
        return window(photo_w, photo_h, aspect, z * (1 + ZOOM_RANGE * i), fx, fy), window(photo_w, photo_h, aspect, z, fx, fy)
    zoom = max(z, MIN_PAN_ZOOM)
    l, t, r, b = window(photo_w, photo_h, aspect, zoom, fx, fy)
    if motion in ("pan_left", "pan_right"):
        share = r - l
        a, c = _travel(0, fx, 1 - share, i, share, motion == "pan_right")
        return window(photo_w, photo_h, aspect, zoom, a, fy), window(photo_w, photo_h, aspect, zoom, c, fy)
    share = b - t
    a, c = _travel(0, fy, 1 - share, i, share, motion == "pan_down")
    return window(photo_w, photo_h, aspect, zoom, fx, a), window(photo_w, photo_h, aspect, zoom, fx, c)


def sharpness(photo_w: int, photo_h: int, aspect: str, start: tuple, end: tuple) -> dict:
    """How sharp the tighter end of the scene will be, from the REAL pixels left after cropping."""
    out_w = OUT_SIZE[aspect][0]
    tightest = min(start[2] - start[0], end[2] - end[0]) * photo_w
    ratio = tightest / out_w
    label = "sharp" if ratio >= SHARP else "ok" if ratio >= OK else "soft"
    height = min(start[3] - start[1], end[3] - end[1]) * photo_h
    return {"label": label, "ratio": round(ratio, 2), "crop_px": [round(tightest), round(height)]}


def geometry(photo_w: int, photo_h: int, aspect: str, scene) -> dict:
    start, end = boxes(photo_w, photo_h, aspect, scene)
    return {"start": [round(v, 4) for v in start], "end": [round(v, 4) for v in end],
            "sharpness": sharpness(photo_w, photo_h, aspect, start, end)}


def frame_size(aspect: str, long_side: int) -> tuple[int, int]:
    w, h = OUT_SIZE[aspect]
    scale = long_side / max(w, h)
    return max(2, round(w * scale)), max(2, round(h * scale))


def render(photo: Image.Image, box: tuple, aspect: str, long_side: int = 480, quality: int = 85) -> bytes:
    """One preview frame as JPEG bytes."""
    pw, ph = photo.size
    size = frame_size(aspect, long_side)
    crop = (box[0] * pw, box[1] * ph, box[2] * pw, box[3] * ph)
    out = BytesIO()
    photo.convert("RGB").resize(size, Image.LANCZOS, box=crop).save(out, "JPEG", quality=quality)
    return out.getvalue()
