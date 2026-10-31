"""Tests for caption styles: presets, user changes and validation."""
import pytest

from app import captionstyles as cs


def test_every_preset_resolves_and_its_font_exists():
    for name in cs.PRESETS:
        style = cs.resolve(name)
        assert style.preset == name and cs.font_path(style.weight).exists()


def test_the_default_look_is_not_the_yellow_outline_style():
    clean = cs.resolve(cs.DEFAULT_PRESET)
    assert clean.outline == 0 and clean.highlight_color != "#FFD400"


def test_user_changes_override_the_preset():
    s = cs.resolve("clean", {"size": 90, "highlight_color": "#00ff00", "animation": "pop"})
    assert (s.size, s.highlight_color, s.animation) == (90, "#00ff00", "pop")
    assert s.weight == "semibold"                 # untouched settings keep the preset's value


def test_numbers_outside_the_safe_range_are_clamped():
    s = cs.resolve("clean", {"position": 99, "size": 5, "words_per_line": 50, "outline": 99})
    assert s.position == cs.POSITION_MAX and s.size == 36 and s.words_per_line == 8 and s.outline == 12
    assert cs.resolve("clean", {"position": 1}).position == cs.POSITION_MIN


@pytest.mark.parametrize("bad", [
    {"text_color": "red"}, {"highlight_color": "#12345"}, {"weight": "comic"},
    {"animation": "spin"}, {"box": "star"}, {"size": "big"}, {"size": True},
    {"uppercase": "yes"}, {"font": "Arial"}, {"preset": "x", "color": 1}])
def test_invalid_settings_are_rejected(bad):
    with pytest.raises(ValueError):
        cs.resolve("clean", bad)


def test_unknown_preset_is_rejected():
    with pytest.raises(ValueError):
        cs.resolve("neon")


def test_preset_list_is_ready_for_the_page():
    items = cs.preset_list()
    assert [i["id"] for i in items] == list(cs.PRESETS)
    assert all(i["label"] and i["description"] and i["style"]["preset"] == i["id"] for i in items)


def test_contrast_text():
    assert cs.contrast_text("#FFB84D") == "#151515"
    assert cs.contrast_text("#222222") == "#FFFFFF"
