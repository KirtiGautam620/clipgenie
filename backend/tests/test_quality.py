"""Tests for the transcript quality check. All fixtures are made up: nothing here is a real
person's speech. The checks prove the RULES work as designed; how well the thresholds suit real
creators' audio is a separate question (see tools/quality_report.py)."""
import json

import numpy as np
import pytest

from app import cuts, pipeline, quality

# ---------------------------------------------------------------- fixture builders

HINDI = ("आज हम सीखेंगे कि कैसे रोज़ थोड़ा थोड़ा अभ्यास करने से बड़ी से बड़ी मुश्किल आसान हो जाती है "
         "और फिर हर दिन नई चीज़ें सीखने का मन करता है इसलिए शुरुआत आज ही कीजिए").split()
ENGLISH = ("today we will learn how a little practice every single day makes even the hardest problem "
           "feel easy and then you want to learn something new each morning so start right now").split()


def words(tokens, start=0.0, step=0.4, p=0.9):
    return [{"word": " " + t, "start": round(start + i * step, 2), "end": round(start + i * step + 0.3, 2),
             **({"p": p} if p is not None else {})} for i, t in enumerate(tokens)]


def speech_envelope(seconds, speech_db=-20.0, floor_db=-65.0, gaps=()):
    """Loud, except a short quiet moment every 3 seconds (like pauses between sentences) and any
    extra `gaps` (start, end) which are near-silent. 10 ms frames."""
    env = np.full(int(seconds / cuts.FRAME) + 50, speech_db)
    for t in np.arange(2.7, seconds, 3.0):
        env[int(t / cuts.FRAME):int((t + 0.3) / cuts.FRAME)] = floor_db
    for a, b in gaps:
        env[int(a / cuts.FRAME):int(b / cuts.FRAME)] = floor_db
    return env


def good_asr(seconds):
    return [{"start": 0.0, "end": seconds, "avg_logprob": -0.3, "no_speech_prob": 0.02,
             "compression_ratio": 1.4}]


def judge(ws, *, seconds=None, envelope="auto", asr="auto", language="hi", **kw):
    seconds = seconds or (ws[-1]["end"] + 0.5 if ws else 5.0)
    if isinstance(envelope, str):
        envelope = speech_envelope(seconds)
    if isinstance(asr, str):
        asr = good_asr(seconds)
    return quality.assess_clip(ws, 0.0, seconds, language=language, asr=asr, dropped=[],
                               envelope=envelope, **kw)


# ---------------------------------------------------------------- the good case

def test_clean_hindi_and_english_speech_is_reliable():
    for tokens, lang in ((HINDI, "hi"), (ENGLISH, "en")):
        r = judge(words(tokens), language=lang)
        assert r["verdict"] == "reliable", r["reasons"]
        assert r["hard"] == [] and r["evidence"] == "full" and r["trusted_fraction"] == 1.0
        assert r["trusted_ranges"] and r["signals"]["audio_checked"]


def test_hinglish_with_some_english_words_is_fine():
    mixed = "आज हम सीखेंगे कि कैसे daily practice से हर problem आसान हो जाती है और फिर motivation भी बढ़ता है".split()
    assert judge(words(mixed))["verdict"] == "reliable"


# ---------------------------------------------------------------- repetition

def test_a_word_loop_is_unreliable():
    r = judge(words(HINDI[:12] + ["तो"] * 74))
    assert r["verdict"] in ("unreliable", "unusable") and "word_loop" in r["hard"]
    assert any("74" in why for why in r["reasons"])


def test_a_clip_that_is_mostly_loop_is_unusable_not_just_unreliable():
    r = judge(words(["दान"] * 80 + HINDI[:5]))
    assert r["verdict"] == "unusable" and r["trusted_fraction"] < quality.MIN_TRUSTED_FRACTION


def test_a_doubled_word_is_normal_speech():
    r = judge(words(HINDI[:6] + ["बहुत", "बहुत"] + HINDI[6:20]))
    assert r["verdict"] == "reliable" and r["signals"]["word_run"] == 2


def test_the_same_line_repeated_is_flagged():
    lines = ["क्या हाल है दोस्तों", "दान सुख बोल रे", "दान सुख बोल रे", "दान सुख बोल रे", "फिर मिलेंगे"]
    r = judge(words(HINDI), lines=lines)
    assert "line_loop" in r["hard"] and r["verdict"] == "unreliable"
    assert "line_repeat" in judge(words(HINDI), lines=lines[:3])["soft"]


