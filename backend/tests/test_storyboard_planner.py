"""Tests for the shot library, the planner and the prompts. All plain text and numbers: no photo, no model."""
import pytest

from app.storyboard import model, planner, prompts, shots

EXAMPLE = ("Create a cinematic UGC video of this product with different camera angles, close-ups, "
           "and smooth transitions.")


def validated(plan, aspect="9:16"):
    """The plan must be something the model accepts."""
    return model.parse({"id": "0123456789ab", "title": "T", "aspect": aspect, "style": plan["style"], "prompt": "x",
                        "scenes": plan["scenes"]}, photo={"file": "photo.jpg", "width": 4000, "height": 3000})


# ---------------------------------------------------------------- the library

def test_every_shot_is_complete_and_valid():
    assert len(shots.SHOTS) >= 12
    for sid, s in shots.SHOTS.items():
        assert s.id == sid and s.label and s.camera and s.detail
        assert model.ZOOM[0] <= s.zoom <= model.ZOOM[1] and all(0 <= v <= 1 for v in s.focus)
        assert s.motion in shots.MOTIONS and 0 <= s.intensity <= 1 and model.DURATION[0] <= s.duration <= model.DURATION[1]
        assert shots.SHOT_PATTERNS[sid].pattern


def test_every_style_lists_real_shots_and_enough_of_them():
    for style in shots.STYLE_INFO.values():
        assert len(set(style.order)) == len(style.order) >= 6 and set(style.order) <= set(shots.SHOTS)
        assert style.transition in shots.TRANSITIONS and 0.2 <= style.transition_seconds <= 2.0


@pytest.mark.parametrize("text,shot", [
    ("a close-up of the label", "close_up"), ("extreme macro detail", "macro"), ("a low angle hero shot", "low_angle"),
    ("top-down on a table", "top_down"), ("an orbit around it", "orbit"), ("pull back to reveal", "pull_back"),
    ("someone holding it", "in_hand"), ("an unboxing", "unboxing"), ("lifestyle footage", "lifestyle"),
    ("slow push-in", "slow_push"), ("side profile", "side_profile"), ("a closing shot", "closing_hero"),
    ("a wide establishing shot", "establishing")])
def test_prompt_words_find_the_right_shot(text, shot):
    assert shot in planner.read_prompt(text)["shots"]


def test_shots_are_found_in_the_order_the_prompt_names_them():
    assert planner.read_prompt("start with a macro, then a close-up, then an orbit")["shots"] == ["macro", "close_up", "orbit"]


def test_ordinary_words_do_not_trigger_shots():
    found = planner.read_prompt("A video of a nice product for my customers, with a wide variety of colours")
    assert found["shots"] == [] and found["styles"] == []


# ---------------------------------------------------------------- the planner

def test_the_example_prompt_gives_a_sensible_cinematic_plan():
    p = planner.plan(EXAMPLE, product="a steel water bottle")
    titles = [s["title"] for s in p["scenes"]]
    assert p["style"] == "cinematic" and len(titles) == 6
    assert "In hand" in titles and "Close-up" in titles                      # what the prompt asked for
    assert titles[0] == "Establishing wide" and titles[-1] == "Closing hero"   # an opener and a closer
    assert p["understood"]["transition"] == "fade" and {s["transition"] for s in p["scenes"]} == {"fade"}
    assert any("cinematic and ugc" in n for n in p["notes"])                 # it says which style it chose
    validated(p)


def test_the_same_inputs_always_give_the_same_plan():
    assert planner.plan(EXAMPLE, product="x") == planner.plan(EXAMPLE, product="x")


def test_scenes_are_numbered_and_each_has_its_own_prompt():
    p = planner.plan(EXAMPLE)
    assert [s["id"] for s in p["scenes"]] == [f"s{i}" for i in range(1, 7)]
    assert len({s["prompt"] for s in p["scenes"]}) == 6
    assert all(f"Camera: {s['camera']}." in s["prompt"] for s in p["scenes"])


def test_a_prompt_does_not_depend_on_where_its_scene_sits():
    """So reordering, adding or deleting scenes can never leave a prompt saying the wrong thing."""
    p = planner.plan(EXAMPLE, product="a bottle")
    s = p["scenes"][3]
    assert s["prompt"] == prompts.compose_scene(camera=s["camera"], detail=s["detail"], duration=s["duration"],
                                                product="a bottle", style=p["style"], aspect="9:16")
    assert all(("Shot " not in x["prompt"] and "previous" not in x["prompt"]) for x in p["scenes"])


def test_no_prompt_uses_the_default_list_and_says_so():
    p = planner.plan("")
    assert len(p["scenes"]) == 6 and p["style"] == "none"
    assert any("No shot types were found" in n for n in p["notes"])
    assert p["scenes"][-1]["shot"] == "closing_hero"
    validated(p)


