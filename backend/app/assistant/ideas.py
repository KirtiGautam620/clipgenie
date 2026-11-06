"""Video ideas, grounded in the creator's own words.

The local model reads what was said in one of the user's videos and suggests follow-up videos. Each
idea must point at something actually said ("based_on", copied from the transcript); ideas whose
quote cannot be found in the transcript are dropped. There is no trend or search data here yet, and
the result says so.
"""
import re

from app.llm import ask_json, unload

MAX_IDEAS = 5
EXCERPT_CHARS = 5000

IDEAS_SYSTEM = """You help a video creator plan their NEXT videos, using what they talked about in
one of their own videos (the transcript below; it may be English, Hindi or Hinglish).
Suggest up to {count} new video ideas that build on topics, stories or questions from it.
For each idea give:
- "title": a clear, honest video title (max 90 characters, in English)
- "angle": one sentence on what the video would cover
- "why": one sentence on why their audience would care, based on the transcript
- "based_on": a SHORT phrase (3 to 12 words) copied EXACTLY from the transcript that inspired it
Never invent facts, numbers or trends. Answer ONLY with JSON: {{"ideas": [{{"title", "angle", "why", "based_on"}}]}}"""


def excerpt(segments: list[dict], limit: int = EXCERPT_CHARS) -> str:
    """Sentences spread across the whole video (not just its start), up to `limit` characters."""
    lines = [s["text"].strip() for s in segments if s.get("text", "").strip()]
    if sum(len(l) + 1 for l in lines) <= limit:
        return "\n".join(lines)
    step = max(1, len(lines) * 120 // limit)          # keep about one line in `step`
    picked = lines[::step]
    out, size = [], 0
    for line in picked:
        if size + len(line) > limit:
            break
        out.append(line)
        size += len(line) + 1
    return "\n".join(out)


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def grounded(phrase: str, transcript_text: str) -> bool:
    """Is `phrase` really from the transcript? At least 80% of its words must appear in it."""
    words = _words(phrase)
    if len(words) < 2:
        return False
    hay = set(_words(transcript_text))
    return sum(w in hay for w in words) / len(words) >= 0.8


def _clean(text, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


def suggest(segments: list[dict], count: int = MAX_IDEAS) -> list[dict]:
    """Up to `count` checked ideas. Raises LLMError if the model cannot be reached."""
    transcript_text = excerpt(segments)
    if len(transcript_text) < 80:
        return []
    try:
        answer = ask_json(IDEAS_SYSTEM.format(count=count), transcript_text, timeout=240)
    finally:
        unload()
    ideas = []
    for item in (answer.get("ideas") or [])[:count] if isinstance(answer, dict) else []:
        if not isinstance(item, dict):
            continue
        idea = {"title": _clean(item.get("title"), 90), "angle": _clean(item.get("angle"), 240),
                "why": _clean(item.get("why"), 240), "based_on": _clean(item.get("based_on"), 160)}
        full_text = " ".join(s.get("text", "") for s in segments)
        if len(idea["title"]) >= 8 and idea["angle"] and grounded(idea["based_on"], full_text):
            ideas.append(idea)
    return ideas
