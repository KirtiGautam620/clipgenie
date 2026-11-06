"""Understand a request: which tool, with which arguments.

Fixed rules first (fast, testable, no model needed): links, numbers, style names and the words people
use for each tool. The local model is asked only when the rules find nothing, and only to choose
one tool name from a fixed list; Python checks its answer. If nothing fits, the assistant asks.
"""
import re

from app import pipeline, styles
from app.assistant import tools
from app.llm import LLMError, ask_json, unload

URL = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)[\w\-?=&%.]+", re.I)
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10}
# "5 Shorts", "five punchy shorts", "3 short vertical clips": a number, up to two words, then the thing
COUNT = re.compile(r"\b(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")\s+(?:[a-z\-]+\s+){0,2}?(?:short|clip|reel|video|highlight)s?\b", re.I)

# words that point at a tool (checked in this order, so "ideas for shorts" is ideas)
RULES = [
    ("get_more_views", r"\b(more views|get views|grow (my )?(channel|views)|growth)\b"),
    ("channel_audit", r"\b(audit|review my channel|channel (review|check))\b"),
    ("create_thumbnail", r"\bthumbnails?\b"),
    ("write_copy", r"\b(titles?|descriptions?|hashtags?|captions? for (posting|youtube|instagram)|caption text)\b"),
    ("find_broll", r"\bb[- ]?roll\b"),
    ("ai_voiceover", r"\b(voice ?over|narrat\w*|text to speech|tts)\b"),
    ("compose_video", r"\b(compose|slideshow|from (my )?photos|photos? (in)?to (a )?video)\b"),
    ("video_ideas", r"\b(ideas?|what should i (make|film|post)|next video|topics?|content plan)\b"),
    ("make_clips", r"\b(shorts?|clips?|reels?|highlights?|cut (it|this|my)|make (videos|vertical)|edit (it|this|my))\b"),
]
LATEST = re.compile(r"\b(my )?(last|latest|previous|recent) (video|upload|project|one)\b", re.I)
MANUAL = re.compile(r"\b(let me (edit|adjust|change)|manual|i('ll| will) (edit|adjust)|ai ?\+ ?manual)\b", re.I)

ROUTER_SYSTEM = """You sort a creator's request into ONE of these tools:
{names}
or "none" if none of them fits. Answer ONLY with JSON: {{"tool": "<name or none>"}}"""


def _count(text: str) -> int | None:
    m = COUNT.search(text)
    if not m:
        return None
    raw = m.group(1).lower()
    n = NUMBER_WORDS.get(raw) or int(raw)
    return n if 1 <= n <= 10 else None


def _style(text: str) -> str | None:
    lower = text.lower()
    for style in styles.all_styles():
        if style["id"] != styles.DEFAULT_STYLE and style["name"].lower() in lower:
            return style["id"]
    for word, style_id in (("punchy", "punchy"), ("calm", "calm"), ("podcast style", "podcast")):
        if word in lower:
            return style_id
    return None


def extract_args(text: str) -> dict:
    """Everything the rules can read from the words themselves."""
    args = {}
    url = URL.search(text)
    if url:
        args["url"] = url.group(0)
    count = _count(text)
    if count:
        args["count"] = count
    style_id = _style(text)
    if style_id:
        args["edit_mode"], args["style_id"] = "custom", style_id
    elif MANUAL.search(text):
        args["edit_mode"] = "assist"
    if LATEST.search(text):
        args["project"] = "latest"
    return args


def route(text: str, has_attachment: bool = False, use_model: bool = True) -> dict:
    """-> {"tool": name | None, "args": {...}, "how": "rules" | "model" | "none"}"""
    text = (text or "").strip()
    args = extract_args(text)
    for name, pattern in RULES:
        if name == "write_copy" and ("url" in args or "count" in args or has_attachment):
            continue                    # "5 Shorts with titles" is about making clips first
        if re.search(pattern, text, re.I):
            return {"tool": name, "args": args, "how": "rules"}
    if "url" in args or has_attachment or "count" in args:
        return {"tool": "make_clips", "args": args, "how": "rules"}   # a video with no other wish: make clips
    # the model needs memory: it is only asked when no video is being made (else: rules only)
    if use_model and len(text) >= 8 and pipeline.heavy_job_lock.acquire(blocking=False):
        names = ", ".join(t["name"] for t in tools.listing())
        try:
            answer = ask_json(ROUTER_SYSTEM.format(names=names), text, timeout=60)
            name = answer.get("tool") if isinstance(answer, dict) else None
            if name in tools.TOOLS:
                return {"tool": name, "args": args, "how": "model"}
        except LLMError:
            pass
        finally:
            unload()
            pipeline.heavy_job_lock.release()
    return {"tool": None, "args": args, "how": "none"}