def test_repetitive_text_is_flagged_by_the_repeat_ratio():
    r = judge(words(("मैं जा रहा हूँ तुम आ रहे हो " * 12).split()), seconds=40)
    assert "repetitive_text" in r["hard"] and r["signals"]["repeat_ratio"] > quality.REPEAT_RATIO_HARD
    assert r["verdict"] == "unreliable"


def test_ordinary_hindi_is_not_mistaken_for_repetition():
    """Raw-text compression would flag Devanagari itself (3 bytes per letter): the ratio must not."""
    paragraph = ("कल सुबह मैं बाज़ार गया था वहाँ मुझे एक पुराना दोस्त मिला उसने बताया कि वह अब शहर छोड़कर "
                 "गाँव में खेती करता है उसकी बातें सुनकर मुझे बहुत अच्छा लगा क्योंकि उसने अपने सपनों के लिए "
                 "मेहनत की थी हमने साथ चाय पी और पुरानी यादें ताज़ा कीं फिर उसने कहा कि अगली बार तुम भी "
                 "आना और देखना कैसे मिट्टी से सोना उगता है मैंने वादा किया कि जल्दी ही मिलूँगा").split()
    r = judge(words(paragraph, step=0.45))
    assert r["signals"]["repeat_ratio"] < 1.6 and "repetitive_text" not in r["hard"]


# ---------------------------------------------------------------- length proves nothing

def test_a_long_transcript_is_not_more_trustworthy():
    long_garbage = words((HINDI * 6)[:150], step=0.05)     # 150 words crammed into ~8 seconds
    r = judge(long_garbage, seconds=8)
    assert r["verdict"] != "reliable" and "too_many_words" in r["hard"]


def test_a_longer_clean_clip_is_judged_the_same_as_a_short_one():
    short = judge(words(HINDI))
    long = judge(words(HINDI + ENGLISH + HINDI[:10], step=0.45))
    assert short["verdict"] == long["verdict"] == "reliable"


# ---------------------------------------------------------------- the writing itself

def test_strange_characters_are_flagged_and_unusable():
    r = judge(words(["ʰᴀᴀᴀᴀᴀᴀᴀᴀ", "ᴀᴀᴀᴀᴀᴀʰʰ", "ᴀᴀᴀᴀʰᴀ", "ʰᴀᴀᴀᴀᴀᴀ"] * 4), language="en")
    assert "bad_characters" in r["hard"] and r["verdict"] == "unusable"


def test_a_hindi_clip_in_english_letters_is_a_warning():
    r = judge(words(ENGLISH), language="hi")
    assert "language_mismatch" in r["soft"] and r["verdict"] == "reliable"     # one warning alone is not enough


def test_two_warnings_together_make_it_unreliable():
    ws = words(["धन्यवाद"] * 5 + HINDI[:15])
    r = judge(ws, language="hi")
    assert len(r["soft"]) == 0 or r["verdict"] in ("reliable", "unreliable")      # sanity: no crash
    r = judge(words(ENGLISH[:5] + ["thanks", "for", "watching"] + ENGLISH[5:]), language="hi")
    assert {"language_mismatch", "stock_phrase"} <= set(r["soft"]) and r["verdict"] == "unreliable"


# ---------------------------------------------------------------- Whisper's own confidence

def test_many_low_confidence_words_are_unreliable():
    ws = words(HINDI)
    for w in ws[::2]:
        w["p"] = 0.15
    r = judge(ws)
    assert "low_confidence" in r["hard"] and r["verdict"] == "unreliable"


def test_a_few_low_confidence_words_alone_are_fine():
    ws = words(HINDI)
    for w in ws[:3]:
        w["p"] = 0.2
    assert judge(ws)["verdict"] == "reliable"


def test_weak_logprob_is_only_a_warning_by_itself():
    asr = [{"start": 0, "end": 30, "avg_logprob": -0.9, "no_speech_prob": 0.01}]
    r = judge(words(HINDI), asr=asr)
    assert "low_logprob" in r["soft"] and r["verdict"] == "reliable"


def test_text_thrown_away_by_whisper_counts_against_the_clip():
    ws = words(HINDI)
    seconds = ws[-1]["end"] + 0.5
    r = quality.assess_clip(ws, 0, seconds, asr=good_asr(seconds), envelope=speech_envelope(seconds),
                            dropped=[{"start": 2.0, "end": seconds - 1.0, "reason": "no speech"}])
    assert "much_dropped" in r["hard"] and r["verdict"] == "unreliable"


