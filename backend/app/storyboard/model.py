"""The storyboard as data: what is saved, what the page edits, and what is checked.

`parse()` checks everything and raises ValueError with a sentence a person can act on. The photo
facts (file, size) always come from the server, never from what the page sends back.
"""
import re
from dataclasses import dataclass, field

from app.photostory.manifest import PEOPLE, RIGHTS, _choice, _number, _text
from app.storyboard.shots import ASPECTS, MOTIONS, SHOTS, STYLES, TRANSITIONS

SCHEMA = 1
STORYBOARD_ID = re.compile(r"[0-9a-f]{12}")
SCENE_ID = re.compile(r"[a-z0-9_-]{1,32}")
MIN_SCENES_SAVED, MAX_SCENES_SAVED = 1, 12
DURATION = (1.0, 10.0)
ZOOM = (1.0, 3.0)
TRANSITION_SECONDS = (0.2, 2.0)
TITLE_MAX, PROJECT_TITLE_MAX, PRODUCT_MAX, PROMPT_MAX = 60, 80, 200, 1000
FIELD_MAX, SCENE_PROMPT_MAX = 300, 1500
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
TRACK_ID = re.compile(r"[A-Za-z0-9_.-]{1,80}")
DEFAULT_MUSIC = {"track_id": None, "volume": 0.7}


@dataclass
class Scene:
    id: str
    title: str
    shot: str                       # a shot from the library, or "custom"
    camera: str                     # what the shot should look like (for the external AI)
    detail: str                     # what it should show
    prompt: str                     # the text to paste into the external generator
    duration: float
    zoom: float                     # preview framing of the photo: 1 = widest, higher = closer
    focus: tuple[float, float]      # where to look in the photo, 0..1 across and down
    motion: str
    intensity: float
    transition: str                 # how this scene arrives
    transition_seconds: float


@dataclass
class Storyboard:
    id: str
    title: str
    photo: dict                     # {"file", "width", "height"}: set by the server
    aspect: str
    style: str
    product: str
    prompt: str
    scenes: list[Scene]
    rights: str = "unsure"
    people: str = "none"
    music: dict = field(default_factory=lambda: dict(DEFAULT_MUSIC))     # for the animatic: {"track_id", "volume"}
    plan: dict = field(default_factory=lambda: {"understood": {}, "notes": []})
    created: str = ""
    updated: str = ""
    schema: int = SCHEMA


def _scene(raw: dict, n: int) -> Scene:
    where = f"Scene {n}"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object.")
    sid = raw.get("id")
    if not isinstance(sid, str) or not SCENE_ID.fullmatch(sid):
        raise ValueError(f"{where}: id must be 1-32 letters, digits, dashes or underscores.")
    shot = raw.get("shot", "custom")
    if shot != "custom" and shot not in SHOTS:
        raise ValueError(f"{where}: unknown shot '{shot}'.")
    focus = raw.get("focus", (0.5, 0.5))
    if not isinstance(focus, (list, tuple)) or len(focus) != 2:
        raise ValueError(f"{where}: focus must be two numbers (across, down).")
    return Scene(
        id=sid, title=_text(raw.get("title"), f"{where}: title", TITLE_MAX), shot=shot,
        camera=_text(raw.get("camera", ""), f"{where}: camera", FIELD_MAX, True),
        detail=_text(raw.get("detail", ""), f"{where}: detail", FIELD_MAX, True),
        prompt=_text(raw.get("prompt", ""), f"{where}: prompt", SCENE_PROMPT_MAX, True),
        duration=_number(raw.get("duration"), f"{where}: duration", *DURATION),
        zoom=_number(raw.get("zoom", 1.0), f"{where}: zoom", *ZOOM),
        focus=(_number(focus[0], f"{where}: focus", 0, 1), _number(focus[1], f"{where}: focus", 0, 1)),
        motion=_choice(raw.get("motion", "hold"), f"{where}: motion", MOTIONS),
        intensity=_number(raw.get("intensity", 0.5), f"{where}: intensity", 0, 1),
        transition=_choice(raw.get("transition", "fade"), f"{where}: transition", TRANSITIONS),
        transition_seconds=_number(raw.get("transition_seconds", 0.6), f"{where}: transition length",
                                   *TRANSITION_SECONDS))


