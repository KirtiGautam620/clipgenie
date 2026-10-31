"""Natural clip boundaries: start a little before the first word and end a little after the
last one, and move each cut into a real pause when there is one nearby.

Whisper's word times are often 50-200 ms off, so cutting exactly on them can clip the first
consonant or chop the last word. Cutting inside a measured silence avoids that.
"""
import re
import subprocess
from pathlib import Path

import numpy as np

PRE_ROLL = 0.25        # seconds of breathing space before the first word
TAIL = 0.4             # seconds after the last word
SNAP_BEFORE = 0.6      # look this far before the start for a pause to cut in
SNAP_AFTER = 0.8       # ... and this far after the end
WORD_GUARD = 0.03      # never get closer than this to a neighbouring word
MIN_SILENCE = 0.15     # shorter gaps are not treated as pauses
SENTENCE_END = ".?!।"
FRAME = 0.01           # loudness is measured every 10 ms
TIE_DB = 1.5           # points this close to the quietest count as equally quiet: take the nearest

Silence = tuple[float, float]


# ---------------------------------------------------------------- measuring the audio

def probe_duration(media: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(media)], capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def silence_threshold(mean_volume_db: float) -> float:
    """Quiet-enough level for a pause: 14 dB under the average, kept within sane limits."""
    return max(-50.0, min(-30.0, mean_volume_db - 14))


def parse_silences(log: str, media_end: float) -> list[Silence]:
    """Read silencedetect's log. A silence still open at the end of the file ends there."""
    out, open_at = [], None
    for line in log.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            open_at = max(0.0, float(m.group(1)))
            continue
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and open_at is not None:
            out.append((open_at, float(m.group(1))))
            open_at = None
    if open_at is not None and media_end > open_at:
        out.append((open_at, media_end))
    return out


def detect_silences(wav: Path) -> list[Silence]:
    """Find the pauses in a whole recording (one quick pass over a small mono WAV)."""
    end = probe_duration(wav)
    vol = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af", "volumedetect",
         "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: (-?[\d.]+) dB", vol)
    if not m:       # silent or unreadable audio: no pauses to report
        return []
    noise = silence_threshold(float(m.group(1)))
    log = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af",
         f"silencedetect=noise={noise:.0f}dB:d={MIN_SILENCE}", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    return parse_silences(log, end)


def load_envelope(wav: Path) -> np.ndarray:
    """Loudness (dB) of every 10 ms of the recording, lightly smoothed over 30 ms.
    Real speech has gaps between words that are too short for silencedetect: this finds them."""
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(wav), "-f", "s16le", "-ac", "1", "-ar", "16000",
         "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float64) / 32768
    size = int(16000 * FRAME)
    frames = x[: len(x) // size * size].reshape(-1, size)
    rms = np.sqrt((frames ** 2).mean(axis=1)) if len(frames) else np.zeros(0)
    rms = np.convolve(rms, np.ones(3) / 3, mode="same") if len(rms) else rms
    return 20 * np.log10(np.maximum(rms, 1e-6))


def _quietest(env: np.ndarray, lo: float, hi: float, near: float) -> float | None:
    """The quietest moment between lo and hi (nearest to `near` among the equally quiet ones)."""
    i0, i1 = int(np.ceil(lo / FRAME)), min(int(hi / FRAME), len(env) - 1)
    if i1 <= i0:
        return None
    seg = env[i0:i1 + 1]
    idx = np.nonzero(seg <= seg.min() + TIE_DB)[0] + i0
    best = min(idx, key=lambda i: abs(i * FRAME + FRAME / 2 - near))
    return float(best * FRAME + FRAME / 2)


def _level(env: np.ndarray | None, t: float) -> float | None:
    if env is None or not len(env):
        return None
    return round(float(env[min(len(env) - 1, max(0, int(t / FRAME)))]), 1)


# ---------------------------------------------------------------- choosing the cut points

def _snap_start(start: float, lower: float, silences: list[Silence]) -> tuple[float, bool]:
    ideal = max(lower, start - PRE_ROLL)
    ideal = min(ideal, start - WORD_GUARD)
    near = [(s, e) for s, e in silences
            if e > start - SNAP_BEFORE and s < start - WORD_GUARD]
    for s, e in near:                       # already inside a pause: keep the ideal point
        if s <= ideal <= e:
            return ideal, True
    if near:                                # otherwise use the pause that ends closest to the word
        s, e = max(near, key=lambda p: p[1])
        cut = max(s, min(e, start) - PRE_ROLL)
        return max(lower, min(cut, start - WORD_GUARD)), True
    return ideal, False


def _snap_end(end: float, upper: float, silences: list[Silence]) -> tuple[float, bool]:
    ideal = min(upper, end + TAIL)
    ideal = max(ideal, end + WORD_GUARD)
    near = [(s, e) for s, e in silences
            if s < end + SNAP_AFTER and e > end + WORD_GUARD]
    for s, e in near:
        if s <= ideal <= e:
            return ideal, True
    if near:
        s, e = min(near, key=lambda p: p[0])
        cut = min(e, max(s, end) + TAIL)
        return min(upper, max(cut, end + WORD_GUARD)), True
    return ideal, False


def refine(words: list[dict], silences: list[Silence], start: float, end: float,
           media_end: float, envelope: np.ndarray | None = None) -> dict:
    """Return the padded cut points for a clip whose speech runs from `start` to `end`.

    A cut goes (1) inside a real pause if there is one close by, else (2) at the quietest
    moment of the padding window (needs `envelope`), else (3) a plain pre-roll / tail.

    {"cut_start", "cut_end", "start_snapped", "end_snapped", "clean_end", "edge_db"}
    """
    before = [w["end"] for w in words if w["end"] <= start + 0.01]
    after = [w["start"] for w in words if w["start"] >= end - 0.01]
    lower = (max(before) + WORD_GUARD) if before else 0.0
    upper = (min(after) - WORD_GUARD) if after else media_end
    upper = min(upper, media_end)

    cut_start, start_snapped = _snap_start(start, lower, silences)
    cut_end, end_snapped = _snap_end(end, upper, silences)
    if envelope is not None:
        if not start_snapped:
            lo, hi = max(lower, start - PRE_ROLL), start - WORD_GUARD
            cut_start = _quietest(envelope, lo, hi, start) or cut_start
        if not end_snapped:
            lo, hi = end + WORD_GUARD, min(upper, end + TAIL)
            cut_end = _quietest(envelope, lo, hi, end) or cut_end
    cut_start = min(start, max(0.0, lower, cut_start))   # never later than the first word
    cut_end = max(end, min(cut_end, upper))              # never earlier than the last word
    last = next((w["word"].strip() for w in reversed(words) if w["end"] <= end + 0.01), "")
    return {"cut_start": round(cut_start, 3), "cut_end": round(cut_end, 3),
            "start_snapped": start_snapped, "end_snapped": end_snapped,
            "edge_db": [_level(envelope, cut_start), _level(envelope, cut_end)],
            "clean_end": bool(last) and last[-1] in SENTENCE_END}
