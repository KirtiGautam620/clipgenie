"""Editing styles: the choices Auto Edit makes, written down as a named set of settings.

A style is plain data. It does not add a second editing engine: every decision in a style (how
captions look, how long pauses may be, whether a hook is suggested, the fades, a slow zoom, the
music level) is something the manifest and the renderer already do. Choosing a style at creation
makes the plan use these choices, and applying one to a finished video changes the manifest to match.

    {"name": "Punchy Shorts", "description": "...",
     "caption_preset": "pill",                      one of captionstyles.PRESETS
     "pauses": "off" | "natural" | "tight",          how hard long silences are tightened
     "hook": {"enabled": true, "seconds": 3, "preset": "poster"},
     "effects": {"zoom": 1.1, "pan": "none"},        see effects.py
     "fades": {"in": 0.0, "out": 0.4},
     "music": {"enabled": true, "volume": 0.5} | null,     null = use the music choice made at creation
     "framing": "crop" | "blur" | null}                    null = use the framing choice made at creation

"Natural" is what Auto Edit always did: it has no opinion on framing or music, so choosing it changes
nothing. Styles you save yourself live in data/styles.json, never inside a project.
"""
import copy
import json
import os
import uuid
from pathlib import Path

from app import captionstyles, effects
from app.config import DATA_DIR

USER_FILE = DATA_DIR / "styles.json"
MAX_USER_STYLES = 20
DEFAULT_STYLE = "natural"

# How firmly long pauses are tightened (see cuts.pause_segments): the shortest pause that is touched,
# the beat of silence that stays on each side of a cut, and the most that may be removed from a clip.
PAUSE_LEVELS = {
    "off": None,
    "natural": {"min_pause": 0.8, "keep": 0.25, "max_fraction": 0.35},
    "tight": {"min_pause": 0.5, "keep": 0.15, "max_fraction": 0.45},
}

BUILTIN = {
    "natural": {
        "name": "Natural", "description": "Keeps the speaker's rhythm: only long pauses are shortened.",
        "caption_preset": "clean", "pauses": "natural",
        "hook": {"enabled": True, "seconds": 3, "preset": "poster"},
        "effects": {"zoom": 1.0, "pan": "none"}, "fades": {"in": 0.0, "out": 0.0},
        "music": None, "framing": None},
    "punchy": {
        "name": "Punchy Shorts", "description": "Fast and energetic: tight pauses, a slow push-in, big captions.",
        "caption_preset": "bold_pop", "pauses": "tight",
        "hook": {"enabled": True, "seconds": 3, "preset": "banner"},
        "effects": {"zoom": 1.12, "pan": "none"}, "fades": {"in": 0.0, "out": 0.4},
        "music": {"enabled": True, "volume": 0.5}, "framing": "crop"},
    "calm": {
        "name": "Calm Story", "description": "Unhurried: pauses kept, gentle fades, softer captions.",
        "caption_preset": "subtitle", "pauses": "off",
        "hook": {"enabled": True, "seconds": 4, "preset": "title"},
        "effects": {"zoom": 1.06, "pan": "none"}, "fades": {"in": 0.6, "out": 0.8},
        "music": {"enabled": True, "volume": 0.7}, "framing": None},
    "podcast": {
        "name": "Podcast Highlight", "description": "Clean and focused on the voice: natural pauses, no hook, light music.",
        "caption_preset": "pill", "pauses": "natural",
        "hook": {"enabled": False, "seconds": 3, "preset": "poster"},
        "effects": {"zoom": 1.0, "pan": "none"}, "fades": {"in": 0.3, "out": 0.5},
        "music": {"enabled": True, "volume": 0.3}, "framing": "crop"},
}


# ---------------------------------------------------------------- checking a style

