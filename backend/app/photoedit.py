"""Typed requests that change one photo of a photo video, e.g.

    "change the text on photo 2 to Good morning"   "fade into photo 3"
    "slide in from the top on photo 2, fast"        "text comes in from the left on photo 4, slow"
    "white frame on photo 1"   "remove the text from photo 5"

Rules come first (fast, testable, no model). The local model is asked only when the rules find nothing,
and only to fill in the same fields; Python checks its answer and never runs anything else.
"""
import re

from app import photovideo
from app.llm import LLMError, ask_json

PHOTO = re.compile(r"\bphoto\s*(\d{1,2})\b", re.I)
QUOTED = re.compile(r"[\"“‘']([^\"”’']{1,200})[\"”’']")
TEXT_WORD = re.compile(r"\b(text|caption|line|words?)\b", re.I)
REMOVE = re.compile(r"\b(remove|delete|clear|no|without)\b", re.I)
MOVE_WORD = re.compile(r"\b(slide|slides|come|comes|coming|move|moves|enter|enters|animate|from|in)\b", re.I)
DIRECTION = re.compile(r"\b(left|right|top|bottom)\b", re.I)
SPEED = re.compile(r"\b(slow|medium|fast)\b", re.I)
KIND = re.compile(r"\b(cut|fade|slide)\b", re.I)
FRAME = re.compile(r"\b(white|black|none|no)\s+(frame|border)\b|\b(frame|border)\s+(white|black|none|no)\b", re.I)
REMOVE_FRAME = re.compile(r"\b(remove|no|without|clear)\b.*\b(frame|border)\b", re.I)

HELP = ("Try: \"change the text on photo 2 to Good morning\", \"fade into photo 3\", "
        "\"slide in from the top on photo 2, fast\", \"text comes in from the left on photo 4\", "
        "\"white frame on photo 1\", \"remove the text from photo 5\".")

SYSTEM = """You change one photo in a short photo video. Answer ONLY with JSON:
{"action": "text" | "transition" | "text_motion" | "frame" | "none", "photo": <number>,
 "value": "<see below>", "direction": "left|right|top|bottom|none", "speed": "slow|medium|fast"}
- "text": change the words on the photo; value is the new text ("" removes it).
- "transition": how the photo comes in; value is cut, fade or slide.
- "text_motion": which side the TEXT comes in from; value is none.
- "frame": a border; value is none, white or black.
Use "none" for the action if the request is about none of these."""

KINDS = {"cut": "cut", "fade": "fade", "slide": "slide"}


def _photo_number(message: str) -> int | None:
    m = PHOTO.search(message)
    return int(m.group(1)) if m else None


def _speed(message: str) -> str | None:
    m = SPEED.search(message)
    return m.group(1).lower() if m else None


def _rule(message: str) -> dict | None:
    """Understand the request from fixed words. Returns the change, or None if the rules find nothing."""
    number = _photo_number(message)
    direction = DIRECTION.search(message)
    speed = _speed(message)
    if TEXT_WORD.search(message) and number:
        if direction and MOVE_WORD.search(message) and not QUOTED.search(message):
            change = {"action": "text_motion", "photo": number, "value": direction.group(1).lower()}
            if speed:
                change["speed"] = speed
            return change
        if REMOVE.search(message) and not QUOTED.search(message):
            return {"action": "text", "photo": number, "text": ""}
        quoted = QUOTED.search(message)
        if quoted:
            return {"action": "text", "photo": number, "text": quoted.group(1).strip()}
        after = re.search(r"(?:\bto\b|\bas\b|:|=)\s*(.+?)\s*$", message, re.I)
        if after and not PHOTO.match(after.group(1)):
            return {"action": "text", "photo": number, "text": after.group(1).strip(" .\"'“”‘’")}
        return None
    if number and REMOVE_FRAME.search(message):
        return {"action": "frame", "photo": number, "value": "none"}
    if number and FRAME.search(message):
        m = FRAME.search(message)
        word = (m.group(1) or m.group(4)).lower()
        return {"action": "frame", "photo": number, "value": "none" if word == "no" else word}
    kind = KIND.search(message)
    if number and kind:
        word = KINDS[kind.group(1).lower()]
        change = {"action": "transition", "photo": number, "value": word}
        if word == "slide":
            change["direction"] = direction.group(1).lower() if direction else "right"
        if speed:
            change["speed"] = speed
        return change
    return None


def _from_model(message: str) -> dict | None:
    from app.pipeline import heavy_job_lock       # the model is only asked when nothing else is running
    if heavy_job_lock.locked():
        raise LLMError("busy")
    answer = ask_json(SYSTEM, message, timeout=60)
    action = str(answer.get("action", "none"))
    number = answer.get("photo")
    if action == "none" or not isinstance(number, int):
        return None
    value = str(answer.get("value", "")).strip()
    direction = str(answer.get("direction", "none")).lower()
    speed = str(answer.get("speed", "medium")).lower()
    if action == "text":
        return {"action": "text", "photo": number, "text": value[:200]}
    if action == "transition":
        change = {"action": "transition", "photo": number, "value": value.lower(), "speed": speed}
        if change["value"] == "slide":
            change["direction"] = direction if direction in ("left", "right", "top", "bottom") else "right"
        return change
    if action == "text_motion":
        return {"action": "text_motion", "photo": number, "value": direction, "speed": speed}
    if action == "frame":
        return {"action": "frame", "photo": number, "value": value.lower()}
    return None


def understand(message: str) -> dict | None:
    """The change the user asked for, or None when nothing could be understood."""
    rule = _rule(message)
    if rule:
        return rule
    try:
        return _from_model(message)
    except LLMError:
        return None


def _describe(change: dict) -> str:
    speed = f", {change['speed']}" if change.get("speed") else ""
    if change["action"] == "transition":
        if change["value"] == "slide":
            return f"slides in from the {change['direction']}{speed}"
        return f"comes in with a {change['value']}{speed}"
    return f"has its text coming in from the {change['value']}{speed}"


def apply(project_id: str, message: str) -> dict:
    """Understand a typed request and make the change. Returns what happened, for the page to show."""
    if not message.strip():
        return {"changed": False, "reply": HELP}
    change = understand(message)
    if change is None:
        return {"changed": False, "reply": "I could not tell which photo or change you meant. " + HELP}
    index = change["photo"]
    try:
        if change["action"] == "text":
            photovideo.change_photo(project_id, index, text=change["text"])
            reply = (f"Photo {index} now shows the text \"{change['text']}\"."
                     if change["text"] else f"Photo {index} has no text now.")
        elif change["action"] == "transition":
            value = change["value"]
            if value == "slide":
                value = f"slide_{change['direction']}"
            photovideo.change_photo(project_id, index, transition=value,
                                    transition_speed=change.get("speed"))
            reply = f"Photo {index} {_describe(change)}."
        elif change["action"] == "text_motion":
            photovideo.change_photo(project_id, index, text_motion=change["value"],
                                    text_speed=change.get("speed"))
            reply = f"Photo {index}'s text {_describe(change)}."
        elif change["action"] == "frame":
            photovideo.change_photo(project_id, index, frame=change["value"])
            reply = (f"Photo {index} has no frame now." if change["value"] == "none"
                     else f"Photo {index} has a {change['value']} frame now.")
        else:
            return {"changed": False, "reply": HELP}
    except ValueError as e:
        return {"changed": False, "reply": str(e)}
    return {"changed": True, "reply": reply + " The video is being made again."}
