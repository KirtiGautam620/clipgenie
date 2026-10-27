"""AI highlight detection, in three stages.

1. DRAFT   - the model suggests moments (as sentence numbers) for each part of the video.
2. REVIEW  - the model re-reads each moment with a little context around it and checks
             it has a hook, a payoff and a clean ending. It may move the start/end a
             few sentences, and it scores the result.
3. RANK    - best-scoring moments across the *whole* video win.

The model only suggests sentence numbers. Python checks everything, so a confused
model can never produce a clip that cuts a sentence in half or is the wrong length.
"""
import re

from app.clips import pick_clips
from app.llm import LLMError, ask_json, unload

WINDOW = 120        # sentences per draft request, so long videos fit in memory
REVIEW_MARGIN = 3   # context sentences shown around a moment, and max boundary move
MAX_DRAFT_ROUNDS = 3  # extra rounds look at parts of the video not examined yet
MIN_SCORE = 5      # score (1-10) below which a moment is dropped

# Sentences like these are never a good first or last line of a clip.
FILLER = re.compile(
    r"\b(thank(s| you)|subscribe|like and|see you|next (video|topic|week|one)|moving on|"
    r"let'?s move|that'?s (it|all)|anyway|welcome (back|to)|(hi|hello|hey) (everyone|guys|friends)|"
    r"sponsor|link in|one second|let me (just )?(adjust|check)|"
    r"now,? let'?s?( me)? (read|look|check|talk|get)|(comments|questions) from)\b"
    r"|^\s*(okay|ok|alright|all right|so anyway),?\s"
    r"|धन्यवाद|शुक्रिया|नमस्ते|स्वागत|सब्सक्राइब|अगले (वीडियो|टॉपिक)|चलिए अब|बस इतना ही|आगे बढ़ते",
    re.IGNORECASE,
)

DRAFT_SYSTEM = """You are a video editor who finds the most engaging moments in a transcript
for YouTube Shorts. The transcript may be English, Hindi or a mix (Hinglish).
Each line looks like: [number] (start time in seconds) sentence.

Pick moments that are interesting, surprising, emotional, funny, memorable, or give a
useful tip or explanation. A moment must make sense on its own and end on a complete thought.
Rules for the boundaries:
- Start at the sentence that sets up the idea (the hook), never in the middle of a story.
- Include the payoff. Never end on a setup like "then she said something" without
  the sentence that follows it.
- Do not include greetings, sponsor reads, "moving on", "that's it for this section",
  "thanks for watching" or other filler at the start or end.

Answer ONLY with JSON in this exact shape:
{"clips": [{"first": <sentence number>, "last": <sentence number>,
"title": "<short title>", "reason": "<one sentence on why it is engaging>",
"mood": "<motivational|emotional|funny|educational|spiritual|other>"}]}
Write title and reason in English. Choose at most {count} moments, best first."""

ADJUST_SYSTEM = """You are an editor fixing the START and END of ONE short video clip.
Lines are numbered. Lines marked >> are currently inside the clip; lines marked .. are
the surrounding context.

Check:
1. HOOK: the clip should open with the sentence that sets up the idea and makes sense
   without earlier context. If it starts mid-story, move "first" earlier. If it starts
   with greetings, housekeeping or filler, move "first" later.
2. PAYOFF: the clip should end right after the point, joke or conclusion lands. If it stops
   just before the payoff (for example "then she said something" with the answer on the next
   line), move "last" later. If it runs on past the payoff into small talk, housekeeping or
   the next topic, move "last" earlier.

Answer ONLY with JSON: {"first": <number>, "last": <number>, "problem": "<what you fixed, or 'none'>"}
"first" and "last" must be line numbers shown to you."""

SCORE_SYSTEM = """You rate ONE short video clip (given as numbered lines) as a standalone
YouTube Short. Judge only the clip itself.

Scale:
 1-3: housekeeping, logistics, lists of tools, greetings, small talk, or no clear point.
 4-5: fine but ordinary; a tip or fact without much feeling.
 6-7: interesting, clear and complete; a good story, a useful insight or a strong statement.
 8-10: memorable: emotional, surprising, funny or powerful, with a clear beginning and ending.
Most clips deserve 3-7. Use 8+ only for clearly outstanding ones.

Answer ONLY with JSON: {"score": <1-10>, "why": "<one short sentence>"}"""


def _is_filler(seg: dict) -> bool:
    return bool(FILLER.search(seg["text"]))


def _length(segments: list[dict], first: int, last: int) -> float:
    return segments[last]["end"] - segments[first]["start"]


def _fix_bounds(segments: list[dict], first: int, last: int, lo: int, hi: int,
                min_len: float, max_len: float) -> tuple[int, int] | None:
    """Make [first, last] a clean clip, or return None if that is impossible."""
    first, last = max(lo, first), min(hi - 1, last)
    if first > last:
        return None
    # 1. drop filler sentences at the edges
    while first < last and _is_filler(segments[first]):
        first += 1
    while last > first and _is_filler(segments[last]):
        last -= 1
    # 2. too long: shrink from the end, one sentence at a time
    while last > first and _length(segments, first, last) > max_len:
        last -= 1
    # 3. too short: grow with real (non-filler) sentences that still fit, first forward
    #    to finish the thought, then backward to include the setup before it
    while (_length(segments, first, last) < min_len and last < hi - 1
           and not _is_filler(segments[last + 1])
           and _length(segments, first, last + 1) <= max_len):
        last += 1
    while (_length(segments, first, last) < min_len and first > lo
           and not _is_filler(segments[first - 1])
           and _length(segments, first - 1, last) <= max_len):
        first -= 1
    if not (min(min_len, 5) <= _length(segments, first, last) <= max_len):
        return None
    return first, last


