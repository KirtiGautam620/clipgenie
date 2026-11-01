"""The animatic: a real video of the user's OWN photo moving through the storyboard's scenes.

It is not AI video. Each scene is the photo cropped and reframed from its start frame to its end frame
(exactly the two preview frames the page shows), with the scene's transition into the next one.

How it works: every frame is cut from the photo here with Pillow, using fractions of a pixel so slow
movement stays smooth, and handed straight to FFmpeg, which only encodes. Nothing is stored except
the finished file, and no model of any kind is used.

Safety on a small computer: one render at a time (the same lock the Shorts processing uses), FFmpeg
runs at low priority on two threads, a render can be cancelled, and it stops by itself if the
computer runs out of memory or disk.
"""
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from bisect import bisect_right
from pathlib import Path

from PIL import Image

from app import jobs, music, rights
from app.storyboard import frames, model, store

FPS = 25
SIZES = {"preview": {"9:16": (360, 640), "16:9": (640, 360)},
         "full": {"9:16": (1080, 1920), "16:9": (1920, 1080)}}
QUALITIES = tuple(SIZES)
CRF = {"preview": "26", "full": "18"}
MUSIC_LUFS = -16                     # a video with no voice: the music IS the sound, so it is levelled like finished audio
MIX_TIMEOUT = 300
MIN_FREE_DISK_GB = 1.0
MEMORY_RED = 4                       # kern.memorystatus_vm_pressure_level: 1 green, 2 yellow, 4 red
CHECK_EVERY = 50                     # frames between looks at the computer's memory
OUTPUT, STATUS = "animatic.mp4", "animatic.json"

_cancel: dict[str, threading.Event] = {}
_done: dict[str, threading.Event] = {}


class Busy(RuntimeError):
    """Something else is being processed (or this storyboard is already rendering)."""


# ---------------------------------------------------------------- timing (same rules as Photo Story)

def durations(scenes) -> list[float]:
    return [float(s.duration) for s in scenes]


def overlaps(scenes) -> list[float]:
    """Seconds each scene shares with the previous one: 0 for the first and for every hard cut,
    never more than half of either neighbour."""
    d = durations(scenes)
    out = [0.0]
    for i in range(1, len(scenes)):
        s = scenes[i]
        out.append(0.0 if s.transition == "cut" else min(s.transition_seconds, 0.5 * min(d[i - 1], d[i])))
    return out


def starts(scenes) -> list[float]:
    out, t = [], 0.0
    for d in durations(scenes):
        out.append(t)
        t += d
    return out


def total_seconds(scenes) -> float:
    return sum(durations(scenes))


def frame_count(scenes) -> int:
    return max(1, round(total_seconds(scenes) * FPS))


# ---------------------------------------------------------------- one frame

def ease(u: float) -> float:
    """Slow start and end, so a move never begins or stops with a jolt."""
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def box_at(start: tuple, end: tuple, u: float) -> tuple:
    e = ease(u)
    return tuple(a + (b - a) * e for a, b in zip(start, end))


def scene_frame(photo: Image.Image, start: tuple, end: tuple, duration: float, local_t: float,
                size: tuple[int, int]) -> Image.Image:
    """The scene at `local_t` seconds in (held on its first or last frame outside its own time)."""
    l, t, r, b = box_at(start, end, local_t / duration if duration > 0 else 1.0)
    pw, ph = photo.size
    return photo.resize(size, Image.BICUBIC, box=(l * pw, t * ph, r * pw, b * ph), reducing_gap=2.0)


def blend(a: Image.Image, b: Image.Image, kind: str, p: float) -> Image.Image:
    """The picture `p` (0..1) of the way through a transition from scene A to scene B."""
    w, h = a.size
    if kind == "fade":
        return Image.blend(a, b, p)
    if kind in ("slide_left", "slide_right"):
        dx = round(p * w)
        out = Image.new("RGB", (w, h))
        if kind == "slide_left":                      # the new picture arrives from the right
            out.paste(a, (-dx, 0))
            out.paste(b, (w - dx, 0))
        else:                                         # ... from the left
            out.paste(a, (dx, 0))
            out.paste(b, (dx - w, 0))
        return out
    if kind == "wipe_left":                           # the new picture is uncovered from the right edge
        edge = round(w * (1 - p))
        out = a.copy()
        if edge < w:
            out.paste(b.crop((edge, 0, w, h)), (edge, 0))
        return out
    return b


def compose(photo: Image.Image, scenes, boxes: list, begin: list, overlap: list, t: float,
            size: tuple[int, int]) -> Image.Image:
    """The finished frame at time t on the video's timeline."""
    i = max(0, bisect_right(begin, t + 1e-9) - 1)
    d = durations(scenes)
    frame = scene_frame(photo, *boxes[i], d[i], t - begin[i], size)
    if i > 0 and overlap[i] > 0 and t < begin[i] + overlap[i]:
        before = scene_frame(photo, *boxes[i - 1], d[i - 1], t - begin[i - 1], size)
        return blend(before, frame, scenes[i].transition, (t - begin[i]) / overlap[i])
    return frame


