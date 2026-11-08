"""Time the user's lyrics to a song.

1. Each lyric line is matched to the words Whisper heard in the song (in order). A line Whisper did
   not hear clearly gets a time between the lines around it, spaced by its number of words.
2. The photos change where the lyrics change: each photo starts on the lyric line nearest its even
   share of the video, so a change lands on a phrase, not in the middle of one.

Pure Python: no model is needed here, so the matching is tested without Whisper.
"""
import difflib
import re

MATCH_WINDOW = 120        # how many heard words to look through for one line
MIN_MATCH = 0.5           # below this similarity a line is treated as not heard


def lyric_lines(raw: str) -> list[str]:
    """One lyric line per non-blank line, tidied. Blank lines separate verses and are not sung text."""
    return [re.sub(r"\s+", " ", line).strip() for line in (raw or "").splitlines() if line.strip()]


def norm(word: str) -> str:
    """Lower case, no punctuation. Devanagari letters and vowel signs are kept."""
    return re.sub(r"[^\w\u0900-\u0963\u0966-\u097F]+", "", word.lower())   # not the danda (।)


def heard_words(segments: list[dict]) -> list[dict]:
    """Flatten Whisper's segments into [{"word", "start"}] with normalized words."""
    out = []
    for seg in segments:
        for w in seg.get("words", []):
            token = norm(w["word"])
            if token:
                out.append({"word": token, "start": float(w["start"])})
    return out


def match_lines(lines: list[str], heard: list[dict]) -> list[float | None]:
    """The start time of each lyric line in the heard words, or None where it was not heard."""
    starts: list[float | None] = []
    cursor = 0
    tokens_heard = [w["word"] for w in heard]
    for line in lines:
        tokens = [t for t in (norm(x) for x in line.split()) if t]
        if not tokens:
            starts.append(None)
            continue
        best_score, best_at = 0.0, None
        for at in range(cursor, min(len(heard), cursor + MATCH_WINDOW)):
            window = tokens_heard[at:at + len(tokens) + 2]
            score = difflib.SequenceMatcher(None, tokens, window).ratio()
            if score > best_score:
                best_score, best_at = score, at
        if best_at is not None and best_score >= MIN_MATCH:
            starts.append(heard[best_at]["start"])
            cursor = best_at + len(tokens)
        else:
            starts.append(None)
    return starts


def fill_gaps(starts: list[float | None], total: float) -> list[float]:
    """Give every line a time. A missing line is spaced between its neighbours by word count."""
    n = len(starts)
    if n == 0:
        return []
    known = [(i, t) for i, t in enumerate(starts) if t is not None]
    if not known:
        return [round(total * i / n, 2) for i in range(n)]
    out = list(starts)
    for i in range(n):
        if out[i] is not None:
            continue
        before = max(((j, t) for j, t in known if j < i), default=(-1, 0.0))
        after = min(((j, t) for j, t in known if j > i), default=(n, total))
        span = after[0] - before[0]
        out[i] = before[1] + (after[1] - before[1]) * (i - before[0]) / span
    # keep the order: a line never starts before the line above it
    for i in range(1, n):
        out[i] = max(out[i], out[i - 1])
    return [round(float(t), 2) for t in out]


def photo_starts(line_times: list[float], photo_count: int, begin: float, end: float) -> list[float]:
    """Where each photo starts, in seconds of the song. Each change snaps to the nearest lyric line
    that falls inside the video. With fewer lines than photos, the photos share the time evenly."""
    length = end - begin
    ideal = [begin + length * k / photo_count for k in range(photo_count)]
    inside = [t for t in line_times if begin < t < end - 0.5]   # no photo shorter than half a second
    if len(inside) < photo_count - 1:
        return [round(t, 2) for t in ideal]
    chosen = [begin]
    for target in ideal[1:]:
        candidates = [t for t in inside if t > chosen[-1] + 0.5]
        if not candidates:
            chosen.append(round(target, 2))
            continue
        chosen.append(min(candidates, key=lambda t: abs(t - target)))
    return [round(t, 2) for t in chosen]


LINE_MAX_SECONDS = 6.0    # a lyric line stays on screen this long at most (an instrumental gap does not hold it)


def cues(line_times: list[float], lines: list[str], begin: float, end: float, max_chars: int) -> list[dict]:
    """Each heard lyric line, on screen from its time until the next line starts (at most LINE_MAX_SECONDS).
    Times are seconds from the start of the video (begin = where the video's part starts in the song).
    A line that was not heard (None) or is too long for the text is left out."""
    timed = [(t, line) for t, line in zip(line_times, lines)
             if line and len(line) <= max_chars and begin <= t < end - 0.5]
    out = []
    for k, (t, line) in enumerate(timed):
        stop = timed[k + 1][0] if k + 1 < len(timed) else end
        stop = min(stop, t + LINE_MAX_SECONDS, end)
        if stop - t < 0.5:
            continue
        out.append({"text": line, "start": round(t - begin, 2), "end": round(stop - begin, 2)})
    return out


def photo_texts(line_times: list[float], lines: list[str], starts: list[float], end: float,
                max_chars: int) -> list[str]:
    """The lyric line that starts each photo (blank if it is too long for the text, or if none starts there)."""
    texts = []
    for k, start in enumerate(starts):
        stop = starts[k + 1] if k + 1 < len(starts) else end
        here = [line for line, t in zip(lines, line_times) if line and start <= t < stop]   # None = not heard
        first = here[0] if here else ""
        texts.append(first if len(first) <= max_chars else "")
    return texts
