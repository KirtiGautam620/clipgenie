"""The shot library and the styles: plain data that the planner picks from.

Each shot says what to ask an external AI for (camera, detail) and how to reframe the photo for the
preview (zoom, focus, motion). Every text here is written by hand, not generated.
"""
import re
from dataclasses import dataclass

MOTIONS = ("hold", "push_in", "pull_out", "pan_left", "pan_right", "pan_up", "pan_down")
TRANSITIONS = ("cut", "fade", "slide_left", "slide_right", "wipe_left")      # the Photo Story names
STYLES = ("none", "cinematic", "ugc", "luxury", "minimal")
ASPECTS = ("9:16", "16:9")


@dataclass(frozen=True)
class Shot:
    id: str
    label: str
    camera: str             # the camera instruction to give an external AI
    detail: str             # what the shot should show
    zoom: float             # preview framing: 1.0 = widest view of the photo, higher = closer
    focus: tuple[float, float]
    motion: str
    intensity: float
    duration: float         # seconds, before the style adjusts it
    words: str              # a regular expression: words in a prompt that ask for this shot


SHOTS: dict[str, Shot] = {s.id: s for s in [
    Shot("establishing", "Establishing wide",
         "wide establishing shot, the camera slowly pushing in",
         "the whole product in its setting, centred, with room around it",
         1.0, (0.5, 0.5), "push_in", 0.35, 3.5,
         r"establishing|wide[- ]?(?:angle )?shots?|wide angle|full shot|master shot|overview shot"),
    Shot("hero", "Hero angle",
         "hero three-quarter angle, steady camera with a slight drift",
         "the product front and centre, clean and well lit",
         1.15, (0.5, 0.5), "push_in", 0.2, 3.0,
         r"hero (?:shot|angle|view)|three[- ]quarter|3/4 view|front view"),
    Shot("low_angle", "Low angle",
         "low-angle shot looking up at the product, the camera rising slowly",
         "the product looks tall and powerful against the background",
         1.3, (0.5, 0.62), "pan_up", 0.4, 3.0,
         r"low[- ]?angle|from below|looking up"),
    Shot("top_down", "Top-down",
         "top-down overhead shot, the camera drifting slowly sideways",
         "the product seen from directly above on a clean surface",
         1.1, (0.5, 0.4), "pan_right", 0.3, 3.0,
         r"top[- ]?down|overhead|from above|flat[- ]?lay|bird'?s[- ]eye"),
    Shot("close_up", "Close-up",
         "close-up shot with shallow depth of field, a slow push-in",
         "an important feature of the product filling the frame",
         1.8, (0.5, 0.45), "push_in", 0.4, 3.0,
         r"close[- ]?ups?|tight shot|detail shot"),
    Shot("macro", "Macro texture",
         "extreme close-up macro shot with a tiny sliding movement",
         "the material, texture and finish of the product up close",
         2.6, (0.45, 0.5), "pan_right", 0.3, 2.5,
         r"macro|textures?|extreme close"),
    Shot("pull_back", "Pull-back reveal",
         "the camera pulls back to reveal the product",
         "starts tight on a detail and widens to show the whole product",
         1.2, (0.5, 0.5), "pull_out", 0.9, 3.5,
         r"pull(?:s|ing)?[- ]?back|pull out|reveal|zoom out|widen"),
    Shot("orbit", "Orbit",
         "smooth orbiting shot, the camera circling slowly around the product",
         "the product seen from several sides as the camera moves around it",
         1.25, (0.5, 0.5), "pan_left", 0.5, 3.5,
         r"orbit|360|turntable|circl\w* around|rotat\w* around"),
    Shot("in_hand", "In hand",
         "handheld shot of a hand holding the product, with natural slight movement",
         "someone holds the product up to the camera the way they would in a real review",
         1.35, (0.5, 0.55), "hold", 0.0, 2.5,
         r"in[- ]?hand|holding|hand[- ]?held|\bugc\b"),
    Shot("unboxing", "Unboxing reveal",
         "over-the-shoulder shot as the product is unboxed, with a quick reveal",
         "the product appearing from its packaging",
         1.2, (0.5, 0.5), "push_in", 0.3, 2.5,
         r"unbox\w*|packaging|opening the box"),
    Shot("lifestyle", "In use",
         "lifestyle shot of the product in everyday use, natural light",
         "the product in a real setting, with hands or surroundings that show how it is used",
         1.1, (0.5, 0.5), "pan_left", 0.25, 3.5,
         r"lifestyle|in use|everyday|real[- ]life|in context"),
    Shot("slow_push", "Slow push-in",
         "slow cinematic push-in towards the product",
         "gradually drawing the viewer closer to the product",
         1.05, (0.5, 0.5), "push_in", 0.6, 4.0,
         r"push[- ]?in|dolly|zoom in|slow zoom"),
    Shot("side_profile", "Side profile",
         "side profile shot, the camera tracking sideways",
         "the product in profile, showing its shape and silhouette",
         1.2, (0.4, 0.5), "pan_right", 0.4, 3.0,
         r"side profile|profile shot|side view|silhouette|tracking shot"),
    Shot("closing_hero", "Closing hero",
         "final hero shot, steady camera with a gentle slow-down",
         "the product centred for a confident closing frame",
         1.1, (0.5, 0.5), "hold", 0.0, 3.0,
         r"closing|final shot|ending shot|end shot|outro|end card"),
]}

