"""Can the words Whisper heard in a clip be trusted? Judged from several independent signals.

No single score decides, and a longer transcript earns nothing: each signal can only push a clip
toward "unreliable". The result is a verdict plus plain-language reasons, so the page can later
explain itself. Nothing here ever returns the transcript text (only counts, times and reasons).

    reliable    - show word-level captions
    unreliable  - speech exists but the words cannot be trusted: do not show them
    unusable    - nothing understandable (no speech, silence, garbage): do not show or invent text

This is "shadow mode": pipeline.py records the verdict with each clip but nothing acts on it yet.
Thresholds were set from a handful of real clips (see tools/quality_report.py): treat them as a
starting point, and lean towards "unreliable", because burning wrong words in costs more than
losing the captions.
"""
import re
import unicodedata
import zlib

import numpy as np

from app.cuts import FRAME

# ---- thresholds (soft = a warning, hard = enough on its own to distrust the clip) ----
RUN_SOFT, RUN_HARD = 4, 8              # the same word, back to back
TRIGRAM_REPEAT_SOFT = 0.35             # share of 3-word phrases that already appeared
REPEAT_RATIO_HARD = 2.5                # how many times over the word sequence is repeating itself
BAD_SCRIPT_HARD = 0.05                 # letters that are neither Devanagari nor Latin
LATIN_IN_HINDI_SOFT = 0.35             # Hinglish is normal, but not mostly English letters
DEVANAGARI_IN_ENGLISH_SOFT = 0.2
LOW_P, LOW_FRACTION_SOFT, LOW_FRACTION_HARD, MEAN_P_SOFT = 0.4, 0.25, 0.4, 0.6
LOGPROB_SOFT = -0.7                    # Whisper retries below -1.0 on its own
NO_SPEECH_SOFT = 0.5
DROPPED_SOFT, DROPPED_HARD = 0.15, 0.35    # share of the clip Whisper itself threw away as made up
SILENT_WORDS_SOFT, SILENT_WORDS_HARD = 0.15, 0.30   # words that sit where nothing is audible
SILENT_MARGIN_DB, SILENT_ABS_DB = 6.0, -55.0
WPS_HIGH_SOFT, WPS_HIGH_HARD, WPS_LOW_SOFT = 6.5, 8.0, 0.3
WORDS_PER_ACTIVE_SECOND_LOW = 0.5      # lots of sound, very few words: music or unrecognised speech
NEAR_SILENT_DB = -55.0
MIN_AUDIO_RANGE_DB = 12.0              # below this there is no 'quiet' to compare words against
MIN_TRUSTED_FRACTION = 0.25
MIN_RANGE_WORDS, MIN_RANGE_SECONDS = 6, 2.0

# matched against the normalised text (lower case, punctuation removed, single spaces)
STOCK_PHRASES = re.compile(
    r"thanks? for watching|please (like|subscribe)|subtitles? by|amara org|transcribed by|captions? by")


def normalize(text: str) -> str:
    """Lower-case letters and combining marks only (Devanagari vowel signs are marks)."""
    text = unicodedata.normalize("NFC", text).lower()
    text = "".join(" " if unicodedata.category(c)[0] in "PSZC" else c for c in text)
    return re.sub(r"\s+", " ", text).strip()


def _script_shares(text: str) -> tuple[int, float, float, float]:
    """(letters, devanagari share, latin share, other share) among letters."""
    letters = [c for c in text if unicodedata.category(c)[0] in "LM"]
    if not letters:
        return 0, 0.0, 0.0, 0.0
    deva = sum("ऀ" <= c <= "ॿ" for c in letters)
    latin = sum(("a" <= c.lower() <= "z") for c in letters)
    n = len(letters)
    return n, deva / n, latin / n, (n - deva - latin) / n


def _word_run(tokens: list[str]) -> tuple[int, set[int]]:
    """Longest run of one token repeated back to back, and the positions inside runs of 4+."""
    best, start, in_loop = 1 if tokens else 0, 0, set()
    for i in range(1, len(tokens) + 1):
        if i == len(tokens) or tokens[i] != tokens[start]:
            if i - start >= RUN_SOFT:
                in_loop.update(range(start, i))
            best, start = max(best, i - start), i
    return best, in_loop


