"""The editing manifest: ONE description of how a clip is made, read by the renderer and the page.

    {"version": 1,
     "clip":        {"start": 0.0, "end": 25.14},            seconds in the source video (the cut)
     "segments":    [{"start": 0.0, "end": 25.14}],          the parts of it that are kept, in order;
                                                             gaps between them are removed (pauses)
     "framing":     {"mode": "crop" | "blur"},
     "effects":     {"zoom": 1.0, "pan": "none"},            see effects.py
     "fades":       {"in": 0.0, "out": 0.0},                 picture (and text) fade, seconds, 0 to 3
     "transitions": [],                                      RESERVED: must stay empty in version 1
     "text":        {"mode": "captions" | "pending" | "headline" | "none",
                     "captions": {"style": {...}, "words": [...]} | null,
                     "headline": {"text": "...", "style": {...}} | null,
                     "hook":     {"text": "...", "style": {...}} | null},   a title card over the first
                                                                           seconds, WITH captions or no text
     "audio":       {"clean_voice": true,
                     "fade_with_video": true,                 the sound fades with the picture
                     "music": {"track_id": "...", "volume": 0.6} | null}}

Where it comes from: nothing new is stored. `from_clip()` builds the manifest from the clip entry
already saved in clips.json, so every existing job has one. Missing parts get defaults that give
exactly the output the app made before (centre/face crop, no zoom, no fades, voice cleaned).

Who reads it:
  * the renderer: `render_args()` turns it into the arguments of export.render_base, and
    `text_drawer_spec()` says what text goes on top (pipeline.set_clip_effects does both);
  * the page: GET /api/jobs/{job}/clips/{n}/manifest returns the same document, so a preview of
    an effect can be computed from the very settings the export will use.

`transitions` is reserved: it must stay empty until a clip can have more than one segment, because
accepting a value the renderer would ignore would make preview and export disagree.
Words of a clip whose speech is not trusted are never put in the manifest (see textmode.py).
"""
import copy
import json
import math
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from app import captionstyles, effects, textmode

SCHEMA_VERSION = 2
ACCEPTED_VERSIONS = (1, 2)      # version 1 documents (no segments) are read and upgraded
MIN_SEGMENT_SECONDS = 0.2
FRAMINGS = ("crop", "blur")
TEXT_MODES = ("captions", "pending", "headline", "none")
MAX_FADE = 3.0
MIN_CLIP_SECONDS = 1.0
MAX_WORDS = 20000


# ---------------------------------------------------------------- building

def default_manifest(start: float, end: float) -> dict:
    """The manifest that reproduces today's output for a cut from `start` to `end`."""
    return {
        "version": SCHEMA_VERSION,
        "clip": {"start": float(start), "end": float(end)},
        "segments": [{"start": float(start), "end": float(end)}],
        "framing": {"mode": "crop"},
        "effects": dict(effects.DEFAULT),
        "fades": {"in": 0.0, "out": 0.0},
        "transitions": [],
        "text": {"mode": "captions", "captions": None, "headline": None, "hook": None},
        "audio": {"clean_voice": True, "fade_with_video": True, "music": None},
    }


def from_clip(clip: dict) -> dict:
    """The manifest of a clip entry from clips.json (old or new). Does not change `clip`."""
    cut = clip.get("cut") or {}
    start = cut.get("cut_start", clip.get("start", 0.0))
    end = cut.get("cut_end", clip.get("end", start))
    m = default_manifest(start, end)
    if clip.get("segments"):
        m["segments"] = deepcopy(clip["segments"])
    if clip.get("framing_choice") in FRAMINGS:
        m["framing"]["mode"] = clip["framing_choice"]
    if clip.get("effects"):
        m["effects"] = {**m["effects"], **clip["effects"]}
    # settings that only the manifest knows about are saved on the clip under their own names
    if clip.get("fades"):
        m["fades"] = {**m["fades"], **clip["fades"]}
    if "fade_with_video" in clip:
        m["audio"]["fade_with_video"] = clip["fade_with_video"]
    if "clean_voice" in clip:
        m["audio"]["clean_voice"] = clip["clean_voice"]

    state = textmode.text_state(clip)
    mode = state.get("mode") if state.get("mode") in TEXT_MODES else "captions"
    m["text"]["mode"] = mode
    caps = clip.get("captions")
    if mode == "captions" and caps and not textmode.is_untrusted(clip):
        m["text"]["captions"] = {"style": deepcopy(caps.get("style", {})),
                                 "words": deepcopy(caps.get("words", []))}
    hook = state.get("hook")
    if hook and hook.get("approved") and mode in ("captions", "none"):     # only an APPROVED hook is drawn
        m["text"]["hook"] = {"text": hook.get("text", ""), "style": deepcopy(hook.get("style", {}))}
    head = state.get("headline")
    if mode == "headline" and head:
        m["text"]["headline"] = {"text": head.get("text", ""), "style": deepcopy(head.get("style", {}))}

    music = clip.get("music")
    if music:
        m["audio"]["music"] = {"track_id": music.get("track_id"), "volume": music.get("volume", 0.6)}
    return m


