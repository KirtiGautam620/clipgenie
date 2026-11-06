"""Thumbnails from the clip's own frames: no image model.

1. candidates(): sample frames across the finished video's caption-free picture and score each one:
   sharp (not motion-blurred), well exposed (not black or washed out), and a visible face (bigger is
   better). The best few, spread out in time, are kept as the choices.
2. compose(): the chosen moment as a 1080x1920 picture (Shorts / Reels) and as a 1280x720 one
   (YouTube). The 16:9 one is taken from the SOURCE video at the same moment, cropped around the
   face, so it is not a squashed portrait. Optional text is drawn with the app's headline drawing.
"""
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from app import captionstyles, jobs, manifest
from app.captions import render_headline
from app.framing import _get_cascade

SAMPLES = 24
KEEP = 6
MIN_GAP = 1.0                      # seconds between two kept frames
SIZES = {"9x16": (1080, 1920), "16x9": (1280, 720)}


def folder_for(job_id: str, clip_id: int) -> Path:
    path = jobs.job_dir(job_id) / "thumbs" / f"clip_{clip_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _duration(path: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(path)], check=True, capture_output=True, text=True).stdout)


def _frame(video: Path, t: float, out: Path, width: int | None = None) -> bool:
    vf = ["-vf", f"scale={width}:-2"] if width else []
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                        *vf, "-q:v", "2", str(out)], capture_output=True)
    return r.returncode == 0 and out.exists()


def score(image: Image.Image) -> dict:
    """How good a frame is as a thumbnail (higher is better), and why."""
    import cv2
    gray = np.asarray(image.convert("L"))
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    bright = float(gray.mean())
    faces = _get_cascade().detectMultiScale(cv2.equalizeHist(gray), scaleFactor=1.1, minNeighbors=5,
                                            minSize=(gray.shape[1] // 12,) * 2)
    face = max((w * h for (x, y, w, h) in faces), default=0) / float(gray.size)
    exposure = 1.0 - min(1.0, abs(bright - 125) / 100)            # 1 at a middle brightness, 0 near black/white
    total = min(sharp, 600) / 600 * 0.45 + exposure * 0.25 + min(face * 8, 1.0) * 0.30
    if bright < 25 or bright > 235:
        total *= 0.2                                               # black or washed out: almost never right
    return {"score": round(total, 3), "sharpness": round(sharp, 1), "brightness": round(bright, 1),
            "face": round(face, 4), "faces": int(len(faces))}


def candidates(job_id: str, clip_id: int, version: int = 0) -> list[dict]:
    """Find and save the best frames to choose from. Returns [{"index", "t", "score", ...}], best first.
    `version` is the clip version they were taken from: after an edit they are found again."""
    root = jobs.job_dir(job_id)
    picture = root / f"clip_{clip_id}_base.mp4"            # no captions burned in: a cleaner thumbnail
    if not picture.exists():
        picture = root / f"clip_{clip_id}.mp4"
    if not picture.exists():
        raise ValueError("This clip's video is not on this computer.")
    out = folder_for(job_id, clip_id)
    length = _duration(picture)
    times = [0.5 + i * max(0.0, length - 1.0) / (SAMPLES - 1) for i in range(SAMPLES)] if length > 1.2 else [length / 2]
    scored = []
    for i, t in enumerate(times):
        path = out / f"sample_{i}.jpg"
        if _frame(picture, t, path, width=540):
            with Image.open(path) as im:
                scored.append({"t": round(t, 2), **score(im)})
            path.unlink(missing_ok=True)
    scored.sort(key=lambda f: -f["score"])
    kept = []
    for f in scored:
        if all(abs(f["t"] - k["t"]) >= MIN_GAP for k in kept):
            kept.append(f)
        if len(kept) == KEEP:
            break
    for index, f in enumerate(kept):
        f["index"] = index
        _frame(picture, f["t"], out / f"frame_{index}.jpg")      # full size, for the final picture
    (out / "frames.json").write_text(json.dumps({"version": version, "frames": kept}))
    return kept


def saved_candidates(job_id: str, clip_id: int, version: int | None = None) -> list[dict]:
    """The frames found before, or [] if there are none or the clip was edited since (version)."""
    path = folder_for(job_id, clip_id) / "frames.json"
    if not path.exists():
        return []
    saved = json.loads(path.read_text())
    if version is not None and saved.get("version") != version:
        return []
    return saved.get("frames", [])


def _cover(image: Image.Image, size: tuple[int, int], centre_x: float = 0.5) -> Image.Image:
    """Fill `size` with `image` (no stretching): scale to cover, crop around centre_x (0..1)."""
    w, h = size
    scale = max(w / image.width, h / image.height)
    im = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left = int(min(max(0, centre_x * im.width - w / 2), im.width - w))
    top = (im.height - h) // 2
    return im.crop((left, top, left + w, top + h))


def _face_centre(image: Image.Image) -> float:
    import cv2
    gray = np.asarray(image.convert("L"))
    faces = _get_cascade().detectMultiScale(cv2.equalizeHist(gray), scaleFactor=1.1, minNeighbors=5,
                                            minSize=(gray.shape[1] // 14,) * 2)
    if len(faces) == 0:
        return 0.5
    x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
    return (x + fw / 2) / gray.shape[1]


def _with_text(canvas: Image.Image, text: str, preset: str) -> Image.Image:
    if not text:
        return canvas
    style = captionstyles.resolve_headline(preset, {"seconds": 0})
    card = render_headline(text, style)                       # the same drawing as headlines on videos
    scale = canvas.width * 0.92 / card.width
    card = card.resize((round(card.width * scale), round(card.height * scale)), Image.LANCZOS)
    y = int(canvas.height * (0.06 if canvas.height > canvas.width else 0.04))
    out = canvas.convert("RGBA")
    out.alpha_composite(card, ((canvas.width - card.width) // 2, y))
    return out.convert("RGB")


def compose(job_id: str, clip_id: int, index: int, text: str, preset: str, m: dict, version: int = 0) -> dict:
    """Make both thumbnails from candidate `index`. Returns {"9x16": path, "16x9": path}."""
    frames = saved_candidates(job_id, clip_id, version)
    chosen = next((f for f in frames if f["index"] == index), None)
    if chosen is None:
        raise ValueError("Choose one of the frames first (find frames again if you edited the clip).")
    if text:
        text = captionstyles.clean_headline(text)
    if preset not in captionstyles.HEADLINE_PRESETS:
        raise ValueError(f"Unknown look '{preset}'.")
    out = folder_for(job_id, clip_id)
    results = {}
    with Image.open(out / f"frame_{index}.jpg") as portrait:
        tall = _cover(portrait.convert("RGB"), SIZES["9x16"])
    results["9x16"] = out / "thumbnail_9x16.png"
    _with_text(tall, text, preset).save(results["9x16"])

    # 16:9 from the source video at the same moment, cropped around the face
    source = jobs.job_dir(job_id) / "source.mp4"
    wide_src = out / "source_frame.jpg"
    if source.exists() and _frame(source, manifest.source_time(m, chosen["t"]), wide_src):
        with Image.open(wide_src) as im:
            im = im.convert("RGB")
            wide = _cover(im, SIZES["16x9"], _face_centre(im))
        wide_src.unlink(missing_ok=True)
    else:
        wide = _cover(tall, SIZES["16x9"])
    results["16x9"] = out / "thumbnail_16x9.png"
    _with_text(wide, text, preset).save(results["16x9"])
    return results
