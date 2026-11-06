"""Tightening long pauses inside a clip (cuts.pause_segments): deterministic, safe, never on a word."""
import pytest

from app import cuts


def total(segments):
    return sum(b - a for a, b in segments)


def check_valid(segments, start, end):
    assert segments[0][0] == start and segments[-1][1] == end
    for (a, b), (c, d) in zip(segments, segments[1:]):
        assert a < b and b < c < d                     # ordered, with a real gap between parts


def test_a_long_pause_is_shortened_to_a_short_beat_in_its_middle():
    segs = cuts.pause_segments([(10.0, 12.0)], [], 0.0, 30.0)
    assert segs == [(0.0, 10.25), (11.75, 30.0)]       # 1.5 s removed, 0.5 s of pause stays
    check_valid(segs, 0.0, 30.0)


def test_short_pauses_are_left_alone():
    assert cuts.pause_segments([(10.0, 10.7)], [], 0.0, 30.0) == [(0.0, 30.0)]


def test_pauses_near_the_start_or_end_are_left_alone():
    assert cuts.pause_segments([(0.1, 2.0), (28.5, 29.9)], [], 0.0, 30.0) == [(0.0, 30.0)]


def test_a_pause_with_a_word_in_it_is_left_alone():
    words = [{"start": 10.9, "end": 11.2}]             # Whisper put a word in the 'silence'
    assert cuts.pause_segments([(10.0, 12.0)], words, 0.0, 30.0) == [(0.0, 30.0)]


def test_a_word_whose_early_timestamp_grazes_the_cut_does_not_block_it():
    """Seen on a real upload: Whisper put "Now" at 7.60 s, but the sound only starts at 7.96 s.
    Only a fifth of the word overlaps the removed part, so the pause is still tightened."""
    words = [{"start": 4.08, "end": 4.46}, {"start": 7.60, "end": 8.14}]
    segs = cuts.pause_segments([(4.51, 7.96)], words, 0.0, 13.8)
    assert segs == [(0.0, 4.76), (7.71, 13.8)]


def test_a_word_mostly_inside_the_cut_still_blocks_it():
    """If a word sits mostly in the 'silence', that silence may be quiet speech: leave the pause."""
    assert cuts.pause_segments([(4.5, 8.0)], [{"start": 6.0, "end": 6.4}], 0.0, 13.8) == [(0.0, 13.8)]
    # just over half of the word inside: blocked; just under: allowed
    # the part removed is 4.75-7.75 s: a word with 56% inside blocks it, one with 43% inside does not
    assert cuts.pause_segments([(4.5, 8.0)], [{"start": 7.30, "end": 8.10}], 0.0, 13.8) == [(0.0, 13.8)]
    assert len(cuts.pause_segments([(4.5, 8.0)], [{"start": 7.45, "end": 8.15}], 0.0, 13.8)) == 2


def test_a_zero_length_word_inside_the_cut_blocks_it():
    assert cuts.pause_segments([(4.5, 8.0)], [{"start": 6.0, "end": 6.0}], 0.0, 13.8) == [(0.0, 13.8)]


def test_words_outside_the_pause_do_not_block_it():
    words = [{"start": 9.0, "end": 9.95}, {"start": 12.05, "end": 12.6}]
    assert len(cuts.pause_segments([(10.0, 12.0)], words, 0.0, 30.0)) == 2


def test_never_removes_more_than_a_third_of_a_clip_longest_pauses_first():
    silences = [(5, 8), (10, 12), (14, 17), (19, 22), (24, 27)]      # five long pauses in a 40 s clip
    segs = cuts.pause_segments(silences, [], 0.0, 40.0)
    removed = 40.0 - total(segs)
    assert removed <= 40.0 * cuts.PAUSE_MAX_FRACTION + 1e-6
    assert len(segs) >= 2
    check_valid(segs, 0.0, 40.0)


def test_nothing_to_do_gives_the_whole_clip():
    assert cuts.pause_segments([], [], 3.0, 20.0) == [(3.0, 20.0)]


def test_pauses_outside_the_clip_are_ignored():
    assert cuts.pause_segments([(50.0, 53.0)], [], 0.0, 30.0) == [(0.0, 30.0)]


@pytest.mark.parametrize("silence", [(10.0, 11.4), (10.0, 20.0), (3.0, 4.0)])
def test_cuts_always_sit_inside_the_silence(silence):
    segs = cuts.pause_segments([silence], [], 0.0, 40.0)
    for (a, b), (c, d) in zip(segs, segs[1:]):
        assert silence[0] <= b and c <= silence[1]     # both sides of every cut are inside the quiet part
