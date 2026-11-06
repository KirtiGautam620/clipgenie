"""Clean up the speaker's voice: rumble filter, light denoise (only if needed), loudness
levelling to a steady volume, and tiny fades so cuts never click.

voice_filter() looks at the clip's audio first and returns the FFmpeg filter text that export.py
puts into its command, plus a small report that is saved with the clip.
"""
import json
import math
import re
import subprocess
from pathlib import Path

TARGET_LUFS = -14.0     # about what YouTube / Instagram / TikTok play at
TARGET_TP = -1.5        # true-peak ceiling, dB
TARGET_LRA = 11.0
HIGHPASS_HZ = 80
MIN_INPUT_LUFS = -45.0   # quieter than this is hiss, not a voice: boosting it would only add noise
NOISY_FLOOR_DB = -50.0  # background quieter than this is left alone (denoise can sound watery)
MIN_FLOOR_GAP_DB = 12.0 # ...and it must sit this far below the speech, or it is not really a separate noise floor
DENOISE = "afftdn=nr=10:nf=-45:tn=1"
FADE_IN = 0.04
FADE_OUT = 0.15


def _ffmpeg_log(src: Path, start: float, duration: float, af: str) -> str:
    return subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
         "-i", str(src), "-vn", "-af", af, "-f", "null", "-"],
        capture_output=True, text=True).stderr


def has_audio(video: Path) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
         "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True).stdout
    return bool(out.strip())


def parse_rms_level(log: str) -> float | None:
    """Average level of the clip in dB (the 'Overall' RMS level from astats)."""
    found = re.findall(r"RMS level dB: (-?[\d.]+)", log)
    return float(found[-1]) if found else None


def parse_noise_floor(log: str) -> float | None:
    """The quietest stretch of the clip (astats' RMS trough), in dB. None if unreadable."""
    # FFmpeg 8 prints this as "RMS through" (a typo in FFmpeg), older/newer builds say "trough"
    found = re.findall(r"RMS (?:trough|through) dB: (-?[\d.]+|-inf)", log)
    if not found:
        return None
    try:
        value = float(found[-1])      # last match = the 'Overall' section
    except ValueError:
        return None
    return value if value != float("-inf") else None


def parse_loudnorm(log: str) -> dict | None:
    """Pull loudnorm's measurement JSON out of FFmpeg's log. None if the audio was silent."""
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", log, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        values = {k: float(data[k]) for k in
                  ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}
    except (ValueError, KeyError):      # a missing or unreadable field
        return None
    return values if all(math.isfinite(v) for v in values.values()) else None   # "-inf" = silence


def voice_filter(src: Path, start: float, duration: float,
                 out_duration: float | None = None) -> tuple[str | None, dict]:
    """Return (filter chain for [0:a], report). Filter is None when the video has no audio.
    The sound is measured over `duration` of the source; `out_duration` (when parts of the clip are
    removed first) is how long the finished sound is, so its end fade lands on its real end."""
    if not has_audio(src):
        return None, {"applied": False, "reason": "no audio"}

    stats = _ffmpeg_log(src, start, duration, "astats")
    floor, level = parse_noise_floor(stats), parse_rms_level(stats)
    # Only denoise when there is clear evidence: a quiet stretch that is itself fairly loud,
    # and well below the speech. A voice with no pauses has no measurable floor: leave it alone.
    denoise = (floor is not None and level is not None and floor > NOISY_FLOOR_DB
               and level - floor >= MIN_FLOOR_GAP_DB)
    base = [f"highpass=f={HIGHPASS_HZ}"] + ([DENOISE] if denoise else [])
    report = {"applied": True, "noise_floor_db": floor, "denoised": denoise,
              "target_lufs": TARGET_LUFS}

    target = f"I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}"
    measured = parse_loudnorm(_ffmpeg_log(
        src, start, duration, ",".join(base + [f"loudnorm={target}:print_format=json"])))
    chain = list(base)
    if measured and measured["input_i"] < MIN_INPUT_LUFS:
        report["loudness"] = f"skipped (audio is almost silent: {measured['input_i']:.0f} LUFS)"
    elif measured:
        chain.append(
            f"loudnorm={target}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true")
        report["input_lufs"] = measured["input_i"]
    else:
        report["loudness"] = "skipped (audio too quiet to measure)"
    length = out_duration if out_duration else duration
    fade_out = min(FADE_OUT, length / 3)
    chain += ["aresample=48000",       # loudnorm works at a high rate internally
              f"afade=t=in:st=0:d={FADE_IN}",
              f"afade=t=out:st={max(0.0, length - fade_out):.3f}:d={fade_out:.3f}"]
    return ",".join(chain), report
