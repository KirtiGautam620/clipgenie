"""The editing manifest: ONE description of how a clip is made, read by the renderer and the page.

    {"version": 1,
     "clip":        {"start": 0.0, "end": 25.14},            seconds in the source video (the cut)
     "framing":     {"mode": "crop" | "blur"},
     "effects":     {"zoom": 1.0, "pan": "none"},            see effects.py
     "fades":       {"in": 0.0, "out": 0.0},                 picture (and text) fade, seconds, 0 to 3
     "transitions": [],                                      RESERVED: must stay empty in version 1
     "text":        {"mode": "captions" | "pending" | "headline" | "none",
                     "captions": {"style": {...}, "words": [...]} | null,
                     "headline": {"text": "...", "style": {...}} | null},
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
import math
from copy import deepcopy

from app import effects, textmode

SCHEMA_VERSION = 1
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
        "framing": {"mode": "crop"},
        "effects": dict(effects.DEFAULT),
        "fades": {"in": 0.0, "out": 0.0},
        "transitions": [],
        "text": {"mode": "captions", "captions": None, "headline": None},
        "audio": {"clean_voice": True, "fade_with_video": True, "music": None},
    }


def from_clip(clip: dict) -> dict:
    """The manifest of a clip entry from clips.json (old or new). Does not change `clip`."""
    cut = clip.get("cut") or {}
    start = cut.get("cut_start", clip.get("start", 0.0))
    end = cut.get("cut_end", clip.get("end", start))
    m = default_manifest(start, end)
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
    if version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported manifest version {version!r}; this ClipGenie reads version "
                         f"{SCHEMA_VERSION}.")

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

    out = {"version": SCHEMA_VERSION, "clip": {"start": start, "end": end},
           "framing": {"mode": mode}, "effects": effects.normalize(_section(manifest, "effects"))}

    fades = _section(manifest, "fades")
    fade_in = _number(fades.get("in", 0.0), "fades.in", 0, MAX_FADE)
    fade_out = _number(fades.get("out", 0.0), "fades.out", 0, MAX_FADE)
    if fade_in + fade_out > end - start:
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
    out["text"] = {"mode": tmode, "captions": captions, "headline": headline if tmode == "headline" else None}

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


# ---------------------------------------------------------------- reading it (renderer)

def render_args(manifest: dict) -> dict:
    """Arguments for export.render_base (stage 1: picture + voice, no text)."""
    m = validate(manifest)
    return {"start": m["clip"]["start"], "end": m["clip"]["end"], "framing": m["framing"]["mode"],
            "clean_audio": m["audio"]["clean_voice"], "effects": m["effects"]}


def text_drawer_spec(manifest: dict) -> dict:
    """What goes on top of the picture (stage 2): {"kind": "captions"|"headline"|"none", ...}."""
    t = validate(manifest)["text"]
    if t["mode"] == "captions" and t["captions"] is not None:
        return {"kind": "captions", **t["captions"]}
    if t["mode"] == "headline":
        return {"kind": "headline", **t["headline"]}
    return {"kind": "none"}
