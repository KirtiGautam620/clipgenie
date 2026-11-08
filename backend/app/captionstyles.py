"""How captions look: a few polished presets, and the settings a user may change.

A style is plain data (colours, size, position...). captions.py turns data + style into video,
so the preview and the export always show the same thing.
"""
import re
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"   # Poppins: Latin + Devanagari
WEIGHTS = {"semibold": "Poppins-SemiBold.ttf", "bold": "Poppins-Bold.ttf",
           "extrabold": "Poppins-ExtraBold.ttf",
           "handwritten": "Caveat-Regular.ttf"}      # Caveat (OFL, see assets/fonts/Caveat-OFL.txt): Latin only
ANIMATIONS = ("none", "highlight", "pop")   # none = the whole line stays the same colour
BOXES = ("none", "pill", "bar")             # pill = behind the spoken word, bar = behind the line
SCRIPTS = ("original", "hinglish")          # hinglish = Hindi words in Roman letters (see hinglish.py)

# Keep captions clear of the Shorts buttons and description (percent of the video height).
POSITION_MIN, POSITION_MAX = 20, 78

HEX = re.compile(r"#[0-9a-fA-F]{6}")


@dataclass(frozen=True)
class CaptionStyle:
    preset: str = "clean"
    weight: str = "semibold"
    size: int = 76               # pixels, at 1080 wide
    text_color: str = "#FFFFFF"
    highlight_color: str = "#FFB84D"
    position: int = 66           # vertical centre of the captions, % of the video height
    animation: str = "highlight"
    uppercase: bool = False
    words_per_line: int = 4      # most words shown together
    box: str = "none"
    outline: int = 0             # pixels of dark edge around letters
    shadow: bool = True
    script: str = "original"     # how Hindi words are written: as heard, or in Hinglish

    def as_dict(self) -> dict:
        return asdict(self)


PRESETS = {
    "clean": {
        "label": "Clean", "description": "White letters with a soft shadow; the spoken word glows amber.",
        "style": dict(weight="semibold", size=76, highlight_color="#FFB84D", animation="highlight",
                      box="none", outline=0, shadow=True, uppercase=False, words_per_line=4)},
    "pill": {
        "label": "Pill", "description": "The spoken word sits on a rounded colour pill.",
        "style": dict(weight="bold", size=70, highlight_color="#FFB84D", animation="pop",
                      box="pill", outline=0, shadow=True, uppercase=False, words_per_line=3)},
    "bold_pop": {
        "label": "Bold Pop", "description": "Big capitals with a dark edge; the spoken word pops.",
        "style": dict(weight="extrabold", size=84, highlight_color="#FFD400", animation="pop",
                      box="none", outline=7, shadow=False, uppercase=True, words_per_line=3)},
    "subtitle": {
        "label": "Subtitle", "description": "A calm, steady line on a soft dark bar. Good for teaching.",
        "style": dict(weight="semibold", size=54, highlight_color="#FFFFFF", animation="none",
                      box="bar", outline=0, shadow=False, uppercase=False, words_per_line=6,
                      position=72)},
}
DEFAULT_PRESET = "clean"

LIMITS = {"size": (36, 120), "position": (POSITION_MIN, POSITION_MAX),
           "words_per_line": (1, 8), "outline": (0, 12)}


def preset_list() -> list[dict]:
    """What the page shows in its list of looks."""
    return [{"id": k, "label": v["label"], "description": v["description"],
             "style": resolve(k).as_dict()} for k, v in PRESETS.items()]


