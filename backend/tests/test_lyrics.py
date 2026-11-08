"""Timing lyrics to a song: matching heard words, filling the gaps, and where the photos change."""
import pytest

from app import lyrics


def seg(*words):
    return {"words": [{"word": w, "start": t} for w, t in words]}


def test_lines_are_tidied_and_blank_lines_are_skipped():
    assert lyrics.lyric_lines("  Hello   there \n\n  second line\n") == ["Hello there", "second line"]


def test_punctuation_is_ignored_but_hindi_is_kept():
    assert lyrics.norm("Aasman,") == "aasman"
    assert lyrics.norm("आसमान।") == "आसमान"


def test_each_line_is_found_in_the_order_it_is_sung():
    heard = lyrics.heard_words([seg(("hello", 1.0), ("there", 1.4), ("my", 2.0), ("friend", 2.3),
                                    ("goodbye", 5.0), ("now", 5.4))])
    starts = lyrics.match_lines(["Hello there", "my friend", "goodbye now"], heard)
    assert starts == [1.0, 2.0, 5.0]


def test_a_line_that_was_not_heard_is_left_out_of_the_match():
    heard = lyrics.heard_words([seg(("one", 1.0), ("two", 1.3), ("zzz", 2.0), ("qqq", 2.2))])
    assert lyrics.match_lines(["one two", "completely different words here"], heard) == [1.0, None]


def test_a_missing_line_is_spaced_between_its_neighbours_by_word_count():
    times = lyrics.fill_gaps([10.0, None, 20.0], total=40.0)
    assert times == [10.0, 15.0, 20.0]


def test_missing_lines_at_the_ends_are_spaced_to_the_song_edges():
    assert lyrics.fill_gaps([None, 10.0, None], total=20.0) == [5.0, 10.0, 15.0]


def test_no_line_found_at_all_spreads_them_over_the_song():
    assert lyrics.fill_gaps([None, None], total=20.0) == [0.0, 10.0]


def test_photos_change_on_the_nearest_lyric_line():
    lines_at = [0.0, 4.2, 9.6, 15.1, 22.0]
    starts = lyrics.photo_starts(lines_at, photo_count=3, begin=0.0, end=30.0)
    assert starts == [0.0, 9.6, 22.0]    # ideal 10 and 20 snap to the lines nearest them


def test_with_fewer_lines_than_photos_the_photos_share_the_time():
    starts = lyrics.photo_starts([5.0], photo_count=4, begin=0.0, end=40.0)
    assert starts == [0.0, 10.0, 20.0, 30.0]


def test_the_part_of_the_song_chosen_is_respected():
    starts = lyrics.photo_starts([5.0, 40.0, 52.0, 60.0, 130.0], photo_count=2, begin=30.0, end=90.0)
    assert starts[0] == 30.0 and 40.0 <= starts[1] <= 60.0


def test_each_photo_shows_the_line_that_starts_it_when_it_fits():
    texts = lyrics.photo_texts([0.0, 4.0, 9.6], ["first line", "second line", "third"],
                               starts=[0.0, 9.6], end=20.0, max_chars=40)
    assert texts == ["first line", "third"]


def test_a_line_too_long_for_the_text_is_not_shown():
    texts = lyrics.photo_texts([0.0], ["x" * 60], starts=[0.0], end=10.0, max_chars=40)
    assert texts == [""]
