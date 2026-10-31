"""Tests for natural clip boundaries. The maths uses made-up words and pauses;
the silence detector is checked on a small synthetic WAV (tone, gap, tone)."""
import subprocess

import pytest

from app import cuts


def w(text, start, end):
    return {"word": " " + text, "start": start, "end": end}


# clip speech runs 10.0 - 20.0; a word ends at 9.0 and the next one starts at 22.0
WORDS = [w("before", 8.5, 9.0), w("start", 10.0, 10.4), w("finish.", 19.5, 20.0),
         w("after", 22.0, 22.4)]


def test_pads_when_there_is_no_pause_information():
    r = cuts.refine(WORDS, [], 10.0, 20.0, media_end=60)
    assert r["cut_start"] == pytest.approx(10.0 - cuts.PRE_ROLL)
    assert r["cut_end"] == pytest.approx(20.0 + cuts.TAIL)
    assert not r["start_snapped"] and not r["end_snapped"]


def test_never_crosses_into_neighbouring_words():
    words = [w("a", 9.5, 9.9), w("start", 10.0, 10.4), w("finish.", 19.5, 20.0), w("b", 20.1, 20.5)]
    r = cuts.refine(words, [], 10.0, 20.0, media_end=60)
    assert r["cut_start"] >= 9.9 + cuts.WORD_GUARD - 1e-9
    assert r["cut_end"] <= 20.1 - cuts.WORD_GUARD + 1e-9
    assert r["cut_start"] <= 10.0 and r["cut_end"] >= 20.0


def test_snaps_into_a_pause_that_contains_the_ideal_point():
    r = cuts.refine(WORDS, [(9.3, 9.95), (20.05, 21.5)], 10.0, 20.0, media_end=60)
    assert 9.3 <= r["cut_start"] <= 9.95 and r["start_snapped"]
    assert 20.05 <= r["cut_end"] <= 21.5 and r["end_snapped"]


def test_moves_into_a_nearby_pause_when_the_ideal_point_is_in_speech():
    # pause ends 0.5 s before the first word; plain pre-roll (9.75) would land in speech
    r = cuts.refine(WORDS, [(9.1, 9.5)], 10.0, 20.0, media_end=60)
    assert 9.1 <= r["cut_start"] <= 9.5 and r["start_snapped"]
    # pause begins 0.6 s after the last word; plain tail (20.4) would land in speech
    r = cuts.refine(WORDS, [(20.6, 21.9)], 10.0, 20.0, media_end=60)
    assert 20.6 <= r["cut_end"] <= 21.9 and r["end_snapped"]


def test_ignores_pauses_too_far_away():
    r = cuts.refine(WORDS, [(8.0, 8.4), (21.5, 21.9)], 10.0, 20.0, media_end=60)
    assert not r["start_snapped"] and not r["end_snapped"]


def test_stays_inside_the_video():
    r = cuts.refine([w("hi.", 0.1, 0.5)], [], 0.1, 0.5, media_end=0.6)
    assert r["cut_start"] >= 0 and r["cut_end"] <= 0.6 + 1e-9


def test_start_of_video_has_no_previous_word():
    r = cuts.refine([w("hi", 0.1, 0.5), w("there.", 0.6, 1.0)], [], 0.1, 1.0, media_end=30)
    assert r["cut_start"] == 0.0


def test_clean_end_flag():
    assert cuts.refine(WORDS, [], 10.0, 20.0, 60)["clean_end"] is True
    assert cuts.refine([w("and", 1.0, 1.3), w("then", 1.4, 1.8)], [], 1.0, 1.8, 60)["clean_end"] is False
    assert cuts.refine([w("हाँ।", 1.0, 1.5)], [], 1.0, 1.5, 60)["clean_end"] is True


def test_parse_silences_including_one_still_open_at_the_end():
    log = ("[silencedetect] silence_start: 1.5\n[silencedetect] silence_end: 2.25 | silence_duration: 0.75\n"
           "[silencedetect] silence_start: 9.5\n")
    assert cuts.parse_silences(log, 10.0) == [(1.5, 2.25), (9.5, 10.0)]
    assert cuts.parse_silences("[silencedetect] silence_start: -0.002\n[silencedetect] silence_end: 0.4 | x", 5) == [(0.0, 0.4)]


def test_threshold_is_limited():
    assert cuts.silence_threshold(-10) == -30
    assert cuts.silence_threshold(-60) == -50
    assert cuts.silence_threshold(-30) == -44


def test_detect_silences_on_real_audio(tmp_path):
    wav = tmp_path / "a.wav"   # 2 s tone, 1 s silence, 2 s tone
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=300:d=2",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1", "-f", "lavfi", "-i", "sine=f=300:d=2",
         "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1", str(wav)], check=True)
    found = cuts.detect_silences(wav)
    assert len(found) == 1
    assert found[0][0] == pytest.approx(2.0, abs=0.1) and found[0][1] == pytest.approx(3.0, abs=0.1)


# ---------------------------------------------------------------- quietest-point search

def _envelope(seconds, quiet_spots):
    """Loud (-20 dB) everywhere except tiny quiet gaps (-60 dB) at the given (start, end) times."""
    import numpy as np
    env = np.full(int(seconds / cuts.FRAME), -20.0)
    for a, b in quiet_spots:
        env[int(a / cuts.FRAME):int(b / cuts.FRAME)] = -60.0
    return env


def test_cuts_land_in_short_word_gaps_that_silencedetect_misses():
    # a 60 ms gap 0.15 s before the first word, and one 0.2 s after the last (no real pauses found)
    env = _envelope(30, [(9.82, 9.88), (20.15, 20.25)])
    r = cuts.refine(WORDS, [], 10.0, 20.0, 60, env)
    assert 9.82 <= r["cut_start"] <= 9.88
    assert 20.14 <= r["cut_end"] <= 20.26
    assert r["edge_db"] == [-60.0, -60.0]


def test_among_equally_quiet_points_the_nearest_to_the_word_wins():
    import numpy as np
    env = np.full(3000, -60.0)          # quiet everywhere: stay close to the word, not 0.25 s away
    r = cuts.refine(WORDS, [], 10.0, 20.0, 60, env)
    assert r["cut_start"] > 10.0 - 0.1 and r["cut_end"] < 20.0 + 0.1


def test_a_real_pause_still_beats_the_envelope_search():
    env = _envelope(30, [(9.82, 9.88)])
    r = cuts.refine(WORDS, [(9.3, 9.95)], 10.0, 20.0, 60, env)
    assert r["start_snapped"] and 9.3 <= r["cut_start"] <= 9.95


def test_load_envelope_sees_the_gap(tmp_path):
    wav = tmp_path / "a.wav"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=300:d=1",
         "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=0.5", "-f", "lavfi", "-i", "sine=f=300:d=1",
         "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1", "-ar", "16000", str(wav)], check=True)
    env = cuts.load_envelope(wav)
    assert abs(len(env) - 250) <= 2
    assert env[50] > -30 and env[125] < -50 and env[200] > -30
