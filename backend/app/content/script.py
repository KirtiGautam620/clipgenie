"""A script outline for a video idea: a hook, the main points, a closing line. A DRAFT for the creator
to rewrite in their own voice, written from the idea and what they said in their own video."""
from app.llm import ask_json, unload

OUTLINE_SYSTEM = """You help a video creator outline their NEXT video. You get one idea (title, angle,
and a line they said before) and an excerpt of what they talked about in an earlier video.
Write a short outline in English:
- "hook": the first sentence to say on camera, max 160 characters
- "points": 3 to 6 main points, each one sentence, max 160 characters
- "closing": a last line that wraps it up, max 160 characters
Use only what fits the idea and the creator's own words. Never invent facts, statistics or quotes.
Answer ONLY with JSON: {"hook": "...", "points": ["...", "..."], "closing": "..."}"""


def _clean(text, limit: int = 160) -> str:
    """Tidy spaces, and drop stray dots or dashes the small model sometimes starts a line with."""
    return " ".join(str(text or "").split()).lstrip(".…-–—•* ")[:limit].strip()


def check_outline(raw) -> dict:
    """The model's outline, checked. Raises ValueError if it is not usable."""
    if not isinstance(raw, dict):
        raise ValueError("The AI gave no usable outline.")
    hook, closing = _clean(raw.get("hook")), _clean(raw.get("closing"))
    points = [p for p in (_clean(x) for x in (raw.get("points") or [])[:6]) if len(p) >= 10]
    if len(hook) < 10 or len(points) < 3:
        raise ValueError("The AI's outline was too thin to be useful. Try again.")
    return {"hook": hook, "points": points, "closing": closing}


def draft(idea: dict, excerpt: str) -> dict:
    """Raises LLMError if the model cannot be reached, ValueError if its outline is not usable."""
    user = (f"IDEA\ntitle: {idea['title']}\nangle: {idea.get('angle', '')}\nthey said: {idea.get('based_on', '')}\n\n"
            f"FROM THEIR EARLIER VIDEO\n{excerpt[:3000]}")
    try:
        return check_outline(ask_json(OUTLINE_SYSTEM, user, timeout=180))
    finally:
        unload()
