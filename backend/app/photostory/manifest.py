"""The Photo Story manifest: the one description of a project that everything else reads.

The renderer, the preview and the export all take only this, so what you preview is what you get.
`parse()` checks everything and raises ValueError with a sentence a person can act on; `to_dict()`
gives back plain data that can be saved as project.json.
"""
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app import captionstyles

SCHEMA_VERSION = 1
PROJECT_ID = re.compile(r"[0-9a-f]{12}")
SCENE_ID = re.compile(r"[a-z0-9_-]{1,32}")
IMAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.(jpg|jpeg|png)", re.IGNORECASE)

MAX_SCENES = 40
MIN_SCENE_SECONDS, MAX_SCENE_SECONDS = 1.0, 30.0
MIN_TRANSITION, MAX_TRANSITION = 0.2, 2.0
MAX_NARRATION_CHARS = 600
MAX_TITLE_CHARS = 120
MAX_EXCERPT_CHARS = 1000

MOTIONS = ("hold", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down")
FITS = ("fill", "blur")                       # fill = crop to 9:16, blur = whole photo over a blurred copy
TRANSITIONS = ("cut", "fade", "slide_left", "slide_right", "wipe_left")
RIGHTS = ("own", "permission", "licensed", "public_domain", "unsure")
PEOPLE = ("none", "consent", "no_consent")    # identifiable people in the photo, and whether they agreed
CLAIM_LABELS = ("user", "sourced", "storytelling")
VOICE_MODES = ("none", "upload", "tts")


def _text(value, what: str, limit: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{what} must be text.")
    value = re.sub(r"[ \t]+", " ", "".join(c for c in value if c.isprintable() or c in "\n ")).strip()
    if not value and not allow_empty:
        raise ValueError(f"{what} cannot be empty.")
    if len(value) > limit:
        raise ValueError(f"{what} must be at most {limit} characters.")
    return value


def _number(value, what: str, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be a number.")
    if not lo <= value <= hi:
        raise ValueError(f"{what} must be between {lo:g} and {hi:g}.")
    return float(value)


def _choice(value, what: str, allowed: tuple) -> str:
    if value not in allowed:
        raise ValueError(f"{what} must be one of: {', '.join(allowed)}.")
    return value


@dataclass
class Claim:
    text: str
    label: str                      # user | sourced | storytelling: nothing is shown as fact without one
    source_id: str | None = None


@dataclass
class Scene:
    id: str
    image: str                      # a file name inside the project's own folder
    duration: float = 5.0
    motion: str = "zoom_in"
    intensity: float = 0.5          # 0 = still, 1 = the strongest move
    fit: str = "fill"
    focus: tuple[float, float] = (0.5, 0.5)     # where to look, 0..1 across and down the photo
    transition: str = "fade"        # how this scene arrives (ignored for the first scene)
    transition_seconds: float = 0.6
    narration_text: str = ""
    narration_audio: str | None = None          # a file name inside the project's folder
    narration_seconds: float | None = None      # measured length of that audio
    claims: list[Claim] = field(default_factory=list)
    rights: str = "unsure"
    people: str = "none"


@dataclass
class Source:
    id: str
    title: str
    url: str
    retrieved: str                  # YYYY-MM-DD
    excerpt: str = ""


@dataclass
class Manifest:
    id: str
    title: str
    scenes: list[Scene]
    voice: dict = field(default_factory=lambda: {"mode": "none", "engine": None, "voice": None})
    music: dict = field(default_factory=lambda: {"track_id": None, "volume": 0.5})
    captions: dict = field(default_factory=lambda: {"on": False, "preset": captionstyles.DEFAULT_PRESET})
    headline: dict | None = None
    sources: list[Source] = field(default_factory=list)
    schema: int = SCHEMA_VERSION


# ---------------------------------------------------------------- parsing

def _parse_claim(raw: dict, where: str, source_ids: set) -> Claim:
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: a claim must be an object.")
    label = _choice(raw.get("label"), f"{where}: claim label", CLAIM_LABELS)
    source_id = raw.get("source_id")
    if label == "sourced" and source_id not in source_ids:
        raise ValueError(f"{where}: a claim marked 'sourced' must point to one of the project's sources.")
    if label != "sourced" and source_id is not None:
        raise ValueError(f"{where}: only 'sourced' claims can have a source.")
    return Claim(_text(raw.get("text"), f"{where}: claim text", MAX_NARRATION_CHARS), label, source_id)


def _parse_scene(raw: dict, n: int, source_ids: set) -> Scene:
    where = f"Scene {n}"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object.")
    scene_id = raw.get("id")
    if not isinstance(scene_id, str) or not SCENE_ID.fullmatch(scene_id):
        raise ValueError(f"{where}: id must be 1-32 letters, digits, dashes or underscores.")
    image = raw.get("image")
    if not isinstance(image, str) or not IMAGE_NAME.fullmatch(image):
        raise ValueError(f"{where}: image must be a plain .jpg or .png file name (no folders).")
    focus = raw.get("focus", (0.5, 0.5))
    if not isinstance(focus, (list, tuple)) or len(focus) != 2:
        raise ValueError(f"{where}: focus must be two numbers (across, down).")
    audio = raw.get("narration_audio")
    if audio is not None and (not isinstance(audio, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.(mp3|wav|m4a)", audio, re.I)):
        raise ValueError(f"{where}: narration audio must be a plain .mp3, .wav or .m4a file name.")
    seconds = raw.get("narration_seconds")
    return Scene(
        id=scene_id, image=image,
        duration=_number(raw.get("duration", 5.0), f"{where}: duration", MIN_SCENE_SECONDS, MAX_SCENE_SECONDS),
        motion=_choice(raw.get("motion", "zoom_in"), f"{where}: motion", MOTIONS),
        intensity=_number(raw.get("intensity", 0.5), f"{where}: intensity", 0, 1),
        fit=_choice(raw.get("fit", "fill"), f"{where}: fit", FITS),
        focus=(_number(focus[0], f"{where}: focus", 0, 1), _number(focus[1], f"{where}: focus", 0, 1)),
        transition=_choice(raw.get("transition", "fade"), f"{where}: transition", TRANSITIONS),
        transition_seconds=_number(raw.get("transition_seconds", 0.6), f"{where}: transition length",
                                   MIN_TRANSITION, MAX_TRANSITION),
        narration_text=_text(raw.get("narration_text", ""), f"{where}: narration", MAX_NARRATION_CHARS, True),
        narration_audio=audio,
        narration_seconds=None if seconds is None else _number(seconds, f"{where}: narration length", 0.1, 600),
        claims=[_parse_claim(c, where, source_ids) for c in raw.get("claims", [])],
        rights=_choice(raw.get("rights", "unsure"), f"{where}: image rights", RIGHTS),
        people=_choice(raw.get("people", "none"), f"{where}: people in the photo", PEOPLE),
    )


def _parse_source(raw: dict, n: int) -> Source:
    where = f"Source {n}"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object.")
    url = raw.get("url")
    parts = urlparse(url) if isinstance(url, str) else None
    if not parts or parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"{where}: url must be a web address starting with http:// or https://.")
    retrieved = raw.get("retrieved")
    if not isinstance(retrieved, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", retrieved):
        raise ValueError(f"{where}: retrieved must be a date like 2026-11-01.")
    source_id = raw.get("id")
    if not isinstance(source_id, str) or not SCENE_ID.fullmatch(source_id):
        raise ValueError(f"{where}: id must be 1-32 letters, digits, dashes or underscores.")
    return Source(source_id, _text(raw.get("title"), f"{where}: title", MAX_TITLE_CHARS), url, retrieved,
                  _text(raw.get("excerpt", ""), f"{where}: excerpt", MAX_EXCERPT_CHARS, True))


def parse(raw: dict) -> Manifest:
    """Check a project description and return it. Raises ValueError with a readable message."""
    if not isinstance(raw, dict):
        raise ValueError("The project must be an object.")
    if raw.get("schema", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ValueError(f"This project was saved by a different version (schema {raw.get('schema')}).")
    pid = raw.get("id")
    if not isinstance(pid, str) or not PROJECT_ID.fullmatch(pid):
        raise ValueError("The project id must be 12 lowercase hex characters.")

    sources = [_parse_source(s, i) for i, s in enumerate(raw.get("sources", []), 1)]
    source_ids = {s.id for s in sources}
    if len(source_ids) != len(sources):
        raise ValueError("Two sources share the same id.")

    scenes_raw = raw.get("scenes")
    if not isinstance(scenes_raw, list) or not scenes_raw:
        raise ValueError("A project needs at least one scene.")
    if len(scenes_raw) > MAX_SCENES:
        raise ValueError(f"A project can have at most {MAX_SCENES} scenes.")
    scenes = [_parse_scene(s, i, source_ids) for i, s in enumerate(scenes_raw, 1)]
    if len({s.id for s in scenes}) != len(scenes):
        raise ValueError("Two scenes share the same id.")

    voice = raw.get("voice", {"mode": "none"})
    if not isinstance(voice, dict):
        raise ValueError("voice must be an object.")
    mode = _choice(voice.get("mode", "none"), "Voice mode", VOICE_MODES)
    if mode == "tts" and not isinstance(voice.get("engine"), str):
        raise ValueError("A text-to-speech voice needs an engine name.")
    music = raw.get("music", {"track_id": None, "volume": 0.5})
    if not isinstance(music, dict) or not (music.get("track_id") is None or isinstance(music.get("track_id"), str)):
        raise ValueError("music must say which track (or none).")
    captions = raw.get("captions", {"on": False})
    if not isinstance(captions, dict) or not isinstance(captions.get("on", False), bool):
        raise ValueError("captions must say whether they are on.")
    preset = captions.get("preset", captionstyles.DEFAULT_PRESET)
    captionstyles.resolve(preset)                       # raises ValueError for an unknown look

    headline = raw.get("headline")
    if headline is not None:
        if not isinstance(headline, dict):
            raise ValueError("headline must be an object.")
        text = captionstyles.clean_headline(headline.get("text"))
        style = captionstyles.resolve_headline(headline.get("preset", captionstyles.DEFAULT_HEADLINE_PRESET),
                                               headline.get("style") or {})
        headline = {"text": text, "preset": style.preset, "style": style.as_dict()}

    return Manifest(
        id=pid, title=_text(raw.get("title"), "The title", MAX_TITLE_CHARS), scenes=scenes,
        voice={"mode": mode, "engine": voice.get("engine"), "voice": voice.get("voice")},
        music={"track_id": music.get("track_id"),
               "volume": _number(music.get("volume", 0.5), "Music volume", 0, 1)},
        captions={"on": captions.get("on", False), "preset": preset},
        headline=headline, sources=sources)


# ---------------------------------------------------------------- reading back

def to_dict(m: Manifest) -> dict:
    """Plain data, ready to save as project.json."""
    return {
        "schema": m.schema, "id": m.id, "title": m.title,
        "scenes": [{**{k: getattr(s, k) for k in (
            "id", "image", "duration", "motion", "intensity", "fit", "transition", "transition_seconds",
            "narration_text", "narration_audio", "narration_seconds", "rights", "people")},
            "focus": list(s.focus),
            "claims": [{"text": c.text, "label": c.label, "source_id": c.source_id} for c in s.claims]}
            for s in m.scenes],
        "voice": dict(m.voice), "music": dict(m.music), "captions": dict(m.captions),
        "headline": m.headline,
        "sources": [{"id": s.id, "title": s.title, "url": s.url, "retrieved": s.retrieved,
                     "excerpt": s.excerpt} for s in m.sources],
    }


def image_files(m: Manifest) -> list[str]:
    """Each photo file the project uses, once, in order."""
    seen: list[str] = []
    for s in m.scenes:
        if s.image not in seen:
            seen.append(s.image)
    return seen


def publish_blockers(m: Manifest) -> list[str]:
    """Reasons this project must not be exported yet (rights and consent), in plain language."""
    out = []
    for n, s in enumerate(m.scenes, 1):
        if s.rights == "unsure":
            out.append(f"Scene {n}: confirm that you have the right to use this photo.")
        if s.people == "no_consent":
            out.append(f"Scene {n}: the people in this photo have not agreed to appear in the video.")
    return out
