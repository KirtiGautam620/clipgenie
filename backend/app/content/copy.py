"""Title, description and hashtags for one clip, written from that clip's own words.

The local model writes a DRAFT. Python checks it: lengths, no links or @mentions, and every hashtag
must name something actually said in the clip (#shorts is the one platform tag always allowed). A
clip whose speech cannot be trusted gets no AI draft at all; the user can still write their own.
"""
import json
import re

from app import captionstyles, jobs, pipeline, textmode
from app.llm import ask_json, unload

TITLE_MAX, DESCRIPTION_MAX, HASHTAGS_MAX = 100, 500, 8
PLATFORM_TAGS = {"shorts"}
LINKISH = re.compile(r"https?://|www\.|@\w", re.I)

COPY_SYSTEM = """You write the publishing text for ONE short vertical video, from what is said in it
(the transcript below; it may be English, Hindi or Hinglish).
Write:
- "title": an honest, specific title, max 90 characters, in the language of the transcript
- "description": 1 to 3 short sentences saying what the viewer will hear, max 400 characters
- "hashtags": 3 to 6 hashtags, each a topic that is actually mentioned in the transcript
Never invent facts, numbers or promises. No links, no @mentions, no emojis.
Answer ONLY with JSON: {"title": "...", "description": "...", "hashtags": ["#...", "#..."]}"""


class Untrusted(ValueError):
    pass


def _clean(text, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit].strip()


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def clean_hashtag(raw) -> str | None:
    """'#Home Cooking' -> '#homecooking'. None if it is not a usable tag."""
    tag = re.sub(r"[^\w]", "", str(raw or "").lstrip("#").lower())
    return f"#{tag}" if 2 <= len(tag) <= 30 else None


def _said(piece: str, words: set[str]) -> bool:
    """A piece of a hashtag matches a said word, allowing a short ending ('cook' ~ 'cooking')."""
    if piece in words:
        return True
    if len(piece) < 4:
        return False
    return any(len(w) >= 4 and (w.startswith(piece) or piece.startswith(w)) and abs(len(w) - len(piece)) <= 3
               for w in words)


def grounded_tag(tag: str, words: set[str]) -> bool:
    """Is this hashtag about something said? It must be made only of words said in the clip:
    '#cooking' (said 'cooking' or 'cook'), '#homecooking' (said 'home' and 'cooking')."""
    t = tag.lstrip("#")
    if t in PLATFORM_TAGS:
        return True
    ok = [True] + [False] * len(t)                 # ok[i]: t[:i] splits into said words
    for i in range(1, len(t) + 1):
        ok[i] = any(ok[j] and _said(t[j:i], words) for j in range(max(0, i - 25), i))
    return ok[-1]


def check_draft(raw: dict, transcript_text: str) -> dict:
    """The model's answer, checked and tidied. Raises ValueError if nothing usable is left."""
    if not isinstance(raw, dict):
        raise ValueError("The AI gave no usable text.")
    title = _clean(raw.get("title"), TITLE_MAX)
    description = _clean(raw.get("description"), DESCRIPTION_MAX)
    if len(title) < 8 or LINKISH.search(title):
        raise ValueError("The AI's title was not usable.")
    if LINKISH.search(description):
        description = ""
    words = _tokens(transcript_text)
    tags = []
    for raw_tag in (raw.get("hashtags") or [])[:12]:
        tag = clean_hashtag(raw_tag)
        if tag and tag not in tags and grounded_tag(tag, words):
            tags.append(tag)
    if "#shorts" not in tags:
        tags.append("#shorts")
    return {"title": title, "description": description, "hashtags": tags[:HASHTAGS_MAX]}


def check_user_copy(body: dict) -> dict:
    """What the user typed: their own words, only tidied and limited (no grounding needed)."""
    title = _clean(body.get("title"), TITLE_MAX)
    description = " ".join(str(body.get("description") or "").split(" "))[:DESCRIPTION_MAX].strip()
    tags = []
    for raw_tag in (body.get("hashtags") or [])[:HASHTAGS_MAX]:
        tag = clean_hashtag(raw_tag)
        if tag and tag not in tags:
            tags.append(tag)
    if not title:
        raise ValueError("Please write a title.")
    return {"title": title, "description": description, "hashtags": tags}


def clip_text(job_id: str, clip: dict) -> str:
    """The clip's own sentences from the saved transcript (the same text its hook is written from)."""
    folder = jobs.job_dir(job_id)
    segments = json.loads((folder / "transcript.json").read_text())["segments"]
    cut = clip.get("cut") or {"cut_start": clip["start"], "cut_end": clip["end"]}
    lo, hi = cut["cut_start"] - 0.5, cut["cut_end"] + 0.5
    return " ".join(s["text"].strip() for s in segments if s["start"] >= lo and s["end"] <= hi)


def _save(job_id: str, clip_id: int, copy: dict) -> dict:
    folder, clips_file, data, clip, _ = pipeline._load_clip(job_id, clip_id)
    clip["copy"] = copy
    jobs.write_atomic(clips_file, json.dumps(data, ensure_ascii=False))
    return clip


def can_draft(clip: dict) -> bool:
    """AI text only for a clip whose speech was trusted (never from withheld or doubtful words)."""
    return not textmode.is_untrusted(clip) and textmode.text_state(clip).get("mode") != "pending"


def draft(job_id: str, clip_id: int, wait: bool = False) -> dict:
    """Ask the model for a draft and save it on the clip (not approved, not used until the user says so).
    wait=False (a button press): Busy if a video is being made. wait=True (an assistant run in the
    background): wait for it. Raises Untrusted, ValueError, LLMError or pipeline.Busy."""
    _, _, _, clip, _ = pipeline._load_clip(job_id, clip_id)
    if not can_draft(clip):
        raise Untrusted("The speech in this clip couldn't be trusted, so ClipGenie won't write about it. "
                        "Write your own title instead.")
    text = clip_text(job_id, clip)
    if len(text) < 20:
        raise ValueError("There is too little speech in this clip to write about.")
    if not pipeline.heavy_job_lock.acquire(blocking=wait):
        raise pipeline.Busy("ClipGenie is busy making a video. Try again in a minute.")
    try:
        try:
            answer = ask_json(COPY_SYSTEM, text[:3000], timeout=180)
        finally:
            unload()
        copy = {**check_draft(answer, text), "source": "ai", "approved": False}
        return _save(job_id, clip_id, copy)
    finally:
        pipeline.heavy_job_lock.release()


def save_user(job_id: str, clip_id: int, body: dict) -> dict:
    """The user's own (or edited) text: saved as approved. The video itself is not changed."""
    copy = {**check_user_copy(body), "source": "user", "approved": True}
    if not pipeline.heavy_job_lock.acquire(blocking=False):
        raise pipeline.Busy("ClipGenie is busy making a video. Try again in a minute.")
    try:
        return _save(job_id, clip_id, copy)
    finally:
        pipeline.heavy_job_lock.release()


def headline_text(clip: dict) -> str:
    """Text for a thumbnail: the approved title, else an approved hook, else the clip's title if it
    is a real one (never AI text from an untrusted clip)."""
    copy = clip.get("copy") or {}
    hook = (clip.get("text") or {}).get("hook") or {}
    if copy.get("approved") and copy.get("title"):
        return copy["title"]
    if hook.get("approved") and hook.get("text"):
        return hook["text"]
    title = textmode.public(clip).get("title") or ""
    if title and not re.fullmatch(r"Clip \d+", title):
        try:
            return captionstyles.clean_headline(title)
        except ValueError:
            return ""
    return ""
