"""Build a shot plan from a prompt: rules and templates, not AI.

The planner looks for words in the prompt (a style, shot types, a number of scenes, a length, how the
scenes should join), then fills any remaining scenes from the style's default shot list. It always
says what it found and what it dropped, so nobody mistakes it for something that understood the photo.
The same inputs always give the same plan.
"""
import re

from app.storyboard import prompts
from app.storyboard.shots import (ASPECTS, CLOSING, OPENING, SHOT_PATTERNS, SHOTS, SLOW_MOTION, STYLE_INFO,
                                  STYLE_PATTERNS, STYLES, TRANSITION_WORDS)

MIN_SCENES, MAX_SCENES, DEFAULT_SCENES = 2, 8, 6
MIN_SECONDS, MAX_SECONDS = 1.5, 8.0
COUNT = re.compile(r"\b(\d{1,2})\s*(?:different\s+)?(?:scenes?|shots?|angles?|clips?)\b", re.IGNORECASE)
LENGTH = re.compile(r"\b(\d{1,3})\s*(?:s|secs?|seconds?)\b", re.IGNORECASE)


def read_prompt(text: str) -> dict:
    """What the prompt asks for, as found by keywords."""
    styles = sorted(((m.start(), sid) for sid, p in STYLE_PATTERNS.items() if (m := p.search(text))))
    shots = sorted(((m.start(), sid) for sid, p in SHOT_PATTERNS.items() if (m := p.search(text))))
    count = COUNT.search(text)
    length = LENGTH.search(text)
    transition = next((tid for tid, p in TRANSITION_WORDS if p.search(text)), None)
    return {"styles": [sid for _, sid in styles], "shots": [sid for _, sid in shots],
            "count": int(count.group(1)) if count else None,
            "seconds": int(length.group(1)) if length else None,
            "transition": transition, "slow_motion": bool(SLOW_MOTION.search(text))}


def plan(prompt: str, *, product: str = "", style: str | None = None, count: int | None = None,
         aspect: str = "9:16") -> dict:
    """{"scenes": [...], "understood": {...}, "notes": [...]}. `style` and `count` override the prompt."""
    if aspect not in ASPECTS:
        raise ValueError(f"aspect must be one of: {', '.join(ASPECTS)}")
    if style is not None and style not in STYLES:
        raise ValueError(f"style must be one of: {', '.join(STYLES)}")
    found = read_prompt(prompt or "")
    notes: list[str] = []

    # style: the user's choice wins, then the first style word in the prompt
    if style is None or style == "none":
        chosen = found["styles"][0] if found["styles"] and style is None else (style or "none")
        if style is None and len(found["styles"]) > 1:
            notes.append(f"The prompt mentions {' and '.join(found['styles'])}; the plan uses {chosen}. "
                         "Pick a style to change it.")
    else:
        chosen = style
    info = STYLE_INFO[chosen]

    # how many scenes
    wanted = count if count is not None else found["count"]
    n = DEFAULT_SCENES if wanted is None else wanted
    if not MIN_SCENES <= n <= MAX_SCENES:
        notes.append(f"{n} scenes is outside {MIN_SCENES}-{MAX_SCENES}; the plan uses "
                     f"{max(MIN_SCENES, min(MAX_SCENES, n))}.")
        n = max(MIN_SCENES, min(MAX_SCENES, n))

    # which shots: the ones the prompt names (in the order it names them), then the style's defaults
    named = found["shots"]
    if len(named) > n:
        notes.append("Too many shots for " + f"{n} scenes; left out: "
                     + ", ".join(SHOTS[s].label for s in named[n:]) + ".")
        named = named[:n]
    picked = list(named)
    for sid in info.order:
        if len(picked) >= n:
            break
        if sid not in picked:
            picked.append(sid)
    for sid in SHOTS:                      # a short style list still fills every scene
        if len(picked) >= n:
            break
        if sid not in picked:
            picked.append(sid)
    if CLOSING not in picked and n >= 4:                      # a plan of four or more ends on a closing shot
        for k in range(len(picked) - 1, -1, -1):
            if picked[k] not in named:
                picked[k] = CLOSING
                break
    if OPENING in picked and OPENING not in named:           # a default opener goes first
        picked.remove(OPENING)
        picked.insert(0, OPENING)
    if CLOSING in picked and CLOSING not in named:           # a default closer goes last
        picked.remove(CLOSING)
        picked.append(CLOSING)
    if not named:
        notes.append("No shot types were found in the prompt, so the plan uses the default shot list.")

    # how scenes join
    transition = found["transition"] or info.transition
    seconds_each = 0.5 if transition == "cut" else {"fade": info.transition_seconds, "slide_left": 0.3}.get(
        transition, info.transition_seconds)

    # how long each scene lasts
    total = found["seconds"]
    scenes = []
    for k, sid in enumerate(picked, 1):
        shot = SHOTS[sid]
        if total:
            duration = total / n
        else:
            duration = shot.duration * info.duration_factor * (1.3 if found["slow_motion"] else 1.0)
        duration = round(max(MIN_SECONDS, min(MAX_SECONDS, duration)), 1)
        camera = shot.camera + (", in slow motion" if found["slow_motion"] else "")
        scenes.append({
            "id": f"s{k}", "title": shot.label, "shot": sid, "camera": camera, "detail": shot.detail,
            "duration": duration, "zoom": shot.zoom, "focus": list(shot.focus), "motion": shot.motion,
            "intensity": shot.intensity, "transition": transition, "transition_seconds": seconds_each})
    for s in scenes:
        s["prompt"] = prompts.compose_scene(camera=s["camera"], detail=s["detail"], duration=s["duration"],
                                            product=product, style=chosen, aspect=aspect)
    if total:
        notes.append(f"{total} seconds in total, shared between {n} scenes.")
    return {"scenes": scenes, "style": chosen, "notes": notes,
            "understood": {"style": chosen, "shots": [SHOTS[s].label for s in named], "scenes": n,
                           "seconds": total, "transition": transition, "slow_motion": found["slow_motion"]}}
