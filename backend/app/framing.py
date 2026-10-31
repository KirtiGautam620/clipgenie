"""Smart framing: keep the speaker's face inside the 9:16 crop.

How it works, in four steps:

1. SAMPLE   - a few frames per second of the clip are read from the video (small, grey).
2. DETECT   - OpenCV's built-in face detector (a "Haar cascade", ships inside the library,
              nothing to download) finds faces in each frame.
3. DECIDE   - faces that keep showing up at about the same place are joined into "tracks".
              The biggest, most persistent track is the speaker. Random false detections
              last only a frame or two, so they are thrown away.
4. SMOOTH   - the speaker's position is smoothed so the crop glides instead of shaking,
              and held still while the speaker only moves a little.

The result is a small "plan": where the left edge of the crop should be over time.
export.py turns that into an FFmpeg crop. Anything unusual falls back to something safe:

  no face / face rarely seen   -> the old centre crop
  two similar faces far apart  -> "blur" framing (the whole picture stays visible)
  anything crashes             -> the old centre crop
"""
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SAMPLE_FPS = 3             # frames examined per second of clip
DETECT_WIDTH = 960         # frames are shrunk to this width before detecting (fast, low memory)
MIN_FACE = 28              # smallest face (pixels, at DETECT_WIDTH) worth tracking
MIN_COVERAGE = 0.5         # the speaker must be seen in at least this share of samples
MIN_HITS = 3               # a track needs this many detections (kills one-frame false alarms)
MERGE_GAP = 4.0           # seconds a speaker may be out of sight and still be the same track
MAX_GAP = 1.0              # seconds a track may disappear and still be the same face
COMPETING_SHARE = 0.3      # a second face this big (vs. the main one) makes the shot ambiguous
STILL_RANGE = 0.10         # speaker moves less than this share of the crop width -> hold still
DEAD_ZONE = 0.12           # camera ignores speaker movement inside this share of crop width
MEDIAN_SAMPLES = 5         # removes single bad detections
SLOW_SIGMA = 1.0           # seconds of smoothing on the raw path
GLIDE_SIGMA = 0.6          # seconds of smoothing after the dead-zone hold
SIMPLIFY_TOLERANCE = 1.5   # pixels; keyframes closer than this to a straight line are dropped


@dataclass
class Plan:
    mode: str                      # "track" | "static" | "center" | "blur"
    reason: str
    crop_w: float = 0.0            # width of the 9:16 window, in source pixels
    keys: list[tuple[float, float]] = field(default_factory=list)  # (seconds, left edge x)
    faces_seen: int = 0            # samples in which the speaker was found
    samples: int = 0

    def summary(self) -> dict:
        return {"mode": self.mode, "reason": self.reason,
                "faces_seen": self.faces_seen, "samples": self.samples}


# ---------------------------------------------------------------- 1 + 2: sample and detect

_cascade = None


def _get_cascade():
    global _cascade
    if _cascade is None:
        import cv2   # imported here so the server starts fast and works without it
        _cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if _cascade.empty():
            raise RuntimeError("OpenCV face model not found")
    return _cascade


def _grey_frames(video: Path, start: float, duration: float, src_w: int, src_h: int):
    """Yield small grey frames, SAMPLE_FPS per second. One frame in memory at a time."""
    h = max(2, int(round(src_h * DETECT_WIDTH / src_w / 2)) * 2)
    cmd = ["ffmpeg", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{duration:.2f}",
           "-i", str(video), "-an", "-vf", f"fps={SAMPLE_FPS},scale={DETECT_WIDTH}:{h}",
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    size = DETECT_WIDTH * h
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, DETECT_WIDTH)
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def detect_faces(video: Path, start: float, duration: float,
                 src_w: int, src_h: int) -> list[list[tuple[float, float, float]]]:
    """One list per sampled frame, each holding faces as (centre x, centre y, size) in source pixels."""
    import cv2
    cascade = _get_cascade()
    scale = src_w / DETECT_WIDTH
    out = []
    for frame in _grey_frames(video, start, duration, src_w, src_h):
        found = cascade.detectMultiScale(cv2.equalizeHist(frame), scaleFactor=1.1,
                                         minNeighbors=6, minSize=(MIN_FACE, MIN_FACE))
        out.append([((x + w / 2) * scale, (y + h / 2) * scale, w * scale) for x, y, w, h in found])
    return out


# ---------------------------------------------------------------- 3: decide who the speaker is

