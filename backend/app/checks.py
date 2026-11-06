"""Automatic quality checks on a finished video: is it a good file for a viewer?

Looks only at the finished video file (never the transcript), with plain FFmpeg analysis:
size and length, sound present, black frames, long silences, loudness. Findings are written in
everyday words. Nothing here ever stops or changes a video: a check that cannot run is reported as
"unchecked", and `safe_check` never raises.

    {"status": "ok" | "notes" | "problems" | "unchecked", "issues": [{"code", "level", "message"}],
     "metrics": {...}, "checked_at": "..."}
"""
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app import audiofx, manifest as manifest_mod

ENABLED = True
OUT_SIZE = (1080, 1920)
DURATION_TOLERANCE = 0.3       # seconds the finished length may differ from the plan
BLACK_MIN = 0.5                # a black stretch must last this long to matter
BLACK_FADE_SLACK = 0.3         # black at the ends is fine inside a fade (plus this much)
SILENCE_DB, SILENCE_MIN = -45, 2.0
LOUDNESS_QUIET, LOUDNESS_LOUD = -23.0, -8.0


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, timeout=180).stderr


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True, check=True, timeout=60).stdout
    data = json.loads(out)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
    return {"width": video.get("width"), "height": video.get("height"),
            "has_audio": any(s["codec_type"] == "audio" for s in data["streams"]),
            "duration": float(data["format"]["duration"])}


def _issue(code: str, level: str, message: str) -> dict:
    return {"code": code, "level": level, "message": message}


def check_clip(path: Path, m: dict) -> dict:
    """Check the finished video at `path` against the manifest it was made from."""
    info = _probe(path)
    issues, metrics = [], {"duration": round(info["duration"], 2), "size": [info["width"], info["height"]]}
    if (info["width"], info["height"]) != OUT_SIZE:
        issues.append(_issue("wrong_size", "problem", f"The video is {info['width']}×{info['height']}, not 1080×1920."))
    expected = manifest_mod.output_length(m)
    if abs(info["duration"] - expected) > DURATION_TOLERANCE:
        issues.append(_issue("wrong_length", "note",
                             f"The video is {info['duration']:.1f}s long; it should be about {expected:.1f}s."))

    # black frames (the start and end are allowed to be dark while a fade runs)
    fades = m["fades"]
    black = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vf",
                  f"blackdetect=d={BLACK_MIN}:pix_th=0.12", "-an", "-f", "null", "-"])
    spans = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", black)]
    bad = [(a, b) for a, b in spans
           if not (a <= 0.05 and b <= fades["in"] + BLACK_FADE_SLACK + 0.05)
           and not (b >= info["duration"] - 0.1 and a >= info["duration"] - fades["out"] - BLACK_FADE_SLACK - 0.05)]
    metrics["black_seconds"] = round(sum(b - a for a, b in bad), 2)
    if bad:
        issues.append(_issue("black_frames", "note", f"Part of the picture is black ({metrics['black_seconds']:.1f}s in total)."))

    if not info["has_audio"]:
        issues.append(_issue("no_audio", "note", "This video has no sound."))
    else:
        silence = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
                        f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN}", "-f", "null", "-"])
        longest = max((float(x) for x in re.findall(r"silence_duration: ([\d.]+)", silence)), default=0.0)
        metrics["longest_silence"] = round(longest, 2)
        if longest >= SILENCE_MIN:
            issues.append(_issue("long_silence", "note", f"There is a stretch of silence {longest:.1f}s long."))
        loud = audiofx.parse_loudnorm(_run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
                                           "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"]))
        if loud:
            metrics["loudness_lufs"] = round(loud["input_i"], 1)
            if loud["input_i"] < LOUDNESS_QUIET:
                issues.append(_issue("quiet", "note", "The sound is quiet; viewers may need to turn it up."))
            elif loud["input_i"] > LOUDNESS_LOUD:
                issues.append(_issue("loud", "note", "The sound is very loud."))

    text = m["text"]
    if text["mode"] == "captions" and text["captions"] is not None and not text["captions"]["words"]:
        issues.append(_issue("no_captions", "note", "No captions were drawn: no clear speech was found."))

    status = "problems" if any(i["level"] == "problem" for i in issues) else ("notes" if issues else "ok")
    return {"status": status, "issues": issues, "metrics": metrics,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def served_file(folder: Path, clip_id: int) -> Path:
    """The file the page plays and the download hands out: the music mix when there is one."""
    mixed = Path(folder) / f"clip_{clip_id}_music.mp4"
    return mixed if mixed.exists() else Path(folder) / f"clip_{clip_id}.mp4"


def safe_check(folder: Path, clip_id: int, m: dict) -> dict:
    """check_clip that never raises and can be switched off (tests that only need the video)."""
    unchecked = {"status": "unchecked", "issues": [], "metrics": {}}
    if not ENABLED:
        return unchecked
    try:
        path = served_file(folder, clip_id)
        return check_clip(path, m) if path.exists() else unchecked
    except Exception:
        return unchecked