def resolve(preset: str = DEFAULT_PRESET, overrides: dict | None = None) -> CaptionStyle:
    """Preset + the user's changes -> a checked style. Raises ValueError for anything invalid."""
    if preset not in PRESETS:
        raise ValueError(f"Unknown caption look '{preset}'")
    values = {**PRESETS[preset]["style"], **(overrides or {})}
    values.pop("preset", None)
    allowed = {f.name for f in fields(CaptionStyle)} - {"preset"}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"Unknown caption setting: {', '.join(sorted(unknown))}")

    style = replace(CaptionStyle(), preset=preset, **values)
    for name, (lo, hi) in LIMITS.items():
        value = getattr(style, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a number")
        style = replace(style, **{name: int(min(hi, max(lo, value)))})   # out of range: clamp
    for name in ("text_color", "highlight_color"):
        if not isinstance(getattr(style, name), str) or not HEX.fullmatch(getattr(style, name)):
            raise ValueError(f"{name} must look like #RRGGBB")
    for name, allowed_values in (("weight", tuple(WEIGHTS)), ("animation", ANIMATIONS), ("box", BOXES),
                                 ("script", SCRIPTS)):
        if getattr(style, name) not in allowed_values:
            raise ValueError(f"{name} must be one of: {', '.join(allowed_values)}")
    if not isinstance(style.uppercase, bool) or not isinstance(style.shadow, bool):
        raise ValueError("uppercase and shadow must be true or false")
    return style


def font_path(weight: str) -> Path:
    return FONT_DIR / WEIGHTS[weight]


def contrast_text(hex_color: str) -> str:
    """Dark or white text, whichever reads better on this background colour."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return "#151515" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#FFFFFF"


# ================================================================== headlines
# A headline is NOT a subtitle: it is a title the user wrote (or approved), shown as a poster-style
# card for a few seconds. It is used when the speech cannot be turned into trustworthy captions.

HEADLINE_BOXES = ("none", "card", "banner")   # card = dark rounded card with an accent rule,
                                              # banner = solid accent colour, none = bare text
HEADLINE_POSITION_MIN, HEADLINE_POSITION_MAX = 10, 72
HEADLINE_MAX_CHARS = 120


@dataclass(frozen=True)
class HeadlineStyle:
    preset: str = "poster"
    weight: str = "extrabold"
    size: int = 74
    text_color: str = "#FFFFFF"
    accent_color: str = "#FFB84D"
    position: int = 24          # vertical centre, % of the video height
    uppercase: bool = False
    seconds: int = 4            # how long it stays on screen; 0 = the whole clip
    box: str = "card"
    shadow: bool = True
    accent_last: bool = False   # True: the last word is drawn in accent_color (no box looks)

    def as_dict(self) -> dict:
        return asdict(self)


HEADLINE_PRESETS = {
    "poster": {
        "label": "Poster", "description": "A dark rounded card with an accent rule, near the top.",
        "style": dict(weight="extrabold", size=74, accent_color="#FFB84D", position=24, box="card",
                      uppercase=False, seconds=4, shadow=True)},
    "banner": {
        "label": "Banner", "description": "Bold text on a solid colour banner.",
        "style": dict(weight="bold", size=64, accent_color="#FFB84D", position=28, box="banner",
                      uppercase=False, seconds=4, shadow=False)},
    "title": {
        "label": "Title", "description": "Big plain capitals with a soft shadow, no box.",
        "style": dict(weight="extrabold", size=82, accent_color="#FFB84D", position=26, box="none",
                      uppercase=True, seconds=3, shadow=True)},
    "handwritten": {
        "label": "Handwritten", "description": "Thin hand-drawn capitals in white, near the top, no box.",
        "style": dict(weight="handwritten", size=96, text_color="#FFFFFF", accent_color="#FFFFFF", position=24,
                      box="none", uppercase=True, seconds=4, shadow=True)},
    "plain": {
        "label": "Plain", "description": "White text near the top, no box, the last word in red.",
        "style": dict(weight="extrabold", size=74, accent_color="#E53935", position=24, box="none",
                      uppercase=False, seconds=4, shadow=True, accent_last=True)},
}
DEFAULT_HEADLINE_PRESET = "poster"
DEFAULT_HOOK_PRESET = "plain"          # a heading (hook) over the top of a short: white, red last word, no box

HEADLINE_LIMITS = {"size": (40, 110), "position": (HEADLINE_POSITION_MIN, HEADLINE_POSITION_MAX),
                   "seconds": (0, 15)}


def headline_preset_list() -> list[dict]:
    return [{"id": k, "label": v["label"], "description": v["description"],
             "style": resolve_headline(k).as_dict()} for k, v in HEADLINE_PRESETS.items()]


def resolve_headline(preset: str = DEFAULT_HEADLINE_PRESET, overrides: dict | None = None) -> HeadlineStyle:
    """Preset + the user's changes -> a checked headline style. Raises ValueError for anything invalid."""
    if preset not in HEADLINE_PRESETS:
        raise ValueError(f"Unknown headline look '{preset}'")
    values = {**HEADLINE_PRESETS[preset]["style"], **(overrides or {})}
    values.pop("preset", None)
    allowed = {f.name for f in fields(HeadlineStyle)} - {"preset"}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"Unknown headline setting: {', '.join(sorted(unknown))}")

    style = replace(HeadlineStyle(), preset=preset, **values)
    for name, (lo, hi) in HEADLINE_LIMITS.items():
        value = getattr(style, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a number")
        style = replace(style, **{name: int(min(hi, max(lo, value)))})
    if style.seconds not in (0,) and style.seconds < 2:
        style = replace(style, seconds=2)                 # shorter than 2 s is unreadable
    for name in ("text_color", "accent_color"):
        if not isinstance(getattr(style, name), str) or not HEX.fullmatch(getattr(style, name)):
            raise ValueError(f"{name} must look like #RRGGBB")
    for name, allowed_values in (("weight", tuple(WEIGHTS)), ("box", HEADLINE_BOXES)):
        if getattr(style, name) not in allowed_values:
            raise ValueError(f"{name} must be one of: {', '.join(allowed_values)}")
    if not isinstance(style.uppercase, bool) or not isinstance(style.shadow, bool):
        raise ValueError("uppercase and shadow must be true or false")
    return style


def clean_headline(text) -> str:
    """The headline text the user typed, tidied and checked. Raises ValueError if unusable."""
    if not isinstance(text, str):
        raise ValueError("The headline must be text.")
    text = re.sub(r"\s+", " ", "".join(c for c in text if c.isprintable() or c.isspace())).strip()
    if not text:
        raise ValueError("Please type a headline.")
    if len(text) > HEADLINE_MAX_CHARS:
        raise ValueError(f"Keep the headline under {HEADLINE_MAX_CHARS} characters.")
    return text