def _build_tracks(samples: list[list[tuple[float, float, float]]]) -> list[dict]:
    """Join detections that stay at about the same place into tracks: {i: (x, y, size)}."""
    max_gap = max(1, int(round(MAX_GAP * SAMPLE_FPS)))
    tracks: list[dict] = []
    for i, faces in enumerate(samples):
        taken = set()
        for face in sorted(faces, key=lambda f: -f[2]):          # big faces choose first
            best, best_d = None, None
            for t in tracks:
                last_i = max(t["hits"])
                if id(t) in taken or i - last_i > max_gap:
                    continue
                lx, ly, ls = t["hits"][last_i]
                d = ((face[0] - lx) ** 2 + (face[1] - ly) ** 2) ** 0.5
                similar_size = 0.5 < face[2] / ls < 2.0      # a small inset face is not the speaker
                if similar_size and d < 0.8 * max(face[2], ls) and (best_d is None or d < best_d):
                    best, best_d = t, d
            if best is None:
                best = {"hits": {}}
                tracks.append(best)
            best["hits"][i] = face
            taken.add(id(best))
    tracks = _merge_tracks(tracks)
    for t in tracks:
        t["score"] = sum(f[2] ** 2 for f in t["hits"].values())   # big and persistent wins
    return [t for t in tracks if len(t["hits"]) >= MIN_HITS]


def _merge_tracks(tracks: list[dict]) -> list[dict]:
    """Rejoin pieces of one person's track: they never overlap in time and pick up in the same place.

    A speaker who turns away or is hidden for a moment would otherwise look like several
    different, weak faces.
    """
    max_join = int(MERGE_GAP * SAMPLE_FPS)
    groups: list[dict] = []
    for t in sorted(tracks, key=lambda t: min(t["hits"])):
        first = min(t["hits"])
        fx, fy, fs = t["hits"][first]
        best, best_d = None, None
        for g in groups:
            last = max(g["hits"])
            if last >= first or first - last > max_join:
                continue
            lx, ly, ls = g["hits"][last]
            d = ((fx - lx) ** 2 + (fy - ly) ** 2) ** 0.5
            if 0.5 < fs / ls < 2.0 and d < max(fs, ls) and (best_d is None or d < best_d):
                best, best_d = g, d
        if best is None:
            groups.append({"hits": dict(t["hits"])})
        else:
            best["hits"].update(t["hits"])
    return groups


def _median_x(track: dict) -> float:
    return float(np.median([f[0] for f in track["hits"].values()]))


def _median_size(track: dict) -> float:
    return float(np.median([f[2] for f in track["hits"].values()]))


# ---------------------------------------------------------------- 4: smooth the path

def _smooth(series: np.ndarray, sigma_samples: float) -> np.ndarray:
    """Gaussian smoothing with no time lag (looks at the past and the future equally)."""
    if sigma_samples <= 0 or len(series) < 2:
        return series
    radius = max(1, int(3 * sigma_samples))
    k = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma_samples) ** 2)
    k /= k.sum()
    padded = np.pad(series, radius, mode="edge")
    return np.convolve(padded, k, mode="valid")


def _median_filter(series: np.ndarray, k: int) -> np.ndarray:
    if k < 2 or len(series) < k:
        return series
    half = k // 2
    padded = np.pad(series, half, mode="edge")
    return np.array([np.median(padded[i:i + k]) for i in range(len(series))])


def _dead_zone(series: np.ndarray, zone: float) -> np.ndarray:
    """A camera operator's habit: stay put until the subject leaves the comfortable middle."""
    cam, out = series[0], []
    for v in series:
        if v > cam + zone:
            cam = v - zone
        elif v < cam - zone:
            cam = v + zone
        out.append(cam)
    return np.array(out)


