"""Picture effects for a clip: a slow zoom in and a sideways pan.

Both are plain FFmpeg `zoompan` maths, so they need no extra software or models. They change only
the picture of the base clip (stage 1 in export.py). Captions and headlines are drawn afterwards,
so the text stays sharp and is never zoomed.
"""

ZOOM_MIN, ZOOM_MAX = 1.0, 1.5      # 1.0 = no zoom; 1.5 = picture enlarged 50% by the last frame
PANS = ("none", "left", "right")   # left: the view slides from left to right; right: the reverse
FPS = 25                           # frames per second used for the effect (matches captions)
DEFAULT = {"zoom": ZOOM_MIN, "pan": "none"}


def normalize(effects: dict | None) -> dict:
    """Check and tidy the effect settings. Raises ValueError with a readable message."""
    effects = {**DEFAULT, **(effects or {})}
    try:
        zoom = float(effects["zoom"])
    except (TypeError, ValueError):
        raise ValueError("Zoom must be a number.")
    if not ZOOM_MIN <= zoom <= ZOOM_MAX:
        raise ValueError(f"Zoom must be between {ZOOM_MIN:.2f} and {ZOOM_MAX:.2f}.")
    if effects["pan"] not in PANS:
        raise ValueError("Pan must be none, left or right.")
    return {"zoom": round(zoom, 2), "pan": effects["pan"]}


def is_active(effects: dict | None) -> bool:
    """True when the picture actually moves."""
    e = normalize(effects)
    return e["zoom"] > ZOOM_MIN or e["pan"] != "none"


def zoom_filter(effects: dict | None, duration: float, width: int, height: int) -> str | None:
    """The FFmpeg filter that applies the effect to a picture of width x height, or None if it
    does nothing. `duration` is the clip length in seconds."""
    if not is_active(effects):
        return None
    e = normalize(effects)
    frames = max(1, round(duration * FPS))
    progress = f"on/{frames}"                      # 0 at the first frame, ~1 at the last
    z = f"{ZOOM_MIN}+({e['zoom'] - ZOOM_MIN:.2f})*{progress}" if e["zoom"] > ZOOM_MIN else str(ZOOM_MIN)
    room = "(iw-iw/zoom)"                          # how far the view can slide sideways
    x = {"none": f"{room}/2",
         "left": f"{room}*{progress}",
         "right": f"{room}*(1-{progress})"}[e["pan"]]
    y = "(ih-ih/zoom)/2"
    return (f"fps={FPS},zoompan=z='{z}':x='{x}':y='{y}':d=1:s={width}x{height}")