def _number(value, name: str, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        raise ValueError(f"{name} must be a number between {lo:g} and {hi:g}.")
    return float(value)


def validate(profile: dict) -> dict:
    """A tidy copy of a style, or ValueError with a readable reason."""
    if not isinstance(profile, dict):
        raise ValueError("A style must be an object.")
    name = " ".join(str(profile.get("name", "")).split())
    if not 1 <= len(name) <= 40:
        raise ValueError("A style needs a name of 1 to 40 characters.")
    preset = profile.get("caption_preset")
    if preset not in captionstyles.PRESETS:
        raise ValueError(f"Unknown caption look '{preset}'.")
    pauses = profile.get("pauses")
    if pauses not in PAUSE_LEVELS:
        raise ValueError("pauses must be off, natural or tight.")
    hook = profile.get("hook") or {}
    if not isinstance(hook.get("enabled"), bool):
        raise ValueError("hook.enabled must be true or false.")
    hook_preset = hook.get("preset", captionstyles.DEFAULT_HEADLINE_PRESET)
    if hook_preset not in captionstyles.HEADLINE_PRESETS:
        raise ValueError(f"Unknown headline look '{hook_preset}'.")
    seconds = int(_number(hook.get("seconds", 3), "hook.seconds", 2, 8))
    fades = profile.get("fades") or {}
    music = profile.get("music")
    if music is not None:
        if not isinstance(music.get("enabled"), bool):
            raise ValueError("music.enabled must be true or false.")
        music = {"enabled": music["enabled"], "volume": round(_number(music.get("volume", 0.6), "music.volume", 0, 1), 2)}
    framing = profile.get("framing")
    if framing not in (None, "crop", "blur"):
        raise ValueError("framing must be crop, blur or empty.")
    return {"name": name, "description": " ".join(str(profile.get("description", "")).split())[:120],
            "caption_preset": preset, "pauses": pauses,
            "hook": {"enabled": hook["enabled"], "seconds": seconds, "preset": hook_preset},
            "effects": effects.normalize(profile.get("effects")),
            "fades": {"in": round(_number(fades.get("in", 0.0), "fades.in", 0, 3), 2),
                      "out": round(_number(fades.get("out", 0.0), "fades.out", 0, 3), 2)},
            "music": music, "framing": framing}


def pause_params(level: str) -> dict | None:
    """The settings cuts.pause_segments should use for a pause level (None = leave pauses alone)."""
    return copy.deepcopy(PAUSE_LEVELS[level])


# ---------------------------------------------------------------- finding and saving styles

def _read_user() -> dict:
    try:
        data = json.loads(Path(USER_FILE).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_user(styles: dict) -> None:
    path = Path(USER_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(styles, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def get(style_id: str) -> dict | None:
    """A style by id (built-in or saved by the user), validated, with its id and whether it is built in."""
    if style_id in BUILTIN:
        return {"id": style_id, "builtin": True, **validate(BUILTIN[style_id])}
    saved = _read_user().get(style_id)
    if saved is None:
        return None
    try:
        return {"id": style_id, "builtin": False, **validate(saved)}
    except ValueError:
        return None          # a damaged saved style is ignored, never a crash


def all_styles() -> list[dict]:
    """Every style: the built-in ones first, then the user's own."""
    out = [get(k) for k in BUILTIN]
    for key in _read_user():
        style = get(key)
        if style:
            out.append(style)
    return out


def save_user(profile: dict) -> dict:
    """Save a new style for the user. Returns it with its id."""
    clean = validate(profile)
    saved = _read_user()
    if len(saved) >= MAX_USER_STYLES:
        raise ValueError(f"You can keep up to {MAX_USER_STYLES} saved styles. Delete one first.")
    style_id = f"u-{uuid.uuid4().hex[:8]}"
    saved[style_id] = clean
    _write_user(saved)
    return {"id": style_id, "builtin": False, **clean}


def delete_user(style_id: str) -> None:
    if style_id in BUILTIN:
        raise ValueError("Built-in styles cannot be deleted.")
    saved = _read_user()
    if style_id not in saved:
        raise KeyError("Unknown style")
    del saved[style_id]
    _write_user(saved)


def from_manifest(m: dict, name: str, description: str = "", pauses: str = "natural",
                  hook_seconds: int = 3, hook_preset: str = captionstyles.DEFAULT_HEADLINE_PRESET) -> dict:
    """The style that describes how a finished video was edited (so it can be reused on other videos)."""
    caps = m["text"]["captions"]
    preset = (caps["style"].get("preset") if caps else None) or captionstyles.DEFAULT_PRESET
    music = m["audio"]["music"]
    return validate({
        "name": name, "description": description, "caption_preset": preset, "pauses": pauses,
        "hook": {"enabled": True, "seconds": hook_seconds, "preset": hook_preset},
        "effects": m["effects"], "fades": m["fades"],
        "music": {"enabled": music is not None, "volume": (music or {}).get("volume", 0.6)},
        "framing": m["framing"]["mode"]})