# ---------------------------------------------------------------- does the text line up with sound?

def test_words_over_silence_are_a_hard_failure():
    ws = words(HINDI)
    seconds = ws[-1]["end"] + 0.5
    env = speech_envelope(seconds, gaps=[(0.0, seconds * 0.55)])       # first half of the clip is silent
    r = quality.assess_clip(ws, 0, seconds, asr=good_asr(seconds), dropped=[], envelope=env)
    assert "words_over_silence" in r["hard"] and r["verdict"] == "unreliable"
    assert r["trusted_fraction"] < 0.7


def test_a_normal_pause_between_sentences_does_not_matter():
    ws = words(HINDI)
    seconds = ws[-1]["end"] + 0.5
    env = speech_envelope(seconds, gaps=[(3.05, 3.25)])
    r = quality.assess_clip(ws, 0, seconds, asr=good_asr(seconds), dropped=[], envelope=env)
    assert r["verdict"] == "reliable"


def test_lots_of_sound_with_hardly_any_words_is_suspicious():
    r = judge(words(HINDI[:5], step=2.0), seconds=40)
    assert "sound_without_words" in r["soft"]


def test_an_almost_silent_clip_is_unusable():
    seconds = 20
    r = judge(words(HINDI), seconds=seconds, envelope=speech_envelope(seconds, speech_db=-70.0, floor_db=-80.0))
    assert r["verdict"] == "unusable" and "silent" in r["reasons"][0]


def test_no_words_at_all_is_unusable():
    r = judge([], seconds=10)
    assert r["verdict"] == "unusable" and "No speech" in r["reasons"][0]
    assert judge(words(["।", "."]), seconds=10)["verdict"] == "unusable"      # punctuation is not speech


# ---------------------------------------------------------------- old jobs and privacy

def test_old_jobs_without_confidence_data_say_so():
    r = quality.assess_clip(words(HINDI, p=None), 0, 20, asr=None, dropped=None, envelope=None)
    assert r["evidence"] == "text_only" and not r["signals"]["audio_checked"]
    assert r["verdict"] == "reliable"          # nothing wrong is visible, but the evidence label says "text only"


def test_the_verdict_never_contains_the_transcript_text():
    ws = words(HINDI[:10] + ["तो"] * 20)
    blob = json.dumps(judge(ws), ensure_ascii=False)
    for token in set(HINDI[:10]):
        assert token not in blob.replace("तो", "")


def test_trusted_ranges_skip_the_bad_stretch():
    ws = words(HINDI[:15] + ["तो"] * 10 + HINDI[15:30], step=0.4)
    r = judge(ws)
    assert len(r["trusted_ranges"]) == 2 and 0 < r["trusted_fraction"] < 1
    first_end = r["trusted_ranges"][0][1]
    assert first_end <= 15 * 0.4 + 0.1


# ---------------------------------------------------------------- pipeline hook

def test_pipeline_helper_returns_a_verdict_and_never_raises():
    ws = words(HINDI)
    transcript = {"language": "hi", "segments": [{"start": 0, "end": 8, "text": "x", "words": ws}],
                  "asr": good_asr(8), "dropped": []}
    cut = {"cut_start": 0.0, "cut_end": ws[-1]["end"] + 0.3}
    got = pipeline._text_quality(transcript, ws, cut, speech_envelope(10))
    assert got["verdict"] == "reliable"
    broken = pipeline._text_quality({}, ws, cut, None)              # no "segments" key: must not raise
    assert broken["verdict"] == "unchecked" and broken["reasons"]


def test_words_and_lines_between_use_the_clip_window():
    ws = words(HINDI)
    inside = quality.words_between(ws, 1.0, 3.0)
    assert inside and all(w["start"] >= 0.95 and w["end"] <= 3.05 for w in inside)
    segs = [{"start": 0, "end": 2, "text": "a"}, {"start": 5, "end": 7, "text": "b"}]
    assert quality.lines_between(segs, 1.0, 3.0) == ["a"]


def test_steady_flat_sound_cannot_be_matched_to_words_so_it_is_a_warning():
    seconds = 14
    flat = np.full(int(seconds / cuts.FRAME) + 50, -25.0)             # constant level, no pauses
    r = judge(words(HINDI), seconds=seconds, envelope=flat)
    assert "flat_audio" in r["soft"] and "silent_words" not in r["signals"] and r["verdict"] == "reliable"
