"""Choose clip time ranges from a transcript (rule-based, no AI model needed).

Used when the AI picker is off or unavailable. The output format (a list of
{"start", "end", "reason"}) is what the rest of the pipeline expects.

Every candidate is a run of whole sentences, so a clip never starts or stops in the
middle of a sentence. Each candidate gets a score from things we can measure in the
transcript itself:
  + it opens with a hook (a question, a number, or a strong opening word)
  + it ends on a finished sentence
  + it is spoken with clear confidence (the recogniser's word confidence)
  + its pace is comfortable (about 2.8 words a second)
  + its length is near the middle of the range asked for
  - long silences inside it
  - a stock phrase such as "thanks for watching"
"""
import re

from app import quality

HOOK_WORDS = {"how", "why", "secret", "mistake", "mistakes", "never", "always", "stop", "truth",
              "real", "wrong", "best", "worst", "first", "nobody", "everyone", "you", "your", "if"}
STOCK = ("thanks for watching", "subscribe", "see you in the next", "like and share")
TARGET_WPS = 2.8
LONG_SILENCE = 1.0          # a gap between two words longer than this (seconds) counts as a silence
MIN_SHORT_CLIP = 5          # the shortest clip ever made when the video itself is short


def pick_clips(segments: list[dict], min_len: float = 30, max_len: float = 60,
               count: int = 3) -> list[dict]:
    """The best non-overlapping windows of whole sentences, in video order."""
    candidates = _candidates(segments, min_len, max_len)
    trusted = [c for c in candidates if c["trusted"]]
    if trusted:                       # windows of speech we cannot trust are skipped...
        candidates = trusted
    # ...unless there is nothing else, so the user still gets clips to review
    chosen: list[dict] = []
    for c in sorted(candidates, key=lambda c: -c["score"]):
        if len(chosen) >= count:
            break
        if all(c["end"] <= o["start"] or c["start"] >= o["end"] for o in chosen):
            chosen.append(c)
    chosen.sort(key=lambda c: c["start"])
    return [{"start": c["start"], "end": c["end"], "reason": c["reason"]} for c in chosen]


def pick_clips_basic(segments: list[dict], min_len: float = 30, max_len: float = 60,
                     count: int = 3) -> list[dict]:
    """The earlier picker: consecutive sentences from the start of the video. Kept for comparison."""
    clips = []
    i = 0
    while i < len(segments) and len(clips) < count:
        start = segments[i]["start"]
        j = i
        while j < len(segments) and segments[j]["end"] - start < min_len:
            j += 1
        if j >= len(segments):
            j = len(segments) - 1
        while j > i and segments[j]["end"] - start > max_len:
            j -= 1
        end = segments[j]["end"]
        if end - start >= min(min_len, MIN_SHORT_CLIP):
            clips.append({"start": start, "end": end,
                          "reason": "Basic pick: consecutive full sentences."})
        i = j + 1
    return clips


def _candidates(segments: list[dict], min_len: float, max_len: float) -> list[dict]:
    target = (min_len + max_len) / 2
    out = []
    for i in range(len(segments)):
        start = segments[i]["start"]
        for j in range(i, len(segments)):
            length = segments[j]["end"] - start
            if length > max_len:
                break
            if length < min(min_len, MIN_SHORT_CLIP):
                continue
            if length < min_len and not _short_video(segments, min_len):
                continue
            window = segments[i:j + 1]
            score, reasons = _score(window, target)
            trusted = _trusted(window)
            if not trusted:
                reasons.append("the speech is hard to trust")
            out.append({"start": start, "end": segments[j]["end"], "score": score, "trusted": trusted,
                        "reason": "; ".join(reasons) + "." if reasons else "Whole sentences."})
    return out


def _trusted(window: list[dict]) -> bool:
    """The same speech check the clip checks use (quality.assess_clip). A check that fails counts as trusted."""
    words = [w for s in window for w in s.get("words", [])]
    if not words:
        return False
    try:
        verdict = quality.assess_clip(words, window[0]["start"], window[-1]["end"], language="auto",
                                      lines=[s["text"] for s in window])["verdict"]
    except Exception:
        return True
    return verdict not in ("unusable", "unreliable")


def _short_video(segments: list[dict], min_len: float) -> bool:
    """True when the whole video is shorter than the minimum, so shorter clips are the only choice."""
    return bool(segments) and segments[-1]["end"] - segments[0]["start"] < min_len


def _score(window: list[dict], target: float) -> tuple[float, list[str]]:
    start, end = window[0]["start"], window[-1]["end"]
    length = max(end - start, 0.01)
    words = [w for s in window for w in s.get("words", [])]
    text = " ".join(s["text"] for s in window).lower()
    reasons, score = [], 0.0

    first = window[0]["text"].lower()
    first_words = set(re.findall(r"[a-z']+", first))
    if "?" in first or re.search(r"\d", first) or first_words & HOOK_WORDS:
        score += 2.0
        reasons.append("opens with a hook")

    if window[-1]["text"].strip()[-1:] in ".?!।":
        score += 1.0
        reasons.append("ends on a finished sentence")

    if words:
        conf = sum(float(w.get("p", 0.0)) for w in words) / len(words)
        score += 1.5 * min(max(conf, 0.0), 1.0)
        gaps = sum(1 for a, b in zip(words, words[1:]) if b["start"] - a["end"] > LONG_SILENCE)
        score -= 0.5 * gaps
        if gaps:
            reasons.append(f"has {gaps} long pause{'s' if gaps > 1 else ''}")
        wps = len(words) / length
        score -= min(abs(wps - TARGET_WPS) / TARGET_WPS, 2.0)
    else:
        score -= 1.0   # no word timings: we cannot judge the speech

    if any(p in text for p in STOCK):
        score -= 3.0
        reasons.append("contains a stock phrase")

    score -= 0.8 * abs(length - target) / target
    return score, reasons