# ---------------------------------------------------------------- checking

def _number(value, name: str, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a number.")
    if not lo <= value <= hi:
        raise ValueError(f"{name} must be between {lo:g} and {hi:g}.")
    return float(value)


def _section(m: dict, key: str, kind=dict):
    value = m.get(key)
    if not isinstance(value, kind):
        raise ValueError(f"The manifest needs a '{key}' section.")
    return value


def validate(manifest: dict) -> dict:
    """Check a manifest and return a tidy copy. Raises ValueError with a readable sentence."""
    if not isinstance(manifest, dict):
        raise ValueError("The manifest must be an object.")
    version = manifest.get("version")
    if version not in ACCEPTED_VERSIONS:
        raise ValueError(f"Unsupported manifest version {version!r}; this ClipGenie reads versions "
                         f"{', '.join(map(str, ACCEPTED_VERSIONS))}.")

    span = _section(manifest, "clip")
    start = _number(span.get("start"), "clip.start", 0, 86400 * 4)
    end = _number(span.get("end"), "clip.end", 0, 86400 * 4)
    if end <= start:
        raise ValueError("clip.end must be after clip.start.")
    if end - start < MIN_CLIP_SECONDS:
        raise ValueError(f"A video must be at least {MIN_CLIP_SECONDS:g} second long.")

    mode = _section(manifest, "framing").get("mode")
    if mode not in FRAMINGS:
        raise ValueError("framing.mode must be crop or blur.")

    segments = _check_segments(manifest.get("segments"), start, end)
    kept = sum(s["end"] - s["start"] for s in segments)
    if kept < MIN_CLIP_SECONDS:
        raise ValueError(f"A video must be at least {MIN_CLIP_SECONDS:g} second long.")

    out = {"version": SCHEMA_VERSION, "clip": {"start": start, "end": end}, "segments": segments,
           "framing": {"mode": mode}, "effects": effects.normalize(_section(manifest, "effects"))}

    fades = _section(manifest, "fades")
    fade_in = _number(fades.get("in", 0.0), "fades.in", 0, MAX_FADE)
    fade_out = _number(fades.get("out", 0.0), "fades.out", 0, MAX_FADE)
    if fade_in + fade_out > kept:
        raise ValueError("The fades together are longer than the video.")
    out["fades"] = {"in": round(fade_in, 2), "out": round(fade_out, 2)}
    if _section(manifest, "transitions", list):
        raise ValueError("Transitions are not supported yet: transitions must be empty.")
    out["transitions"] = []

    text = _section(manifest, "text")
    tmode = text.get("mode")
    if tmode not in TEXT_MODES:
        raise ValueError("text.mode must be captions, pending, headline or none.")
    captions, headline = text.get("captions"), text.get("headline")
    if tmode != "captions" and captions:
        raise ValueError("Captions are only allowed when text.mode is captions.")
    if tmode != "headline" and headline:
        raise ValueError("A headline is only allowed when text.mode is headline.")
    if tmode == "headline":
        if not isinstance(headline, dict) or not str(headline.get("text", "")).strip():
            raise ValueError("A headline needs its text.")
        headline = {"text": str(headline["text"]), "style": dict(headline.get("style") or {})}
    if captions is not None:
        captions = _check_captions(captions, end - start)
    hook = text.get("hook")
    if hook:
        if tmode not in ("captions", "none"):
            raise ValueError("A hook can only be shown together with captions or with no other text.")
        if not isinstance(hook, dict) or not str(hook.get("text", "")).strip():
            raise ValueError("A hook needs its text.")
        style = dict(hook.get("style") or {})
        try:                                    # checked with the same rules as a headline's look
            style = captionstyles.resolve_headline(style.get("preset") or captionstyles.DEFAULT_HEADLINE_PRESET,
                                                   {k: v for k, v in style.items() if k != "preset"}).as_dict()
            hook = {"text": captionstyles.clean_headline(hook["text"]), "style": style}
        except ValueError as e:
            raise ValueError(f"The hook is not usable: {e}")
    else:
        hook = None
    out["text"] = {"mode": tmode, "captions": captions, "headline": headline if tmode == "headline" else None,
                   "hook": hook}

    audio = _section(manifest, "audio")
    clean = audio.get("clean_voice", True)
    if not isinstance(clean, bool):
        raise ValueError("audio.clean_voice must be true or false.")
    music = audio.get("music")
    if music is not None:
        if not isinstance(music, dict) or not music.get("track_id"):
            raise ValueError("audio.music needs a track_id.")
        music = {"track_id": str(music["track_id"]),
                 "volume": _number(music.get("volume", 0.6), "audio.music.volume", 0, 1)}
    fade_audio = audio.get("fade_with_video", True)
    if not isinstance(fade_audio, bool):
        raise ValueError("audio.fade_with_video must be true or false.")
    out["audio"] = {"clean_voice": clean, "fade_with_video": fade_audio, "music": music}
    return out


def _check_captions(captions, length: float) -> dict:
    if not isinstance(captions, dict) or not isinstance(captions.get("words"), list):
        raise ValueError("captions needs a list of words.")
    words = captions["words"]
    if len(words) > MAX_WORDS:
        raise ValueError("Too many caption words.")
    clean = []
    for i, w in enumerate(words):
        if not isinstance(w, dict) or not str(w.get("text", "")).strip():
            raise ValueError(f"Caption word {i + 1} needs text.")
        s = _number(w.get("start"), f"Caption word {i + 1} start", 0, length + 5)
        e = _number(w.get("end"), f"Caption word {i + 1} end", 0, length + 5)
        if e < s:
            raise ValueError(f"Caption word {i + 1} ends before it starts.")
        clean.append({**w, "text": str(w["text"]), "start": s, "end": e})
    return {"style": dict(captions.get("style") or {}), "words": clean}


def _check_segments(segments, start: float, end: float) -> list[dict]:
    """The kept parts of the clip, tidied: missing means the whole clip; parts are cut to the clip's
    range (so trimming just works), sorted, and may not overlap."""
    if segments is None:
        return [{"start": start, "end": end}]
    if not isinstance(segments, list) or not segments:
        raise ValueError("segments must be a list with at least one part.")
    kept = []
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            raise ValueError(f"Segment {i + 1} must be an object.")
        s = _number(seg.get("start"), f"Segment {i + 1} start", 0, 86400 * 4)
        e = _number(seg.get("end"), f"Segment {i + 1} end", 0, 86400 * 4)
        s, e = max(s, start), min(e, end)
        if e - s >= MIN_SEGMENT_SECONDS:
            kept.append({"start": round(s, 3), "end": round(e, 3)})
    if not kept:
        raise ValueError("None of the kept parts are inside the video's range.")
    kept.sort(key=lambda s: s["start"])
    for a, b in zip(kept, kept[1:]):
        if b["start"] < a["end"] - 0.001:
            raise ValueError("The kept parts of the video overlap.")
    return kept


def output_length(m: dict) -> float:
    """How long the finished video is: the kept parts added up."""
    return sum(s["end"] - s["start"] for s in m["segments"])


def is_cut(m: dict) -> bool:
    """True when parts of the clip are removed (so the video is shorter than its range)."""
    return abs(output_length(m) - (m["clip"]["end"] - m["clip"]["start"])) > 0.01


def source_time(m: dict, t: float) -> float:
    """A moment of the finished video (seconds from its start) -> the same moment in the source video."""
    done = 0.0
    for seg in m["segments"]:
        length = seg["end"] - seg["start"]
        if t <= done + length + 1e-9:
            return seg["start"] + max(0.0, t - done)
        done += length
    return m["segments"][-1]["end"]


def remap_words(words: list[dict], m: dict) -> list[dict]:
    """Caption words are stored in time from the clip's start. When parts are removed, the picture
    moves earlier by the removed time, so the words must too. A word that is cut in two, or sits
    in a removed part, is dropped."""
    if not is_cut(m):
        return words
    origin, out, done = m["clip"]["start"], [], 0.0
    for seg in m["segments"]:
        lo, hi = seg["start"] - origin, seg["end"] - origin
        for w in words:
            if w["start"] >= lo - 0.03 and w["end"] <= hi + 0.03:
                out.append({**w, "start": max(0.0, done + max(w["start"], lo) - lo),
                            "end": done + min(w["end"], hi) - lo})
        done += hi - lo
    return out


def trim_captions(captions: dict, offset: float, length: float) -> dict:
    """Caption words after the video's start moved later by `offset` seconds and its length became
    `length`: times shift earlier by `offset`; a word that is cut in half by either new edge is
    dropped, because it would show text whose sound is no longer fully there."""
    kept = []
    for w in captions["words"]:
        s, e = w["start"] - offset, w["end"] - offset
        if s >= -0.05 and e <= length + 0.05:
            kept.append({**w, "start": max(0.0, s), "end": min(length, e)})
    return {"style": copy.deepcopy(captions["style"]), "words": kept}


def check_renderable(manifest: dict) -> None:
    """Can the renderer rebuild this clip from the manifest alone? Raises ValueError if not.
    Clips made before captions were stored have their words burned in: redrawing them would
    silently drop the captions, so they cannot be re-rendered."""
    t = manifest["text"]
    if t["mode"] == "captions" and t["captions"] is None:
        raise ValueError("This clip was made before its captions could be changed, so its picture "
                         "cannot be remade without losing them. Make new clips from this video.")


# ---------------------------------------------------------------- the saved manifest

HISTORY_KEEP = 20


def store_path(folder: Path, clip_id: int) -> Path:
    return Path(folder) / f"clip_{clip_id}.manifest.json"


def load(folder: Path, clip_id: int) -> dict | None:
    """The manifest saved for a clip (the one its current video was made from), or None."""
    path = store_path(folder, clip_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())["current"]
    except (ValueError, KeyError, OSError):
        return None


def save(folder: Path, clip_id: int, manifest: dict, reason: str = "") -> None:
    """Make `manifest` the clip's saved manifest. The one it replaces goes into a short history
    (newest first), so an earlier version can be brought back later."""
    path = store_path(folder, clip_id)
    history = []
    if path.exists():
        try:
            old = json.loads(path.read_text())
            history = [{"manifest": old["current"], "saved_at": old.get("saved_at"), "reason": old.get("reason", "")},
                       *old.get("history", [])][:HISTORY_KEEP]
        except (ValueError, KeyError, OSError):
            history = []
    doc = {"current": manifest, "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "reason": reason, "history": history}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False))
    os.replace(tmp, path)


def baseline_path(folder: Path, clip_id: int) -> Path:
    return Path(folder) / f"clip_{clip_id}.baseline.json"


def save_baseline(folder: Path, clip_id: int, manifest: dict, edit: dict | None = None) -> None:
    """Keep the manifest ClipGenie made for a new clip, untouched by later edits, so the user can
    always go back to it. `edit` = how it was made (mode and style), saved beside it."""
    path = baseline_path(folder, clip_id)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"manifest": manifest, "edit": edit or {}}, ensure_ascii=False))
    os.replace(tmp, path)