SHOT_PATTERNS = {sid: re.compile(r"\b(?:%s)" % s.words, re.IGNORECASE) for sid, s in SHOTS.items()}
OPENING, CLOSING = "establishing", "closing_hero"


@dataclass(frozen=True)
class Style:
    id: str
    label: str
    phrase: str                  # added to every prompt
    transition: str
    transition_seconds: float
    duration_factor: float
    order: tuple[str, ...]       # shots used, in this order, when the prompt does not ask for others
    words: str                   # words in a prompt that ask for this style


STYLE_INFO: dict[str, Style] = {s.id: s for s in [
    Style("none", "No style", "", "fade", 0.6, 1.0,
          ("establishing", "hero", "low_angle", "close_up", "macro", "pull_back", "top_down", "closing_hero"), ""),
    Style("cinematic", "Cinematic",
          "cinematic look, shallow depth of field, soft directional lighting, rich film colour grade, "
          "smooth deliberate camera movement", "fade", 0.8, 1.15,
          ("establishing", "slow_push", "low_angle", "close_up", "macro", "pull_back", "orbit", "closing_hero"),
          r"cinemat\w*"),
    Style("ugc", "UGC",
          "authentic user-generated style, handheld smartphone look, natural daylight, casual and relatable",
          "slide_left", 0.3, 0.8,
          ("in_hand", "close_up", "hero", "lifestyle", "unboxing", "macro", "closing_hero", "side_profile"),
          r"\bugc\b|user[- ]generated|selfie"),
    Style("luxury", "Luxury",
          "luxury commercial look, dark moody lighting, elegant reflections, slow graceful movement",
          "fade", 1.0, 1.2,
          ("slow_push", "low_angle", "macro", "orbit", "close_up", "closing_hero", "hero", "top_down"),
          r"luxur\w*|\bpremium\b|high[- ]end|elegant"),
    Style("minimal", "Minimal",
          "clean minimal look, soft even light, simple uncluttered background",
          "fade", 0.6, 1.0,
          ("hero", "top_down", "close_up", "side_profile", "macro", "closing_hero"),
          r"minimal\w*"),
]}
STYLE_PATTERNS = {sid: re.compile(s.words, re.IGNORECASE) for sid, s in STYLE_INFO.items() if s.words}

TRANSITION_WORDS = [
    ("fade", re.compile(r"smooth|seamless|cross[- ]?fade|dissolve", re.IGNORECASE)),
    ("slide_left", re.compile(r"\bfast\b|quick|snappy|whip|energetic", re.IGNORECASE)),
    ("cut", re.compile(r"hard cuts?|jump cuts?|straight cuts?", re.IGNORECASE)),
]
SLOW_MOTION = re.compile(r"slow[- ]?mo(?:tion)?", re.IGNORECASE)