def _repeat_ratio(tokens: list[str]) -> float:
    """How much the word SEQUENCE compresses (about 1 = no repetition, 3 = every phrase ~3 times).
    Words are replaced by ids first: compressing the raw text would reward the byte patterns of
    Devanagari itself (3 bytes per letter) and make ordinary Hindi look repetitive."""
    ids: dict[str, int] = {}
    raw = b"".join(ids.setdefault(t, len(ids)).to_bytes(2, "big") for t in tokens)
    return len(raw) / max(1, len(zlib.compress(raw, 9)))


def _trigram_repeat(tokens: list[str]) -> float:
    grams = [tuple(tokens[i:i + 3]) for i in range(len(tokens) - 2)]
    return 1 - len(set(grams)) / len(grams) if len(grams) >= 10 else 0.0


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _syllabic_ratio(env_db: np.ndarray) -> float | None:
    """Share of the loudness wobble that happens at 2.5-7 Hz, the rhythm of syllables. Speech has a
    lot of it, steady music and chanting less. EXPERIMENTAL: recorded, not used in the verdict."""
    if len(env_db) < 400:
        return None
    x = 10 ** (env_db / 20)
    x = (x - x.mean()) * np.hanning(len(x))
    power = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(len(x), FRAME)
    wide = power[(freqs >= 0.5) & (freqs <= 20)].sum()
    return float(power[(freqs >= 2.5) & (freqs <= 7)].sum() / wide) if wide > 0 else None