# ---------------------------------------------------------------- what is a render of, and is it out of date

def scene_boxes(sb: model.Storyboard) -> list[tuple]:
    return [frames.boxes(sb.photo["width"], sb.photo["height"], sb.aspect, s) for s in sb.scenes]


def music_info(sb: model.Storyboard) -> dict | None:
    """The chosen track with its licence, any warnings and the credit line to paste (None if no music)."""
    choice = sb.music.get("track_id")
    track = music.get_track(choice) if choice else None
    if track is None:
        return None
    info = {"track_id": track["id"], "title": track["title"], "volume": sb.music["volume"],
            "license": track["license_label"], "attribution": track["attribution"], "warning": track["warning"]}
    nothing_to_declare = {"rights": "own", "url": None, "title": "", "uploader": ""}   # only the music part is wanted
    return {**info, "warnings": rights.warnings(nothing_to_declare, {"music": info}),
            "credits": rights.credits_text(nothing_to_declare, {"music": info})}


def fingerprint(sb: model.Storyboard, quality: str) -> str:
    """Changes whenever something that changes the PICTURE or the SOUND changes (not titles or prompt text)."""
    picture = {"aspect": sb.aspect, "quality": quality,
               "music": [sb.music.get("track_id"), round(sb.music.get("volume", 0.7), 3)],
               "scenes": [[round(s.duration, 3), s.transition, round(s.transition_seconds, 3),
                           [round(v, 4) for box in boxes for v in box]]
                          for s, boxes in zip(sb.scenes, scene_boxes(sb))]}
    return hashlib.sha1(json.dumps(picture, sort_keys=True).encode()).hexdigest()[:16]


def status(sb: model.Storyboard) -> dict:
    """The latest render's state, and whether the storyboard has changed since."""
    path = store.folder(sb.id) / STATUS
    info = json.loads(path.read_text()) if path.exists() else {"state": "none"}
    if info.get("state") == "done":
        info["stale"] = info.get("fingerprint") != fingerprint(sb, info.get("quality", "preview"))
    if info.get("state") == "rendering" and sb.id not in _cancel:       # the server restarted mid-render
        info = {"state": "error", "error": "The render was interrupted. Please start it again."}
    return info


def _write(sid: str, **info) -> dict:
    jobs.write_atomic(store.folder(sid) / STATUS, json.dumps(info))
    return info


# ---------------------------------------------------------------- is it safe to start (and to go on)?

def _pressure() -> int | None:
    try:
        out = subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], capture_output=True,
                             text=True, timeout=5).stdout.strip()
        return int(out) if out.isdigit() else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def trouble(folder: Path) -> str | None:
    """A sentence if the computer should not be asked to render right now, else None."""
    free = shutil.disk_usage(folder).free / 1e9
    if free < MIN_FREE_DISK_GB:
        return f"There is only {free:.1f} GB of disk space left. Free some up and try again."
    level = _pressure()
    if level is not None and level >= MEMORY_RED:
        return "Your Mac is very short of memory right now. Close some apps and try again."
    return None


# ---------------------------------------------------------------- the render

def _encoder(out: Path, size: tuple[int, int], quality: str) -> subprocess.Popen:
    cmd = (["nice", "-n", "10"] if shutil.which("nice") else []) + [
        "ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
        "-r", str(FPS), "-i", "-", "-an",
        # the picture is RGB: say which colour standard to convert to, so players show the right colours
        "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", CRF[quality], "-threads", "2",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
        "-movflags", "+faststart", str(out)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def _mix_music(silent: Path, track_file: Path, out: Path, volume: float, seconds: float) -> None:
    """Put the track under the finished picture: levelled, faded in and out, looped if it is short.
    The picture is copied as it is, so this takes a second or two."""
    fade_out = min(1.5, seconds / 3)
    graph = (f"[1:a]atrim=0:{seconds:.3f},asetpts=PTS-STARTPTS,loudnorm=I={MUSIC_LUFS}:TP=-1.5:LRA=11,"
             f"aresample=48000,volume={volume:.3f},afade=t=in:st=0:d=0.5,afade=t=out:st={seconds - fade_out:.3f}:d={fade_out:.3f},"
             f"alimiter=limit=0.95[a]")
    cmd = (["nice", "-n", "10"] if shutil.which("nice") else []) + [
        "ffmpeg", "-loglevel", "error", "-y", "-i", str(silent), "-stream_loop", "-1", "-i", str(track_file),
        "-filter_complex", graph, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
        "-t", f"{seconds:.3f}", "-movflags", "+faststart", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=MIX_TIMEOUT)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"The music could not be added: {e.stderr[-300:]}") from e


