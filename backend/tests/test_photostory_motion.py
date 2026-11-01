"""Tests for photo movement. Plain maths: no images, no FFmpeg."""
import math

import pytest

from app.photostory import motion

MOTIONS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down")
FOCI = [(0.5, 0.5), (0.0, 0.0), (1.0, 1.0), (0.9, 0.1), (0.1, 0.9)]


def inside(keys):
    for k in keys:
        half = 0.5 / k.zoom
        assert half - 1e-9 <= k.cx <= 1 - half + 1e-9, k
        assert half - 1e-9 <= k.cy <= 1 - half + 1e-9, k
        assert k.zoom >= 1.0


@pytest.mark.parametrize("name", MOTIONS)
@pytest.mark.parametrize("intensity", [0.05, 0.3, 0.6, 1.0])
@pytest.mark.parametrize("focus", FOCI)
def test_the_window_never_leaves_the_photo(name, intensity, focus):
    inside(motion.path(name, intensity, 6.0, focus))      # no black edges, ever


def test_a_still_picture_is_one_keyframe():
    for keys in (motion.path("hold", 1.0, 5), motion.path("zoom_in", 0, 5), motion.path("pan_left", 0, 5)):
        assert len(keys) == 1 and keys[0].zoom == 1.0


@pytest.mark.parametrize("name", MOTIONS)
def test_keyframes_run_from_zero_to_the_scene_length(name):
    keys = motion.path(name, 0.7, 8.0)
    assert len(keys) == motion.SAMPLES + 1
    assert keys[0].t == 0 and keys[-1].t == pytest.approx(8.0)
    assert all(a.t < b.t for a, b in zip(keys, keys[1:]))


def test_zoom_in_grows_steadily_to_the_chosen_strength():
    keys = motion.path("zoom_in", 0.6, 5)
    zooms = [k.zoom for k in keys]
    assert zooms[0] == 1.0 and zooms[-1] == pytest.approx(1 + motion.ZOOM_RANGE * 0.6)
    assert all(a <= b for a, b in zip(zooms, zooms[1:]))


def test_zoom_out_is_the_same_move_played_backwards():
    zin, zout = motion.path("zoom_in", 0.8, 5, (0.7, 0.4)), motion.path("zoom_out", 0.8, 5, (0.7, 0.4))
    assert [(k.zoom, k.cx, k.cy) for k in zout] == [(k.zoom, k.cx, k.cy) for k in reversed(zin)]
    assert zout[0].zoom > 1 and zout[-1].zoom == 1.0
    assert all(a.t < b.t for a, b in zip(zout, zout[1:]))


def test_a_stronger_zoom_goes_further():
    assert motion.path("zoom_in", 1.0, 5)[-1].zoom > motion.path("zoom_in", 0.3, 5)[-1].zoom


def test_zoom_in_heads_towards_the_focus_point():
    keys = motion.path("zoom_in", 1.0, 5, (0.8, 0.3))
    assert keys[-1].cx > 0.5 and keys[-1].cy < 0.5


@pytest.mark.parametrize("name,axis,sign", [("pan_right", "cx", 1), ("pan_left", "cx", -1),
                                            ("pan_down", "cy", 1), ("pan_up", "cy", -1)])
def test_pans_travel_the_right_way_at_a_constant_zoom(name, axis, sign):
    keys = motion.path(name, 0.6, 6)
    values = [getattr(k, axis) for k in keys]
    assert sign * (values[-1] - values[0]) > 0.05
    assert all(sign * (b - a) >= -1e-9 for a, b in zip(values, values[1:]))       # never doubles back
    assert len({round(k.zoom, 9) for k in keys}) == 1 and keys[0].zoom >= 1 + motion.MIN_PAN_ZOOM


def test_a_stronger_pan_travels_further():
    def travel(i):
        keys = motion.path("pan_right", i, 6)
        return keys[-1].cx - keys[0].cx
    assert travel(1.0) > travel(0.3) > 0