def _simplify(points: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker: keep only the keyframes needed to follow the path within `tol`."""
    if len(points) < 3:
        return points
    (t0, x0), (t1, x1) = points[0], points[-1]
    worst, worst_i = 0.0, 0
    for i in range(1, len(points) - 1):
        t, x = points[i]
        line = x0 + (x1 - x0) * (t - t0) / (t1 - t0) if t1 > t0 else x0
        if abs(x - line) > worst:
            worst, worst_i = abs(x - line), i
    if worst <= tol:
        return [points[0], points[-1]]
    return _simplify(points[:worst_i + 1], tol)[:-1] + _simplify(points[worst_i:], tol)


def plan_framing(samples: list[list[tuple[float, float, float]]], src_w: int, src_h: int) -> Plan:
    """Turn face detections into a crop plan. Pure maths: easy to test without any video."""
    n = len(samples)
    crop_w = src_h * 9 / 16
    centre_x = (src_w - crop_w) / 2

    def center(reason: str) -> Plan:
        return Plan("center", reason, crop_w, [(0.0, centre_x)], 0, n)

    if src_w <= crop_w + 1:
        return center("video is not wider than 9:16")
    tracks = _build_tracks(samples)
    if not tracks:
        return center("no steady face found")
    main = max(tracks, key=lambda t: t["score"])
    seen = len(main["hits"])
    if seen / max(n, 1) < MIN_COVERAGE:
        return center(f"face seen in only {seen} of {n} samples")

    # a second, similar-sized face at the same time, standing apart from the speaker
    for other in tracks:
        if other is main or other["score"] < COMPETING_SHARE * main["score"]:
            continue
        shared = [i for i in other["hits"] if i in main["hits"]]
        apart = abs(_median_x(other) - _median_x(main)) > max(_median_size(other), _median_size(main))
        if len(shared) >= 0.3 * len(other["hits"]) and apart:
            pad = 0.75 * max(_median_size(main), _median_size(other))   # face edge plus a margin
            left = min(_median_x(main), _median_x(other)) - pad
            right = max(_median_x(main), _median_x(other)) + pad
            if right - left <= crop_w * 0.9:                 # both fit: frame them together
                x = min(max((left + right) / 2 - crop_w / 2, 0), src_w - crop_w)
                return Plan("static", "two faces, framed together", crop_w, [(0.0, x)], seen, n)
            return Plan("blur", "two faces too far apart for one vertical crop", crop_w, [], seen, n)

    # the speaker's x position over time; gaps are filled in by interpolation
    idx = np.array(sorted(main["hits"]))
    xs = np.array([main["hits"][i][0] for i in idx])
    series = np.interp(np.arange(n), idx, xs)
    series = _median_filter(series, MEDIAN_SAMPLES)

    def left_edge(centres: np.ndarray) -> np.ndarray:
        return np.clip(centres - crop_w / 2, 0, src_w - crop_w)

    if series.max() - series.min() < STILL_RANGE * crop_w:   # barely moves: perfectly still shot
        x = float(left_edge(np.array([np.median(series)]))[0])
        return Plan("static", "speaker stays put", crop_w, [(0.0, x)], seen, n)

    path = _smooth(series, SLOW_SIGMA * SAMPLE_FPS)
    path = _dead_zone(path, DEAD_ZONE * crop_w)
    path = _smooth(path, GLIDE_SIGMA * SAMPLE_FPS)
    keys = [(i / SAMPLE_FPS, float(x)) for i, x in enumerate(left_edge(path))]
    return Plan("track", "following the speaker", crop_w, _simplify(keys, SIMPLIFY_TOLERANCE), seen, n)


def crop_x_expression(keys: list[tuple[float, float]], scale: float) -> str:
    """FFmpeg expression giving the crop's left edge at time t (a straight line between keyframes).

    Written as  x0 + slope1*clip(t-t1,0,d1) + slope2*clip(t-t2,0,d2) + ...  which is a flat sum,
    so even long paths stay a safe, simple expression. `scale` converts source pixels to the
    scaled-up picture the crop is applied to.
    """
    pts = [(t, x * scale) for t, x in keys]
    if len(pts) == 1 or max(x for _, x in pts) - min(x for _, x in pts) < 0.5:
        return f"{pts[0][1]:.1f}"
    expr = f"{pts[0][1]:.2f}"
    for (t0, x0), (t1, x1) in zip(pts, pts[1:]):
        if t1 - t0 > 1e-6 and abs(x1 - x0) > 1e-3:
            expr += f"+{(x1 - x0) / (t1 - t0):.4f}*clip(t-{t0:.3f},0,{t1 - t0:.3f})"
    return expr.replace("+-", "-")


def plan_for_clip(video: Path, start: float, duration: float, src_w: int, src_h: int) -> Plan:
    """Detect faces in the clip and plan the framing. Never raises: any problem means centre crop."""
    crop_w = src_h * 9 / 16
    try:
        return plan_framing(detect_faces(video, start, duration, src_w, src_h), src_w, src_h)
    except Exception as e:  # missing OpenCV, odd video, ... the old centre crop is always safe
        return Plan("center", f"face detection unavailable ({type(e).__name__})", crop_w,
                    [(0.0, (src_w - crop_w) / 2)])