def _lines(segments: list[dict], lo: int, hi: int, inside: range | None = None) -> str:
    out = []
    for i in range(lo, hi):
        mark = ">>" if inside is not None and i in inside else ".."
        out.append(f"{mark} [{i}] ({segments[i]['start']:.0f}s) {segments[i]['text']}")
    return "\n".join(out)


def _draft(segments: list[dict], min_len: float, max_len: float, count: int,
           exclude: set[int] = frozenset()) -> list[dict]:
    """Ask the model for moments. Sentences in `exclude` were already looked at: hide them."""
    candidates = []
    for lo in range(0, len(segments), WINDOW):
        hi = min(lo + WINDOW, len(segments))
        text = "\n".join(f"[{i}] ({segments[i]['start']:.0f}s) {segments[i]['text']}"
                         for i in range(lo, hi) if i not in exclude)
        if not text:
            continue
        answer = ask_json(DRAFT_SYSTEM.replace("{count}", str(count + 2)), text)
        for item in answer.get("clips", []):
            try:
                first, last = int(item["first"]), int(item["last"])
            except (KeyError, TypeError, ValueError):
                continue
            fixed = _fix_bounds(segments, first, last, lo, hi, min_len, max_len)
            if fixed and not any(i in exclude for i in range(fixed[0], fixed[1] + 1)):
                candidates.append({
                    "first": fixed[0], "last": fixed[1], "lo": lo, "hi": hi,
                    "title": str(item.get("title", ""))[:80],
                    "reason": str(item.get("reason", ""))[:300] or "Chosen by the AI.",
                    "mood": str(item.get("mood", "other")).lower()[:20],
                })
    return _drop_overlaps(candidates)


def _drop_overlaps(clips: list[dict]) -> list[dict]:
    kept = []
    for c in clips:
        if all(c["last"] < o["first"] or c["first"] > o["last"] for o in kept):
            kept.append(c)
    return kept


def _review(segments: list[dict], c: dict, min_len: float, max_len: float) -> dict | None:
    """Second opinion on one moment. Returns the improved moment, or None to drop it.

    Two separate questions, because small models answer one clear question much better:
    (a) where should the clip start and end?  (b) how good is the *corrected* clip?
    """
    lo = max(c["lo"], c["first"] - REVIEW_MARGIN)
    hi = min(c["hi"], c["last"] + 1 + REVIEW_MARGIN)
    answer = ask_json(ADJUST_SYSTEM,
                      _lines(segments, lo, hi, range(c["first"], c["last"] + 1)))
    first, last = c["first"], c["last"]
    try:  # accept boundary moves only if they are small and inside what we showed
        new_first, new_last = int(answer["first"]), int(answer["last"])
        if lo <= new_first <= new_last < hi and \
                abs(new_first - first) <= REVIEW_MARGIN and abs(new_last - last) <= REVIEW_MARGIN:
            first, last = new_first, new_last
    except (KeyError, TypeError, ValueError):
        pass
    fixed = _fix_bounds(segments, first, last, c["lo"], c["hi"], min_len, max_len)
    if fixed is None:
        return None
    first, last = fixed

    # score the final clip on its own, without surrounding context
    scored = ask_json(SCORE_SYSTEM, _lines(segments, first, last + 1))
    try:
        score = max(1, min(10, int(scored["score"])))
    except (KeyError, TypeError, ValueError):
        score = 5
    if score < MIN_SCORE:
        return None
    return {**c, "first": first, "last": last, "score": score}


def pick_ai_clips(segments: list[dict], min_len: float, max_len: float,
                  count: int) -> tuple[list[dict], str]:
    """Return (clips, note). note says which method was really used."""
    if not segments:
        return [], "No speech found."
    try:
        return _pick(segments, min_len, max_len, count)
    finally:
        unload()   # free the model's memory before the video editing starts


def _pick(segments: list[dict], min_len: float, max_len: float,
          count: int) -> tuple[list[dict], str]:
    reviewed, seen = [], set()   # seen = sentences the model has already looked at
    try:
        for _ in range(MAX_DRAFT_ROUNDS):
            drafts = _draft(segments, min_len, max_len, count, seen)
            if not drafts:
                break
            for c in drafts:
                seen.update(range(c["first"], c["last"] + 1))
            reviewed += [r for r in (_review(segments, c, min_len, max_len) for c in drafts) if r]
            if len(_drop_overlaps(reviewed)) >= count:
                break
    except LLMError as e:
        return (pick_clips(segments, min_len, max_len, count),
                f"AI unavailable, used the basic picker instead ({e})")
    if not reviewed:
        return (pick_clips(segments, min_len, max_len, count),
                "AI found no strong moments, used the basic picker instead")

    reviewed.sort(key=lambda c: -c["score"])        # best across the whole video first
    chosen = _drop_overlaps(reviewed)[:count]       # (boundaries may have moved: re-check)
    chosen.sort(key=lambda c: c["first"])           # show in video order
    out = []
    for c in chosen:
        out.append({
            "start": segments[c["first"]]["start"], "end": segments[c["last"]]["end"],
            "title": c["title"], "reason": c["reason"], "mood": c["mood"],
            "score": c["score"], "first": c["first"], "last": c["last"],
        })
    return out, "ok"