def test_movement_starts_and_ends_gently():
    keys = motion.path("zoom_in", 1.0, 6)
    steps = [b.zoom - a.zoom for a, b in zip(keys, keys[1:])]
    assert steps[0] < steps[len(steps) // 2] and steps[-1] < steps[len(steps) // 2]


def test_the_same_inputs_always_give_the_same_path():
    assert motion.path("pan_up", 0.4, 7, (0.3, 0.6)) == motion.path("pan_up", 0.4, 7, (0.3, 0.6))


# ---------------------------------------------------------------- expressions

def evaluate(expr, **names):
    """Run an FFmpeg-style expression in Python (only the functions we use)."""
    return eval(expr, {"__builtins__": {}}, {"clip": lambda v, lo, hi: max(lo, min(hi, v)), **names})


def test_window_at_is_a_straight_line_between_keyframes():
    keys = motion.path("zoom_in", 1.0, 4)
    assert motion.window_at(keys, 0)[0] == 1.0
    assert motion.window_at(keys, 99)[0] == keys[-1].zoom
    mid = (keys[3].t + keys[4].t) / 2
    assert motion.window_at(keys, mid)[0] == pytest.approx((keys[3].zoom + keys[4].zoom) / 2)


def test_linear_expression_matches_the_points_it_was_built_from():
    pts = [(0.0, 1.0), (10.0, 1.2), (20.0, 1.2), (30.0, 1.0)]
    expr = motion.linear_expression(pts)
    for x, v in pts:
        assert evaluate(expr, on=x) == pytest.approx(v, abs=1e-4)
    assert evaluate(expr, on=5) == pytest.approx(1.1, abs=1e-4)
    assert evaluate(expr, on=99) == pytest.approx(1.0, abs=1e-4)


def test_a_flat_path_is_just_a_number_and_a_falling_path_has_no_double_signs():
    assert motion.linear_expression([(0, 0.5), (50, 0.5)]) == "0.50000"
    falling = motion.linear_expression([(0, 1.0), (10, 0.5)])
    assert "+-" not in falling and evaluate(falling, on=10) == pytest.approx(0.5, abs=1e-4)


@pytest.mark.parametrize("name", MOTIONS)
@pytest.mark.parametrize("focus", FOCI)
def test_the_zoompan_window_stays_inside_the_picture_on_every_frame(name, focus):
    keys = motion.path(name, 1.0, 6)
    z, x, y = motion.zoompan_expressions(keys, 25)
    iw, ih = 2160, 3840
    for frame in range(0, 151):
        zoom = evaluate(z, on=frame)
        left, top = evaluate(x, on=frame, iw=iw, zoom=zoom), evaluate(y, on=frame, ih=ih, zoom=zoom)
        assert left >= -0.5 and top >= -0.5
        assert left + iw / zoom <= iw + 0.5 and top + ih / zoom <= ih + 0.5


def test_a_still_scene_gives_constant_expressions():
    z, x, y = motion.zoompan_expressions(motion.path("hold", 1, 5), 25)
    assert evaluate(z, on=0) == evaluate(z, on=100) == 1.0
    assert evaluate(x, on=0, iw=2160, zoom=1.0) == pytest.approx(0, abs=1e-6)


def test_expressions_are_safe_to_put_in_a_filter():
    z, x, y = motion.zoompan_expressions(motion.path("pan_left", 0.8, 6), 25)
    for e in (z, x, y):
        assert "'" not in e and ";" not in e and "\n" not in e and e.count("(") == e.count(")")
        assert len(e) < 1500                                  # short even with every keyframe


def test_frame_keys_follow_the_frame_rate():
    z, _, _ = motion.zoompan_expressions(motion.path("zoom_in", 1.0, 4), 25)
    assert evaluate(z, on=100) == pytest.approx(1 + motion.ZOOM_RANGE, abs=1e-3)          # 4 s at 25 fps
    assert not math.isnan(evaluate(z, on=50))