def assess_clip(words: list[dict], start: float, end: float, *, language: str = "hi",
                asr: list[dict] | None = None, dropped: list[dict] | None = None,
                lines: list[str] | None = None, envelope: np.ndarray | None = None) -> dict:
    """Judge the words of one clip (times in the video's own seconds).

    words: transcript words {"word", "start", "end", optional "p"} that belong to the clip.
    asr / dropped: transcript["asr"] / ["dropped"] (Whisper's own figures; None for old jobs).
    lines: the clip's transcript lines (to spot a line repeated again and again).
    envelope: loudness per 10 ms of the whole video (cuts.load_envelope), to check alignment.
    """
    seconds = max(0.01, end - start)
    words = [w for w in words if normalize(w["word"])]      # punctuation-only "words" are not words
    tokens = [normalize(w["word"]) for w in words]
    text = " ".join(tokens)
    letters, deva, latin, other = _script_shares(text)
    hard: list[str] = []
    soft: list[str] = []
    reasons: dict[str, str] = {}
    signals: dict = {"words": len(tokens), "seconds": round(seconds, 1),
                     "words_per_second": round(len(tokens) / seconds, 2)}

    def flag(level: list, name: str, reason: str) -> None:
        level.append(name)
        reasons[name] = reason

    # ---- is there anything at all?
    audio_db = None
    if envelope is not None and len(envelope):
        window = envelope[int(start / FRAME):int(end / FRAME)]
        audio_db = window if len(window) else None
    near_silent = audio_db is not None and float(np.percentile(audio_db, 90)) < NEAR_SILENT_DB
    signals["audio_checked"] = audio_db is not None
    if not tokens or letters < 6:
        return _verdict("unusable", ["No speech was found in this clip."], [], [], signals, 0.0, [])
    if near_silent:
        return _verdict("unusable", ["The audio of this clip is almost silent."], [], [], signals, 0.0, [])

    # ---- repetition
    run, loop_positions = _word_run(tokens)
    signals["word_run"] = run
    if run >= RUN_HARD:
        flag(hard, "word_loop", f"One word is repeated {run} times in a row.")
    elif run >= RUN_SOFT:
        flag(soft, "word_repeat", f"One word is repeated {run} times in a row.")
    tri = _trigram_repeat(tokens)
    signals["trigram_repeat"] = round(tri, 2)
    if tri >= TRIGRAM_REPEAT_SOFT:
        flag(soft, "phrase_repeat", "The same phrases keep coming back.")
    if len(tokens) >= 40:
        ratio = _repeat_ratio(tokens)
        signals["repeat_ratio"] = round(ratio, 2)
        if ratio > REPEAT_RATIO_HARD:
            flag(hard, "repetitive_text", "The words repeat themselves far too much.")
    if lines:
        norm = [normalize(x) for x in lines]
        repeats = sum(1 for i in range(1, len(norm)) if len(norm[i].split()) >= 2 and norm[i] == norm[i - 1])
        signals["repeated_lines"] = repeats
        if repeats >= 2:
            flag(hard, "line_loop", "The same line is repeated several times in a row.")
        elif repeats == 1:
            flag(soft, "line_repeat", "A line is repeated.")

    # ---- the writing itself
    signals["script"] = {"devanagari": round(deva, 2), "latin": round(latin, 2), "other": round(other, 2)}
    if other > BAD_SCRIPT_HARD:
        flag(hard, "bad_characters", "The text has characters that are neither Hindi nor English.")
    if language == "hi" and latin > LATIN_IN_HINDI_SOFT:
        flag(soft, "language_mismatch", "A Hindi clip came out mostly in English letters.")
    if language == "en" and deva > DEVANAGARI_IN_ENGLISH_SOFT:
        flag(soft, "language_mismatch", "An English clip came out partly in Hindi letters.")
    if STOCK_PHRASES.search(text):
        flag(soft, "stock_phrase", "The text contains a phrase Whisper tends to invent (like 'thanks for watching').")

    # ---- Whisper's own confidence (missing for old jobs)
    ps = [w["p"] for w in words if w.get("p") is not None]
    if ps and len(ps) >= 0.8 * len(words):
        low = sum(p < LOW_P for p in ps) / len(ps)
        signals.update(mean_p=round(sum(ps) / len(ps), 2), low_confidence_words=round(low, 2))
        if low > LOW_FRACTION_HARD:
            flag(hard, "low_confidence", f"{low:.0%} of the words have very low confidence.")
        elif low > LOW_FRACTION_SOFT or sum(ps) / len(ps) < MEAN_P_SOFT:
            flag(soft, "weak_confidence", "Many words have low confidence.")
    if asr:
        weighted = [(_overlap(s["start"], s["end"], start, end), s) for s in asr]
        weighted = [(o, s) for o, s in weighted if o > 0 and s.get("avg_logprob") is not None]
        if weighted:
            total = sum(o for o, _ in weighted)
            avg_lp = sum(o * s["avg_logprob"] for o, s in weighted) / total
            signals["avg_logprob"] = round(avg_lp, 2)
            if avg_lp < LOGPROB_SOFT:
                flag(soft, "low_logprob", "Whisper was unsure of its own wording.")
            if any(s.get("no_speech_prob", 0) > NO_SPEECH_SOFT for _, s in weighted):
                flag(soft, "maybe_no_speech", "Whisper thought part of this might not be speech.")
    if dropped:
        gone = sum(_overlap(d["start"], d["end"], start, end) for d in dropped) / seconds
        signals["dropped_share"] = round(gone, 2)
        if gone > DROPPED_HARD:
            flag(hard, "much_dropped", "Much of this clip was thrown away by Whisper as made-up text.")
        elif gone > DROPPED_SOFT:
            flag(soft, "some_dropped", "Part of this clip was thrown away by Whisper as made-up text.")

    # ---- does the text line up with the sound?
    silent_idx: set[int] = set()
    if audio_db is not None:
        floor = float(np.percentile(audio_db, 5))
        loud = float(np.percentile(audio_db, 90))
        signals["audio_range_db"] = round(loud - floor, 1)
        if loud - floor < MIN_AUDIO_RANGE_DB:
            # No quiet moments at all (steady music or noise): words cannot be matched to sound
            flag(soft, "flat_audio", "The sound never pauses or changes the way speech does.")
        else:
            for i, w in enumerate(words):
                a, b = int(max(0, w["start"] - 0.1) / FRAME), int((w["end"] + 0.1) / FRAME)
                span = envelope[a:max(a + 1, b)]
                if len(span) and float(span.max()) < max(floor + SILENT_MARGIN_DB, SILENT_ABS_DB):
                    silent_idx.add(i)
            frac = len(silent_idx) / len(tokens)
            signals["silent_words"] = round(frac, 2)
            if len(tokens) >= 8 and frac > SILENT_WORDS_HARD:
                flag(hard, "words_over_silence", f"{frac:.0%} of the words fall where nothing is audible.")
            elif len(tokens) >= 8 and frac > SILENT_WORDS_SOFT:
                flag(soft, "words_near_silence", "Some words fall where nothing is audible.")
            active = float((audio_db > floor + 10).sum()) * FRAME
            signals["active_seconds"] = round(active, 1)
            if active >= 8 and len(tokens) / active < WORDS_PER_ACTIVE_SECOND_LOW:
                flag(soft, "sound_without_words", "There is a lot of sound but very few words: music, "
                                                  "singing or speech that was not recognised.")
        signals["syllabic_ratio"] = _round(_syllabic_ratio(audio_db))   # experimental: not in the verdict
    wps = len(tokens) / seconds
    if wps > WPS_HIGH_HARD:
        flag(hard, "too_many_words", "Far more words than anyone could say in this time.")
    elif wps > WPS_HIGH_SOFT:
        flag(soft, "many_words", "More words than is usual for this length.")
    elif wps < WPS_LOW_SOFT and seconds >= 10:
        flag(soft, "few_words", "Very few words for the length of this clip.")

    # ---- which words can be trusted, and where
    trusted = []
    for i, w in enumerate(words):
        ok = (i not in loop_positions and i not in silent_idx and (w.get("p") is None or w["p"] >= LOW_P)
              and _script_shares(tokens[i])[3] <= BAD_SCRIPT_HARD)
        trusted.append(ok)
    trusted_fraction = sum(trusted) / len(trusted)
    ranges = _trusted_ranges(words, trusted)

    if hard and trusted_fraction < MIN_TRUSTED_FRACTION:
        verdict = "unusable"
        reasons["nothing_trustworthy"] = "Almost none of the words can be trusted."
        hard.append("nothing_trustworthy")
    elif hard or len(soft) >= 2:
        verdict = "unreliable"
    else:
        verdict = "reliable"
    return _verdict(verdict, [reasons[n] for n in hard + soft], hard, soft, signals, trusted_fraction,
                    ranges, evidence="full" if (ps and asr is not None) else "text_only")


