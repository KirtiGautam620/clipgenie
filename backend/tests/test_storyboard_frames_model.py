"""Tests for the preview frame geometry and the storyboard data checks. Plain maths and tiny images."""
import copy
from io import BytesIO

import pytest
from PIL import Image

from app.storyboard import frames, model, planner

SIZES = [(4000, 3000), (3000, 4000), (1000, 1000), (800, 600), (6000, 1500), (1500, 6000)]


def scene(**kw):
    base = dict(zoom=1.0, intensity=0.5, motion="hold", focus=(0.5, 0.5))
    base.update(kw)
    return type("S", (), base)()


# ================================================================== geometry

@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("aspect", ["9:16", "16:9"])
@pytest.mark.parametrize("zoom", [1.0, 1.5, 3.0])
@pytest.mark.parametrize("centre", [(0.5, 0.5), (0.0, 0.0), (1.0, 1.0), (0.2, 0.8)])
def test_a_window_always_stays_inside_the_photo_and_has_the_right_shape(size, aspect, zoom, centre):
    w, h = size
    l, t, r, b = frames.window(w, h, aspect, zoom, *centre)
    assert -1e-9 <= l < r <= 1 + 1e-9 and -1e-9 <= t < b <= 1 + 1e-9
    want = frames.OUT_SIZE[aspect][0] / frames.OUT_SIZE[aspect][1]
    assert ((r - l) * w) / ((b - t) * h) == pytest.approx(want, rel=1e-6)


def test_zooming_in_makes_the_window_proportionally_smaller():
    full = frames.window(4000, 3000, "9:16", 1.0, 0.5, 0.5)
    double = frames.window(4000, 3000, "9:16", 2.0, 0.5, 0.5)
    assert (double[2] - double[0]) == pytest.approx((full[2] - full[0]) / 2)
    assert (double[3] - double[1]) == pytest.approx((full[3] - full[1]) / 2)


def test_a_focus_near_the_edge_is_pulled_back_inside():
    left = frames.window(4000, 3000, "9:16", 2.0, 0.0, 0.5)
    right = frames.window(4000, 3000, "9:16", 2.0, 1.0, 0.5)
    assert left[0] == 0 and right[2] == pytest.approx(1.0)


def test_a_hold_has_the_same_start_and_end():
    s, e = frames.boxes(4000, 3000, "9:16", scene(motion="hold", zoom=1.4, focus=(0.3, 0.6)))
    assert s == e


def test_push_in_ends_tighter_and_pull_out_starts_tighter():
    s, e = frames.boxes(4000, 3000, "9:16", scene(motion="push_in", intensity=1.0))
    assert (e[2] - e[0]) < (s[2] - s[0])
    s2, e2 = frames.boxes(4000, 3000, "9:16", scene(motion="pull_out", intensity=1.0))
    assert (s2[2] - s2[0]) < (e2[2] - e2[0]) and (s2, e2) == (e, s)


def test_a_stronger_push_goes_closer():
    weak = frames.boxes(4000, 3000, "9:16", scene(motion="push_in", intensity=0.2))[1]
    strong = frames.boxes(4000, 3000, "9:16", scene(motion="push_in", intensity=1.0))[1]
    assert (strong[2] - strong[0]) < (weak[2] - weak[0])


@pytest.mark.parametrize("motion,axis,sign", [("pan_right", 0, 1), ("pan_left", 0, -1), ("pan_down", 1, 1), ("pan_up", 1, -1)])
@pytest.mark.parametrize("size", [(4000, 3000), (3000, 4000), (1000, 1000)])
def test_pans_move_the_right_way_and_stay_inside_even_with_little_spare_picture(motion, axis, sign, size):
    s, e = frames.boxes(*size, "9:16", scene(motion=motion, intensity=0.8))
    moved = e[axis] - s[axis]
    assert sign * moved > 0.001
    for box in (s, e):
        assert -1e-9 <= box[0] < box[2] <= 1 + 1e-9 and -1e-9 <= box[1] < box[3] <= 1 + 1e-9


