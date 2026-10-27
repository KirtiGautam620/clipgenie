"""The music library: tracks in data/music/ plus a library.json with license information.

Only music YOU put there is ever used. Every track keeps its license and attribution
text. A track without a license record is still usable, but is flagged with a warning.
"""
import json
import re
import uuid
import zlib
from pathlib import Path

from app.config import DATA_DIR

MUSIC_DIR = DATA_DIR / "music"
LIBRARY_FILE = MUSIC_DIR / "library.json"
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
MOODS = ["motivational", "emotional", "funny", "educational", "spiritual", "other"]

# License choices shown in the UI. "attribution" = you must credit the artist.
LICENSES = {
    "cc0": "CC0 / public domain",
    "cc-by": "CC BY (credit the artist)",
    "royalty-free": "Royalty-free (I have a licence to use it)",
    "own": "I made it / I own it",
    "unknown": "Unknown licence",
}

# If no track has the clip's mood, try these instead (calmest first).
FALLBACK_MOODS = ["educational", "emotional", "other"]


def _load_raw() -> list[dict]:
    if LIBRARY_FILE.exists():
        return json.loads(LIBRARY_FILE.read_text())
    return []


def _save_raw(tracks: list[dict]) -> None:
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARY_FILE.write_text(json.dumps(tracks, ensure_ascii=False, indent=2))


def _warning(t: dict) -> str | None:
    if t["license"] == "unknown":
        return "Licence unknown. Do not publish clips with this track unless you are sure you may use it."
    if t["license"] == "cc-by" and not t.get("attribution"):
        return "This licence requires crediting the artist, but no credit text is saved."
    return None


def list_tracks() -> list[dict]:
    """All tracks, including audio files dropped into the folder without a record."""
    tracks = _load_raw()
    known = {t["file"] for t in tracks}
    if MUSIC_DIR.exists():
        for f in sorted(MUSIC_DIR.iterdir()):
            if f.suffix.lower() in AUDIO_SUFFIXES and f.name not in known:
                tracks.append({"id": f"file-{zlib.crc32(f.name.encode()):08x}", "file": f.name,
                               "title": f.stem, "moods": ["other"], "license": "unknown",
                               "attribution": "", "source": "Added to the folder by hand"})
    out = []
    for t in tracks:
        if (MUSIC_DIR / t["file"]).exists():
            out.append({**t, "license_label": LICENSES.get(t["license"], t["license"]),
                        "warning": _warning(t)})
    return out


def get_track(track_id: str) -> dict | None:
    return next((t for t in list_tracks() if t["id"] == track_id), None)


def track_path(track: dict) -> Path:
    return MUSIC_DIR / track["file"]


def add_track(data: bytes, filename: str, title: str, moods: list[str], license: str,
              attribution: str, source: str) -> dict:
    suffix = Path(filename).suffix.lower()
    if suffix not in AUDIO_SUFFIXES:
        raise ValueError("Music must be an MP3, WAV, M4A, OGG or FLAC file")
    if license not in LICENSES:
        raise ValueError("Unknown licence choice")
    moods = [m for m in moods if m in MOODS] or ["other"]
    track_id = uuid.uuid4().hex[:8]
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).stem)[:40] or "track"
    file = f"{safe}-{track_id}{suffix}"
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    (MUSIC_DIR / file).write_bytes(data)
    track = {"id": track_id, "file": file, "title": title.strip()[:80] or safe,
             "moods": moods, "license": license, "attribution": attribution.strip()[:300],
             "source": source.strip()[:300]}
    _save_raw(_load_raw() + [track])
    return track


def pick_track(mood: str, seed: str) -> dict | None:
    """Choose a track that fits the mood. `seed` makes the choice stable but varied."""
    tracks = list_tracks()
    if not tracks:
        return None
    for wanted in [mood, *FALLBACK_MOODS]:
        matches = [t for t in tracks if wanted in t["moods"]]
        if matches:
            return matches[zlib.crc32(seed.encode()) % len(matches)]
    return tracks[zlib.crc32(seed.encode()) % len(tracks)]