def parse(raw: dict, photo: dict | None = None) -> Storyboard:
    """Check a storyboard and return it. `photo` (from the server) replaces whatever the page sent."""
    if not isinstance(raw, dict):
        raise ValueError("The storyboard must be an object.")
    sid = raw.get("id")
    if not isinstance(sid, str) or not STORYBOARD_ID.fullmatch(sid):
        raise ValueError("The storyboard id must be 12 lowercase hex characters.")
    photo = photo if photo is not None else raw.get("photo")
    if (not isinstance(photo, dict) or photo.get("file") != "photo.jpg"
            or any(not isinstance(photo.get(k), int) or photo[k] < 1 for k in ("width", "height"))):
        raise ValueError("The storyboard has no valid photo.")
    scenes_raw = raw.get("scenes")
    if not isinstance(scenes_raw, list) or not MIN_SCENES_SAVED <= len(scenes_raw) <= MAX_SCENES_SAVED:
        raise ValueError(f"A storyboard needs {MIN_SCENES_SAVED} to {MAX_SCENES_SAVED} scenes.")
    scenes = [_scene(s, i) for i, s in enumerate(scenes_raw, 1)]
    if len({s.id for s in scenes}) != len(scenes):
        raise ValueError("Two scenes share the same id.")
    music = raw.get("music") or dict(DEFAULT_MUSIC)
    if not isinstance(music, dict) or not (music.get("track_id") is None or (
            isinstance(music.get("track_id"), str) and TRACK_ID.fullmatch(music["track_id"]))):
        raise ValueError("The music must name a track from your library, or none.")
    plan = raw.get("plan") or {"understood": {}, "notes": []}
    if not isinstance(plan, dict) or not isinstance(plan.get("notes", []), list):
        raise ValueError("The plan notes must be a list.")
    for key in ("created", "updated"):
        if raw.get(key, "") and not (isinstance(raw[key], str) and TIMESTAMP.match(raw[key])):
            raise ValueError(f"{key} must be a timestamp.")
    return Storyboard(
        id=sid, title=_text(raw.get("title"), "The title", PROJECT_TITLE_MAX),
        photo={"file": "photo.jpg", "width": photo["width"], "height": photo["height"]},
        aspect=_choice(raw.get("aspect", "9:16"), "Aspect", ASPECTS),
        style=_choice(raw.get("style", "none"), "Style", STYLES),
        product=_text(raw.get("product", ""), "The product description", PRODUCT_MAX, True),
        prompt=_text(raw.get("prompt", ""), "The prompt", PROMPT_MAX, True), scenes=scenes,
        rights=_choice(raw.get("rights", "unsure"), "Image rights", RIGHTS),
        people=_choice(raw.get("people", "none"), "People in the photo", PEOPLE),
        music={"track_id": music.get("track_id"), "volume": _number(music.get("volume", 0.7), "Music volume", 0, 1)},
        plan={"understood": plan.get("understood", {}), "notes": [str(n)[:300] for n in plan.get("notes", [])[:20]]},
        created=raw.get("created", ""), updated=raw.get("updated", ""))


def to_dict(sb: Storyboard) -> dict:
    return {
        "schema": sb.schema, "id": sb.id, "title": sb.title, "photo": dict(sb.photo), "aspect": sb.aspect,
        "style": sb.style, "product": sb.product, "prompt": sb.prompt, "rights": sb.rights, "people": sb.people,
        "music": dict(sb.music), "plan": sb.plan, "created": sb.created, "updated": sb.updated,
        "scenes": [{"id": s.id, "title": s.title, "shot": s.shot, "camera": s.camera, "detail": s.detail,
                    "prompt": s.prompt, "duration": s.duration, "zoom": s.zoom, "focus": list(s.focus),
                    "motion": s.motion, "intensity": s.intensity, "transition": s.transition,
                    "transition_seconds": s.transition_seconds} for s in sb.scenes]}


def export_blockers(sb: Storyboard) -> list[str]:
    """Reasons the prompts and package must not be handed out yet (rights and consent)."""
    out = []
    if sb.rights == "unsure":
        out.append("Confirm that you have the right to use this photo.")
    if sb.people == "no_consent":
        out.append("The people in this photo have not agreed to appear in a video.")
    return out