def test_a_stronger_pan_travels_further():
    def travel(i):
        s, e = frames.boxes(4000, 3000, "16:9", scene(motion="pan_right", intensity=i, zoom=1.5))
        return e[0] - s[0]
    assert travel(1.0) > travel(0.2) > 0


def test_zero_intensity_means_no_movement():
    for motion in ("push_in", "pull_out", "pan_left", "pan_up"):
        s, e = frames.boxes(4000, 3000, "9:16", scene(motion=motion, intensity=0))
        assert s == e


# ---------------------------------------------------------------- sharpness is real arithmetic

def test_sharpness_comes_from_the_pixels_left_after_cropping():
    big = frames.geometry(4000, 3000, "9:16", scene(zoom=1.0))["sharpness"]
    tiny = frames.geometry(400, 300, "9:16", scene(zoom=1.0))["sharpness"]
    assert big["label"] == "sharp" and tiny["label"] == "soft"
    assert big["ratio"] == pytest.approx(1687.5 / 1080, abs=0.01) and big["crop_px"] == [1688, 3000]
    assert tiny["ratio"] < 0.6


def test_zooming_in_makes_the_same_photo_softer():
    labels = [frames.geometry(2000, 1500, "9:16", scene(zoom=z))["sharpness"]["ratio"] for z in (1.0, 1.5, 2.0, 3.0)]
    assert labels == sorted(labels, reverse=True) and labels[-1] < labels[0]


def test_sharpness_uses_the_tighter_end_of_the_move():
    still = frames.geometry(4000, 3000, "9:16", scene(zoom=1.0, motion="hold"))["sharpness"]["ratio"]
    pushed = frames.geometry(4000, 3000, "9:16", scene(zoom=1.0, motion="push_in", intensity=1.0))["sharpness"]["ratio"]
    assert pushed < still


def test_landscape_output_is_judged_against_its_own_width():
    assert frames.geometry(3840, 2160, "16:9", scene())["sharpness"]["ratio"] == pytest.approx(3840 / 1920, abs=0.01)


# ---------------------------------------------------------------- drawing

def gradient(w=600, h=400):
    img = Image.new("RGB", (w, h))
    for x in range(w):
        for y in range(0, h, 40):
            img.paste((int(255 * x / w), 80, int(255 * (1 - x / w))), (x, y, x + 1, y + 40))
    return img


def test_frame_sizes_follow_the_format():
    assert frames.frame_size("9:16", 480) == (270, 480) and frames.frame_size("16:9", 480) == (480, 270)


def test_a_rendered_frame_is_a_jpeg_of_the_expected_size_and_shows_the_chosen_part():
    photo = gradient()
    left = frames.render(photo, frames.window(600, 400, "9:16", 1.0, 0.0, 0.5), "9:16", 160)
    right = frames.render(photo, frames.window(600, 400, "9:16", 1.0, 1.0, 0.5), "9:16", 160)
    a, b = Image.open(BytesIO(left)), Image.open(BytesIO(right))
    assert a.format == "JPEG" and a.size == (90, 160)
    assert a.getpixel((45, 80))[0] < b.getpixel((45, 80))[0]               # more red towards the right of the photo


def test_start_and_end_frames_of_a_move_differ_and_a_hold_does_not():
    photo = gradient()
    move = scene(motion="pan_right", intensity=1.0, zoom=2.0)
    s, e = frames.boxes(600, 400, "16:9", move)
    assert frames.render(photo, s, "16:9", 160) != frames.render(photo, e, "16:9", 160)
    s, e = frames.boxes(600, 400, "16:9", scene())
    assert frames.render(photo, s, "16:9", 160) == frames.render(photo, e, "16:9", 160)


# ================================================================== model

def good():
    p = planner.plan("a macro shot", count=3)
    return {"id": "0123456789ab", "title": "My bottle", "aspect": "9:16", "style": "none", "product": "a bottle",
            "prompt": "a macro shot", "rights": "own", "people": "none", "scenes": p["scenes"],
            "plan": {"understood": p["understood"], "notes": p["notes"]},
            "photo": {"file": "photo.jpg", "width": 4000, "height": 3000}}