def load_baseline(folder: Path, clip_id: int) -> tuple[dict, dict] | None:
    """(the AI's manifest, how it was made) for a clip, or None for clips made before this existed."""
    try:
        doc = json.loads(baseline_path(folder, clip_id).read_text())
        return validate(doc["manifest"]), doc.get("edit", {})
    except (OSError, ValueError, KeyError):
        return None


def current(folder: Path, clip: dict) -> dict:
    """The clip's manifest, validated: the saved one when there is one, else built from the clip
    entry (every project made before manifests were saved works this way)."""
    saved = load(folder, clip["id"])
    if saved is not None:
        try:
            m = validate(saved)
        except ValueError:
            m = None
        if m is not None:
            if textmode.is_untrusted(clip):
                m["text"]["captions"] = None      # never from an untrusted transcript
            return m
    return validate(from_clip(clip))


# ---------------------------------------------------------------- reading it (renderer)

def render_args(manifest: dict) -> dict:
    """Arguments for export.render_base (stage 1: picture + voice, no text)."""
    m = validate(manifest)
    return {"start": m["clip"]["start"], "end": m["clip"]["end"], "framing": m["framing"]["mode"],
            "clean_audio": m["audio"]["clean_voice"], "effects": m["effects"],
            "segments": [(s["start"], s["end"]) for s in m["segments"]] if is_cut(m) else None}


def text_drawer_spec(manifest: dict) -> dict:
    """What goes on top of the picture (stage 2): {"kind": "captions"|"headline"|"none", ...}."""
    m = validate(manifest)
    t = m["text"]
    if t["mode"] == "captions" and t["captions"] is not None:
        return {"kind": "captions", "style": t["captions"]["style"], "hook": t["hook"],
                "words": remap_words(t["captions"]["words"], m)}       # in time of the finished video
    if t["mode"] == "headline":
        return {"kind": "headline", **t["headline"]}
    return {"kind": "none", "hook": t["hook"]}