def render(sid: str, quality: str, cancel: threading.Event) -> dict:
    """Make the video from the SAVED storyboard. Blocking; updates animatic.json as it goes."""
    sb = store.load(sid)
    folder = store.folder(sid)
    size = SIZES[quality][sb.aspect]
    n = frame_count(sb.scenes)
    base = {"quality": quality, "frames": n, "fingerprint": fingerprint(sb, quality),
            "seconds": round(total_seconds(sb.scenes), 2), "started": time.time(), "music": music_info(sb)}
    partial, final = folder / "animatic.partial.mp4", folder / OUTPUT
    mixed = folder / "animatic.mixed.mp4"
    proc = None
    try:
        if sb.music.get("track_id") and base["music"] is None:      # chosen, but gone from the library
            raise RuntimeError("The chosen music track is not in your library any more.")
        boxes, begin, overlap = scene_boxes(sb), starts(sb.scenes), overlaps(sb.scenes)
        with Image.open(store.photo_path(sid)) as opened:
            photo = opened.convert("RGB")
        proc = _encoder(partial, size, quality)
        for k in range(n):
            if cancel.is_set():
                try:
                    proc.stdin.close()
                except OSError:
                    pass
                proc.kill()
                proc.wait()
                partial.unlink(missing_ok=True)
                return _write(sid, state="cancelled", **base)
            if k % CHECK_EVERY == 0 and k:
                level = _pressure()
                if level is not None and level >= MEMORY_RED:
                    raise RuntimeError("Stopped because your Mac ran short of memory. Close some apps and try again.")
            proc.stdin.write(compose(photo, sb.scenes, boxes, begin, overlap, k / FPS, size).tobytes())
            if k % 10 == 0:
                _write(sid, state="rendering", progress=round(k / n, 3), **base)
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise RuntimeError(f"The video could not be encoded: {err[-300:]}")
        if base["music"]:
            track = music.get_track(base["music"]["track_id"])
            if track is None:
                raise RuntimeError("The chosen music track is not in your library any more.")
            _write(sid, state="rendering", phase="music", progress=1.0, **base)
            _mix_music(partial, music.track_path(track), mixed, base["music"]["volume"], n / FPS)
            os.replace(mixed, final)
            partial.unlink(missing_ok=True)
        else:
            os.replace(partial, final)
        return _write(sid, state="done", progress=1.0, bytes=final.stat().st_size, finished=time.time(), **base)
    except Exception as e:                       # shown on the page; never leaves a half-made file behind
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()
        partial.unlink(missing_ok=True)
        mixed.unlink(missing_ok=True)
        message = str(e) if isinstance(e, RuntimeError) else f"The video could not be made ({type(e).__name__})."
        try:
            return _write(sid, state="error", error=message, **base)
        except OSError:                          # the folder is gone (the storyboard was deleted)
            return {"state": "error", "error": message}


def start(sid: str, quality: str):
    """Check that a render may begin, take the one heavy-work slot, and return the function to run it
    (the caller runs it in the background). Raises ValueError or Busy."""
    from app.pipeline import heavy_job_lock          # the lock Shorts processing uses: one heavy job at a time
    if quality not in QUALITIES:
        raise ValueError(f"quality must be one of: {', '.join(QUALITIES)}")
    store.photo_path(sid)                            # 404-style error for an unknown storyboard
    wanted = store.load(sid).music.get("track_id")
    if wanted and music.get_track(wanted) is None:
        raise ValueError("The chosen music track is not in your library any more. Pick another or choose no music.")
    problem = trouble(store.folder(sid))
    if problem:
        raise Busy(problem)
    if sid in _cancel:
        raise Busy("This storyboard is already being rendered.")
    if not heavy_job_lock.acquire(blocking=False):
        raise Busy("ClipGenie is busy processing a video. Try again in a minute.")
    cancel, done = threading.Event(), threading.Event()
    _cancel[sid], _done[sid] = cancel, done
    try:
        (store.folder(sid) / OUTPUT).unlink(missing_ok=True)       # the status always describes the file that exists
        _write(sid, state="rendering", progress=0.0, quality=quality)
    except Exception:
        _cancel.pop(sid, None), _done.pop(sid, None)
        heavy_job_lock.release()
        raise

    def run():
        try:
            render(sid, quality, cancel)
        finally:
            _cancel.pop(sid, None)
            heavy_job_lock.release()
            done.set()
            _done.pop(sid, None)
    return run


def cancel(sid: str, wait: float = 0.0) -> bool:
    """Ask a running render to stop; optionally wait for it. True if there was one."""
    event, done = _cancel.get(sid), _done.get(sid)
    if event is None:
        return False
    event.set()
    if done is not None and wait:
        done.wait(wait)
    return True
