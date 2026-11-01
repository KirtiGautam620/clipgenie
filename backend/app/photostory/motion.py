"""How a photo moves: Ken Burns style zooms and pans, worked out as plain numbers.

A move is a short list of keyframes. Each says, at time t, how far in we are (zoom, 1 = the whole
picture) and where the centre of the visible window is (cx, cy, as a share of the photo, 0..1).
The window never leaves the photo: there are no black edges.

linear_expression() turns keyframes into a flat FFmpeg expression, the same trick framing.py uses
for the speaker-following crop, written here for any variable (frame number, for zoompan).
"""
from dataclasses import dataclass

ZOOM_RANGE = 0.35      # at full intensity a zoom ends 35% closer than it began
MIN_PAN_ZOOM = 0.08    # a pan needs spare picture at the sides: at least 8% closer
SAMPLES = 12           # keyframes per move (more keeps the easing smooth, fewer keeps the expression short)


@dataclass(frozen=True)
class Key:
    t: float           # seconds from the start of the scene
    zoom: float        # 1.0 = the whole picture, 1.35 = 35% closer
    cx: float          # centre of the visible window, 0 (left) .. 1 (right)
    cy: float          # 0 (top) .. 1 (bottom)


def _ease(u: float) -> float:
    """Slow start, slow end: a move that does not begin or stop with a jolt."""
    return u * u * (3 - 2 * u)


def _inside(centre: float, zoom: float) -> float:
    """Keep a window of size 1/zoom entirely inside the photo."""
    half = 0.5 / zoom
    return min(max(centre, half), 1 - half)


def path(motion: str, intensity: float, seconds: float, focus: tuple[float, float] = (0.5, 0.5)) -> list[Key]:
    """The keyframes of one scene's move. `hold`, or an intensity of 0, means the picture stays still."""
    if motion == "hold" or intensity <= 0:
        return [Key(0.0, 1.0, 0.5, 0.5)]
    fx, fy = focus

    if motion in ("zoom_in", "zoom_out"):
        end_zoom = 1 + ZOOM_RANGE * intensity
        keys = []
        for k in range(SAMPLES + 1):
            u = k / SAMPLES
            e = _ease(u)
            zoom = 1 + (end_zoom - 1) * e
            keys.append(Key(u * seconds, zoom, _inside(0.5 + (fx - 0.5) * e, zoom),
                            _inside(0.5 + (fy - 0.5) * e, zoom)))
        if motion == "zoom_out":      # the same move, played backwards
            keys = [Key(seconds - key.t, key.zoom, key.cx, key.cy) for key in reversed(keys)]
        return keys

    zoom = 1 + max(MIN_PAN_ZOOM, ZOOM_RANGE * intensity)
    half = 0.5 / zoom
    span = (1 - 2 * half) * (0.4 + 0.6 * intensity)      # how far the window travels, as a share of the photo
    horizontal = motion in ("pan_left", "pan_right")
    along = fx if horizontal else fy
    low = max(half, min(1 - half - span, along - span / 2))
    high = low + span
    forward = motion in ("pan_right", "pan_down")
    start, end = (low, high) if forward else (high, low)
    keys = []
    for k in range(SAMPLES + 1):
        u = k / SAMPLES
        pos = start + (end - start) * _ease(u)
        other = _inside(fy if horizontal else fx, zoom)
        keys.append(Key(u * seconds, zoom, pos if horizontal else other, other if horizontal else pos))
    return keys


def window_at(keys: list[Key], t: float) -> tuple[float, float, float]:
    """(zoom, cx, cy) at time t, a straight line between keyframes (how the expressions behave)."""
    if t <= keys[0].t or len(keys) == 1:
        return keys[0].zoom, keys[0].cx, keys[0].cy
    for a, b in zip(keys, keys[1:]):
        if t <= b.t:
            f = (t - a.t) / (b.t - a.t) if b.t > a.t else 1.0
            return (a.zoom + (b.zoom - a.zoom) * f, a.cx + (b.cx - a.cx) * f, a.cy + (b.cy - a.cy) * f)
    last = keys[-1]
    return last.zoom, last.cx, last.cy


def linear_expression(points: list[tuple[float, float]], var: str = "on") -> str:
    """FFmpeg expression for a value that moves in straight lines between (x, value) points.

    Written as  v0 + slope1*clip(var-x1,0,d1) + slope2*clip(var-x2,0,d2) + ...  a flat sum, so even a
    long path stays simple and safe. Put it inside quotes in a filter so its commas are not misread.
    """
    first = points[0][1]
    if len(points) == 1 or max(v for _, v in points) - min(v for _, v in points) < 1e-6:
        return f"{first:.5f}"
    expr = f"{first:.5f}"
    for (x0, v0), (x1, v1) in zip(points, points[1:]):
        if x1 - x0 > 1e-9 and abs(v1 - v0) > 1e-9:
            expr += f"+{(v1 - v0) / (x1 - x0):.7f}*clip({var}-{x0:.3f},0,{x1 - x0:.3f})"
    return expr.replace("+-", "-")


def zoompan_expressions(keys: list[Key], fps: int) -> tuple[str, str, str]:
    """(z, x, y) for FFmpeg's zoompan filter, written per output frame number `on`.

    x and y are the top-left corner of the visible window in the (up-scaled) input picture: the
    window centre times the picture size, minus half the window. `zoom` is the zoompan variable
    holding this frame's zoom.
    """
    z = linear_expression([(k.t * fps, k.zoom) for k in keys])
    cx = linear_expression([(k.t * fps, k.cx) for k in keys])
    cy = linear_expression([(k.t * fps, k.cy) for k in keys])
    return z, f"({cx})*iw-iw/zoom/2", f"({cy})*ih-ih/zoom/2"