@pytest.mark.parametrize("n", range(2, 9))
def test_any_scene_count_from_two_to_eight_gives_distinct_shots(n):
    for style in shots.STYLES:
        p = planner.plan("", count=n, style=style)
        assert len(p["scenes"]) == n and len({s["shot"] for s in p["scenes"]}) == n
        validated(p)


def test_the_count_can_come_from_the_prompt_or_the_form_and_the_form_wins():
    assert len(planner.plan("give me 4 shots")["scenes"]) == 4
    assert len(planner.plan("give me 4 shots", count=7)["scenes"]) == 7
    assert len(planner.plan("5 different angles")["scenes"]) == 5


def test_a_count_outside_the_limits_is_corrected_and_the_user_is_told():
    big, small = planner.plan("", count=20), planner.plan("", count=1)
    assert len(big["scenes"]) == 8 and any("outside 2-8" in n for n in big["notes"])
    assert len(small["scenes"]) == 2 and any("outside 2-8" in n for n in small["notes"])


def test_if_the_prompt_asks_for_more_shots_than_scenes_the_extras_are_listed_as_left_out():
    p = planner.plan("macro, close-up, orbit, top-down, low angle and pull back", count=3)
    assert [s["shot"] for s in p["scenes"]] == ["macro", "close_up", "orbit"]
    assert any("left out" in n and "Top-down" in n for n in p["notes"])


def test_a_total_length_is_shared_between_the_scenes_within_limits():
    assert {s["duration"] for s in planner.plan("a 15 seconds video", count=5)["scenes"]} == {3.0}
    assert {s["duration"] for s in planner.plan("a 60 second video", count=4)["scenes"]} == {planner.MAX_SECONDS}
    assert {s["duration"] for s in planner.plan("a 4 second video", count=4)["scenes"]} == {planner.MIN_SECONDS}


def test_slow_motion_lengthens_scenes_and_is_written_into_the_camera_text():
    normal, slow = planner.plan("a macro shot"), planner.plan("a slow motion macro shot")
    assert slow["scenes"][0]["duration"] > normal["scenes"][0]["duration"]
    assert "slow motion" in slow["scenes"][0]["camera"] and "slow motion" not in normal["scenes"][0]["camera"]


@pytest.mark.parametrize("text,expected", [("smooth transitions", "fade"), ("seamless", "fade"),
                                           ("fast paced", "slide_left"), ("hard cuts", "cut")])
def test_transition_words_set_how_scenes_join(text, expected):
    assert {s["transition"] for s in planner.plan(text)["scenes"]} == {expected}


def test_the_chosen_style_overrides_the_prompt_and_sets_the_defaults():
    ugc = planner.plan("a cinematic video", style="ugc")
    assert ugc["style"] == "ugc" and ugc["scenes"][0]["shot"] == "in_hand"
    assert planner.plan("a cinematic video", style="none")["style"] == "none"
    assert planner.plan("a cinematic video")["style"] == "cinematic"


def test_bad_inputs_are_refused():
    with pytest.raises(ValueError, match="style must be"):
        planner.plan("x", style="neon")
    with pytest.raises(ValueError, match="aspect must be"):
        planner.plan("x", aspect="4:3")


def test_the_widescreen_plan_asks_for_horizontal_video():
    p = planner.plan("a macro shot", aspect="16:9")
    assert "horizontal 16:9" in p["scenes"][0]["prompt"]
    validated(p, "16:9")


# ---------------------------------------------------------------- the prompts

def one(**changes):
    args = dict(camera="close-up shot", detail="a feature of the product", duration=3.0,
                product="a steel water bottle", style="cinematic", aspect="9:16")
    args.update(changes)
    return prompts.compose_scene(**args)


def test_a_prompt_names_the_product_the_shot_the_style_and_the_format():
    text = one()
    assert "a steel water bottle" in text and "Camera: close-up shot." in text
    assert "Shows: A feature of the product." in text and "cinematic look" in text and "vertical 9:16" in text
    assert "3-second" in text


def test_every_prompt_tells_the_generator_not_to_change_the_product_or_add_text():
    for style in shots.STYLES:
        text = one(style=style)
        assert prompts.KEEP in text and prompts.NO_TEXT in text


def test_without_a_product_description_it_says_the_product_in_the_photo():
    assert "the product in the reference photo" in one(product="  ")


def test_no_style_adds_no_style_line():
    assert "Style:" not in one(style="none")


def test_compose_refuses_an_unknown_format():
    with pytest.raises(ValueError, match="aspect must be"):
        one(aspect="1:1")


def test_the_combined_text_has_every_scene():
    p = planner.plan("a macro shot", count=3)
    text = prompts.prompts_text("My bottle", "9:16", p["scenes"])
    assert text.startswith("Storyboard: My bottle") and text.count("=== Scene") == 3
    assert all(s["prompt"] in text for s in p["scenes"])
