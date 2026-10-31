"""Tests for the transcription benchmark's measurements (not the models themselves)."""
import pytest

from tools import asr_benchmark as b


def test_normalize_ignores_punctuation_case_and_spacing():
    assert b.normalize("  Hello,   WORLD! ") == "hello world"
    assert b.normalize("नमस्ते, दोस्तों।") == "नमस्ते दोस्तों"


def test_cer():
    assert b.cer("नमस्ते दोस्तों", "नमस्ते  दोस्तों।") == 0.0       # punctuation / spacing do not count
    assert b.cer("abcd", "abxd") == pytest.approx(0.25)           # one wrong letter of four
    assert b.cer("abcd", "") == 1.0
    assert b.cer("", "") == 0.0 and b.cer("", "x") == 1.0


def test_repeat_loops_counts_lines_said_again():
    lines = ["क्या हाल है", "दान सुख बोल", "दान सुख बोल", "दान सुख बोल।", "फिर कुछ और"]
    got = b.repeat_loops(lines)
    assert (got["repeated_lines"], got["longest_run"]) == (2, 3)
    assert b.repeat_loops(["a b", "c d", "a b"])["repeated_lines"] == 0
    assert b.repeat_loops(["hi", "hi"])["repeated_lines"] == 0    # one-word lines may genuinely repeat


def test_a_word_repeated_inside_one_line_is_caught():
    """The small model once wrote 'तो तो तो ...' dozens of times in ONE segment."""
    assert b.repeat_loops(["तो " * 60 + "ठीक है"])["word_run"] == 60
    assert b.repeat_loops(["बहुत बहुत अच्छा"])["word_run"] == 0   # a doubled word is normal speech
    assert b.repeat_loops([])["word_run"] == 0


def test_summarize_with_and_without_reference():
    segs = [{"text": " hello there", "compression_ratio": 1.0},
            {"text": " garbage", "no_speech_prob": 0.9, "avg_logprob": -2.0}]
    s = b.summarize(segs, 10.0, 5.0, 900, "hello there garbage")
    assert (s["segments"], s["times_real_time"], s["flagged_garbage"], s["cer"]) == (2, 0.5, 1, 0.0)
    assert "cer" not in b.summarize(segs, 10.0, 5.0, None)


def test_peak_memory_is_read_from_time_output():
    log = "  1.23 real\n 1234567890  maximum resident set size\n"
    assert b._peak_memory_mb(log) == round(1234567890 / 1024 / 1024)
    assert b._peak_memory_mb("nothing") is None
