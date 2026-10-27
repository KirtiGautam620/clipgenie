"""Generate a few simple, original starter music tracks (one per mood).

Everything is synthesised from scratch with numpy, so there is no outside copyright:
the tracks are released as CC0 (public domain). They are plain placeholders so the music
features can be tried right away. Add your own licensed music for better results.

Run from the backend folder:   .venv/bin/python tools/make_starter_music.py
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.music import LIBRARY_FILE, MUSIC_DIR  # noqa: E402

SR = 44100
RNG = np.random.default_rng(7)


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def env(n: int, attack=0.01, release=0.2, decay=None) -> np.ndarray:
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(attack, 1e-4))
    e *= np.minimum(1, np.maximum(0, (n / SR - t)) / max(release, 1e-4))
    if decay:
        e *= np.exp(-t / decay)
    return e


def osc(freq: float, n: int, kind="sine") -> np.ndarray:
    ph = 2 * np.pi * freq * np.arange(n) / SR
    if kind == "tri":
        return 2 / np.pi * np.arcsin(np.sin(ph))
    if kind == "saw":
        return 2 * ((freq * np.arange(n) / SR) % 1) - 1
    return np.sin(ph)


def lowpass(x: np.ndarray, k: int) -> np.ndarray:
    return np.convolve(x, np.ones(k) / k, mode="same")


class Track:
    def __init__(self, seconds: float):
        self.buf = np.zeros(int(seconds * SR))

    def add(self, start: float, x: np.ndarray, gain: float = 1.0) -> None:
        i = int(start * SR)
        if i >= len(self.buf):
            return
        x = x[: len(self.buf) - i]
        self.buf[i:i + len(x)] += gain * x

    def pad(self, start, dur, midis, gain=0.12, kind="tri"):
        n = int(dur * SR)
        x = sum(osc(hz(m) * d, n, kind) for m in midis for d in (0.997, 1.003))
        self.add(start, x * env(n, 0.4, 0.6) / len(midis), gain)

    def pluck(self, start, midi, dur=0.5, gain=0.2, kind="tri", decay=0.18):
        n = int(dur * SR)
        self.add(start, osc(hz(midi), n, kind) * env(n, 0.004, 0.05, decay), gain)

    def bass(self, start, midi, dur=0.25, gain=0.3):
        n = int(dur * SR)
        self.add(start, osc(hz(midi), n, "sine") * env(n, 0.005, 0.08, 0.3), gain)

    def kick(self, start, gain=0.5):
        n = int(0.25 * SR)
        t = np.arange(n) / SR
        self.add(start, np.sin(2 * np.pi * (50 + 90 * np.exp(-t * 28)) * t) * np.exp(-t * 14), gain)

    def hat(self, start, gain=0.05):
        n = int(0.05 * SR)
        noise = RNG.standard_normal(n)
        self.add(start, (noise - lowpass(noise, 6)) * np.exp(-np.arange(n) / SR * 90), gain)

    def bell(self, start, midi, gain=0.14):
        n = int(4 * SR)
        x = sum(a * osc(hz(midi) * r, n) for r, a in ((1, 1), (2.76, 0.4), (5.4, 0.2)))
        self.add(start, x * env(n, 0.003, 0.5, 1.3), gain)


CHORDS = {"maj": [0, 4, 7], "min": [0, 3, 7], "maj7": [0, 4, 7, 11], "sus": [0, 5, 7]}


def chord(root: int, kind: str) -> list[int]:
    return [root + step for step in CHORDS[kind]]


def motivational(sec=64):
    bpm = 120; beat = 60 / bpm; t = Track(sec)
    prog = [(48, "maj"), (55, "maj"), (57, "min"), (53, "maj")]
    for bar in range(int(sec / (4 * beat))):
        root, kind = prog[bar % 4]; ch = chord(root, kind); s = bar * 4 * beat
        t.pad(s, 4 * beat, [m + 12 for m in ch])
        for b in range(4):
            t.kick(s + b * beat); t.hat(s + b * beat + beat / 2)
        for e in range(8):
            t.bass(s + e * beat / 2, root - 12, 0.2)
            t.pluck(s + e * beat / 2, ch[e % 3] + 24, 0.3, 0.09)
    return t.buf


def emotional(sec=64):
    bpm = 66; beat = 60 / bpm; t = Track(sec)
    prog = [(45, "min"), (41, "maj"), (48, "maj"), (43, "maj")]
    for bar in range(int(sec / (4 * beat))):
        root, kind = prog[bar % 4]; ch = chord(root, kind); s = bar * 4 * beat
        t.pad(s, 4 * beat + 0.5, [m + 12 for m in ch], 0.16)
        t.bass(s, root - 12, 2.5, 0.22)
        for b in range(4):
            t.pluck(s + b * beat, ch[b % 3] + 24, 1.4, 0.13, "sine", 0.6)
    return t.buf


def funny(sec=64):
    bpm = 132; beat = 60 / bpm; t = Track(sec)
    prog = [(48, "maj"), (53, "maj"), (55, "maj"), (48, "maj")]
    pent = [72, 74, 76, 79, 81, 84]
    for bar in range(int(sec / (4 * beat))):
        root, kind = prog[bar % 4]; ch = chord(root, kind); s = bar * 4 * beat
        for e in range(8):
            off = (beat / 6) if e % 2 else 0           # swing
            t.bass(s + e * beat / 2 + off, root - 12 + (7 if e % 4 == 2 else 0), 0.12, 0.3)
            t.hat(s + e * beat / 2 + off, 0.04)
        for b in (1, 3):
            t.pluck(s + b * beat, ch[0] + 12, 0.1, 0.18, "tri", 0.05)
        for _ in range(3):
            t.pluck(s + RNG.integers(0, 8) * beat / 2, int(RNG.choice(pent)), 0.15, 0.13, "tri", 0.07)
    return t.buf


def educational(sec=64):
    bpm = 92; beat = 60 / bpm; t = Track(sec)
    prog = [(50, "maj7"), (55, "maj"), (47, "min"), (52, "min")]
    for bar in range(int(sec / (4 * beat))):
        root, kind = prog[bar % 4]; ch = chord(root, kind); s = bar * 4 * beat
        t.pad(s, 4 * beat, [m + 12 for m in ch], 0.09)
        for e in range(8):
            t.pluck(s + e * beat / 2, ch[e % len(ch)] + 24, 0.5, 0.11, "tri", 0.25)
        t.bass(s, root - 12, 1.2, 0.2); t.hat(s + 2 * beat, 0.03)
    return t.buf


def spiritual(sec=64):
    t = Track(sec)
    t.pad(0, sec, [38, 45], 0.2, "sine")
    t.pad(0, sec, [62, 69, 74], 0.05, "sine")
    scale = [74, 76, 78, 81, 83, 86]
    for k in range(int(sec / 4.5)):
        t.bell(2 + k * 4.5 + RNG.uniform(-0.3, 0.3), int(RNG.choice(scale)))
    return t.buf


TRACKS = [
    ("starter-motivational", "Rising Steps (starter)", ["motivational"], motivational),
    ("starter-emotional", "Quiet Window (starter)", ["emotional"], emotional),
    ("starter-funny", "Bouncy Pockets (starter)", ["funny"], funny),
    ("starter-educational", "Clear Desk (starter)", ["educational", "other"], educational),
    ("starter-spiritual", "Still Water (starter)", ["spiritual"], spiritual),
]


def main() -> None:
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    existing = json.loads(LIBRARY_FILE.read_text()) if LIBRARY_FILE.exists() else []
    library = [t for t in existing if not t["id"].startswith("starter-")]
    for track_id, title, moods, fn in TRACKS:
        audio = fn()
        audio = audio / (np.abs(audio).max() or 1) * 0.8
        raw = MUSIC_DIR / f"{track_id}.f32"
        raw.write_bytes(audio.astype(np.float32).tobytes())
        mp3 = MUSIC_DIR / f"{track_id}.mp3"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1",
             "-i", str(raw), "-af", "aecho=0.8:0.5:70|140:0.25|0.15,lowpass=f=9000,"
             "stereotools=mlev=0.9", "-c:a", "libmp3lame", "-b:a", "128k", str(mp3)],
            check=True)
        raw.unlink()
        library.append({"id": track_id, "file": mp3.name, "title": title, "moods": moods,
                        "license": "cc0", "attribution": "",
                        "source": "Generated from scratch by backend/tools/make_starter_music.py"})
        print("made", mp3.name)
    LIBRARY_FILE.write_text(json.dumps(library, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