def _round(x):
    return None if x is None else round(x, 2)


def _trusted_ranges(words: list[dict], trusted: list[bool]) -> list[list[float]]:
    """Stretches of trustworthy words long enough to build on: [[start, end], ...]."""
    out, run = [], []
    for w, ok in list(zip(words, trusted)) + [(None, False)]:
        if ok:
            run.append(w)
            continue
        if len(run) >= MIN_RANGE_WORDS and run[-1]["end"] - run[0]["start"] >= MIN_RANGE_SECONDS:
            out.append([round(run[0]["start"], 2), round(run[-1]["end"], 2)])
        run = []
    return out


def _verdict(verdict, reasons, hard, soft, signals, trusted_fraction, ranges, evidence="text_only") -> dict:
    return {"verdict": verdict, "reasons": reasons, "hard": hard, "soft": soft, "evidence": evidence,
            "trusted_fraction": round(trusted_fraction, 2), "trusted_ranges": ranges, "signals": signals}


def words_between(words: list[dict], start: float, end: float) -> list[dict]:
    """The transcript words inside a clip's cut (same rule the captions use)."""
    return [w for w in words if w["start"] >= start - 0.05 and w["end"] <= end + 0.05 and w["word"].strip()]


def lines_between(segments: list[dict], start: float, end: float) -> list[str]:
    return [s["text"] for s in segments if s["end"] > start and s["start"] < end]
