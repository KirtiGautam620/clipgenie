"""How long things last: scene lengths, where each scene starts, transition overlaps, and caption
timing estimated from the narration text.

If narration audio exists, a scene lasts at least as long as that audio plus a short pause, so the
voice is never cut off. Caption timings made here are ESTIMATES (spread over the speaking time by
word length): they carry `estimated: True` and must not be presented as aligned to the audio.
"""
from app.photostory.manifest import Manifest, Scene

FPS = 25
TAIL_PAD = 0.4       # a breath of silence after the narration before the next scene
LEAD_IN = 0.15       # narration starts a moment after the scene appears
PAUSE_AFTER = ".,?!;:।"
PAUSE_WEIGHT = 3     # a full stop or comma is worth this many extra letters of time


def frames(seconds: float) -> int:
    return max(1, round(seconds * FPS))


def scene_seconds(scene: Scene) -> float:
    """How long the scene is on screen (not counting the part shared with a transition)."""
    if scene.narration_seconds:
        return max(scene.duration, scene.narration_seconds + TAIL_PAD)
    return scene.duration


def durations(scenes: list[Scene]) -> list[float]:
    return [scene_seconds(s) for s in scenes]


def overlaps(scenes: list[Scene]) -> list[float]:
    """Seconds each scene shares with the one before it. The first is 0, and so is every 'cut'.
    An overlap is never more than half of either neighbour, so a short scene cannot disappear."""
    d = durations(scenes)
    out = [0.0]
    for i in range(1, len(scenes)):
        s = scenes[i]
        out.append(0.0 if s.transition == "cut" else min(s.transition_seconds, 0.5 * min(d[i - 1], d[i])))
    return out


def starts(scenes: list[Scene]) -> list[float]:
    """When each scene begins on the finished video's timeline."""
    out, t = [], 0.0
    for d in durations(scenes):
        out.append(t)
        t += d
    return out


def render_lengths(scenes: list[Scene]) -> list[float]:
    """How long each scene's clip must be rendered: its own time plus the part that overlaps the
    NEXT scene, so a transition always has picture on both sides."""
    d, o = durations(scenes), overlaps(scenes)
    return [d[i] + (o[i + 1] if i + 1 < len(d) else 0.0) for i in range(len(d))]


def total_seconds(scenes: list[Scene]) -> float:
    return sum(durations(scenes))


def estimate_word_times(text: str, start: float, speaking_seconds: float) -> list[dict]:
    """Caption words for `text`, spread over the speaking time in proportion to word length."""
    tokens = text.split()
    if not tokens:
        return []
    weights = [len(t) + (PAUSE_WEIGHT if t[-1] in PAUSE_AFTER else 0) for t in tokens]
    unit = max(0.1, speaking_seconds) / sum(weights)
    out, t = [], start
    for token, weight in zip(tokens, weights):
        out.append({"text": token, "start": round(t, 3), "end": round(t + len(token) * unit, 3),
                    "estimated": True})
        t += weight * unit
    return out


def caption_words(m: Manifest) -> list[dict]:
    """Caption words for the whole video, on the finished timeline (same shape captions.py draws)."""
    words: list[dict] = []
    for scene, begin in zip(m.scenes, starts(m.scenes)):
        if not scene.narration_text:
            continue
        speaking = scene.narration_seconds or max(0.5, scene_seconds(scene) - TAIL_PAD - LEAD_IN)
        words += estimate_word_times(scene.narration_text, begin + LEAD_IN, speaking)
    return words