def scene_with(**changes):
    raw = good()
    raw["scenes"][0].update(changes)
    return raw


def test_a_planned_storyboard_is_accepted_and_survives_save_and_load():
    first = model.to_dict(model.parse(good()))
    assert model.to_dict(model.parse(first)) == first
    assert len(first["scenes"]) == 3 and first["photo"]["width"] == 4000


@pytest.mark.parametrize("change,message", [
    ({"duration": 0.5}, "between 1 and 10"), ({"duration": 11}, "between 1 and 10"), ({"duration": True}, "must be a number"),
    ({"zoom": 0.9}, "between 1 and 3"), ({"zoom": 3.5}, "between 1 and 3"), ({"focus": [2, 0.5]}, "between 0 and 1"),
    ({"focus": [0.5]}, "two numbers"), ({"motion": "spin"}, "motion must be"), ({"transition": "boom"}, "transition must be"),
    ({"intensity": 2}, "between 0 and 1"), ({"transition_seconds": 9}, "between 0.2 and 2"), ({"id": "Bad Id"}, "id must be"),
    ({"title": ""}, "cannot be empty"), ({"title": "x" * 61}, "at most 60"), ({"shot": "levitate"}, "unknown shot"),
    ({"prompt": "x" * 1501}, "at most 1500"), ({"camera": "x" * 301}, "at most 300")])
def test_bad_scene_values_are_refused_with_the_scene_named(change, message):
    with pytest.raises(ValueError, match=message):
        model.parse(scene_with(**change))
    with pytest.raises(ValueError, match="Scene 1"):
        model.parse(scene_with(**change))


def test_a_custom_scene_is_allowed():
    assert model.parse(scene_with(shot="custom")).scenes[0].shot == "custom"


@pytest.mark.parametrize("mutate,message", [
    (lambda r: r.update(id="short"), "12 lowercase hex"), (lambda r: r.update(scenes=[]), "1 to 12 scenes"),
    (lambda r: r.update(scenes=r["scenes"] * 5), "1 to 12 scenes"),
    (lambda r: r["scenes"][1].update(id=r["scenes"][0]["id"]), "share the same id"),
    (lambda r: r.update(title=""), "cannot be empty"), (lambda r: r.update(aspect="4:3"), "Aspect must be"),
    (lambda r: r.update(style="neon"), "Style must be"), (lambda r: r.update(rights="stolen"), "Image rights must be"),
    (lambda r: r.update(people="maybe"), "People in the photo must be"), (lambda r: r.update(prompt="x" * 1001), "at most 1000"),
    (lambda r: r.update(product="x" * 201), "at most 200"), (lambda r: r.update(photo={"file": "../x.jpg", "width": 1, "height": 1}), "no valid photo"),
    (lambda r: r.update(photo=None), "no valid photo"), (lambda r: r.update(created="yesterday"), "timestamp"),
    (lambda r: r.update(plan={"notes": "no"}), "must be a list")])
def test_bad_storyboards_are_refused(mutate, message):
    raw = good()
    mutate(raw)
    with pytest.raises(ValueError, match=message):
        model.parse(raw)


def test_the_photo_facts_come_from_the_server_not_from_the_page():
    raw = good()
    raw["photo"] = {"file": "photo.jpg", "width": 1, "height": 1}
    sb = model.parse(raw, photo={"file": "photo.jpg", "width": 4000, "height": 3000})
    assert (sb.photo["width"], sb.photo["height"]) == (4000, 3000)


def test_parsing_never_changes_what_it_was_given():
    raw = good()
    before = copy.deepcopy(raw)
    model.parse(raw)
    assert raw == before


def test_rights_and_consent_block_export():
    raw = good()
    raw["rights"], raw["people"] = "unsure", "no_consent"
    blockers = model.export_blockers(model.parse(raw))
    assert len(blockers) == 2 and "right to use" in blockers[0] and "agreed" in blockers[1]
    assert model.export_blockers(model.parse(good())) == []
