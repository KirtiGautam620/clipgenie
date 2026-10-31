"""Tests for smart framing. The planning maths is tested with made-up face positions,
and the FFmpeg part with a small synthetic video (no real footage needed)."""
import math
import subprocess

import numpy as np
import pytest

from app import export, framing
from app.framing import SAMPLE_FPS, Plan, crop_x_expression, plan_framing

SRC_W, SRC_H = 1920, 1080
CROP_W = SRC_H * 9 / 16          # 607.5: the width of the 9:16 window


def face(x, size=200, y=400):
    return (float(x), float(y), float(size))


def seconds(n):
    return n * SAMPLE_FPS


def covers(plan: Plan, t: float, face_x: float) -> bool:
    """Is the face's centre inside the crop window at time t (straight lines between keys)?"""
    ts, xs = zip(*plan.keys)
    left = float(np.interp(t, ts, xs))
    return left <= face_x <= left + plan.crop_w


# ---------------------------------------------------------------- fallbacks

def test_no_faces_falls_back_to_centre_crop():
    plan = plan_framing([[] for _ in range(seconds(10))], SRC_W, SRC_H)
    assert plan.mode == "center"
    assert plan.keys[0][1] == pytest.approx((SRC_W - CROP_W) / 2)


def test_face_seen_too_rarely_falls_back_to_centre():
    samples = [[face(300)] if i < 8 else [] for i in range(seconds(10))]   # 8 of 30 samples
    assert plan_framing(samples, SRC_W, SRC_H).mode == "center"


def test_one_frame_false_alarms_are_ignored():
    samples = [[] for _ in range(seconds(10))]
    for i in (3, 11, 20):
        samples[i] = [face(300 + 400 * i % 1500)]
    assert plan_framing(samples, SRC_W, SRC_H).mode == "center"


def test_portrait_video_is_left_alone():
    plan = plan_framing([[face(300)]] * 30, 1080, 1920)
    assert plan.mode == "center"


# ---------------------------------------------------------------- following one speaker

@pytest.mark.parametrize("x", [250, 960, 1700])
def test_steady_speaker_gets_a_still_shot_that_contains_the_face(x):
    plan = plan_framing([[face(x)] for _ in range(seconds(10))], SRC_W, SRC_H)
    assert plan.mode == "static"
    assert len(plan.keys) == 1
    assert covers(plan, 0, x)
    assert 0 <= plan.keys[0][1] <= SRC_W - CROP_W


def test_moving_speaker_is_followed_and_stays_inside_the_crop():
    n = seconds(20)
    xs = np.linspace(400, 1500, n)                       # walks across the picture
    plan = plan_framing([[face(x)] for x in xs], SRC_W, SRC_H)
    assert plan.mode == "track"
    for i in range(0, n, 3):
        assert covers(plan, i / SAMPLE_FPS, xs[i]), f"face lost at sample {i}"


def test_crop_path_is_smooth():
    n = seconds(20)
    xs = np.linspace(400, 1500, n)
    plan = plan_framing([[face(x)] for x in xs], SRC_W, SRC_H)
    ts, left = map(np.array, zip(*plan.keys))
    speed = np.abs(np.diff(left) / np.diff(ts))
    assert speed.max() < 0.35 * CROP_W         # never faster than a third of the width per second


def test_small_sway_does_not_move_the_crop():
    rng = np.random.default_rng(1)
    xs = 900 + rng.normal(0, 12, seconds(15))             # a few pixels of head movement
    plan = plan_framing([[face(x)] for x in xs], SRC_W, SRC_H)
    assert plan.mode == "static"


def test_single_bad_detection_does_not_yank_the_crop():
    xs = np.full(seconds(15), 800.0)
    xs[20] = 1700                                          # one wild detection
    samples = [[face(x)] for x in xs]
    plan = plan_framing(samples, SRC_W, SRC_H)
    assert plan.mode == "static"
    assert covers(plan, 0, 800)


def test_speaker_briefly_out_of_sight_is_still_followed():
    samples = [[face(700)] if not 10 <= i < 16 else [] for i in range(seconds(10))]
    plan = plan_framing(samples, SRC_W, SRC_H)
    assert plan.mode == "static" and covers(plan, 5, 700)


# ---------------------------------------------------------------- several faces

def test_small_inset_face_does_not_hijack_the_speaker():
    samples = [[face(500, size=400), face(1750, size=110, y=200)] for _ in range(seconds(10))]
    plan = plan_framing(samples, SRC_W, SRC_H)
    assert plan.mode == "static" and covers(plan, 0, 500)


def test_two_close_faces_are_framed_together():
    samples = [[face(800, size=150), face(1050, size=150)] for _ in range(seconds(10))]
    plan = plan_framing(samples, SRC_W, SRC_H)
    assert plan.mode == "static"
    assert covers(plan, 0, 800) and covers(plan, 0, 1050)


def test_two_faces_too_far_apart_use_the_blur_layout():
    samples = [[face(300, size=250), face(1600, size=250)] for _ in range(seconds(10))]
    assert plan_framing(samples, SRC_W, SRC_H).mode == "blur"


# ---------------------------------------------------------------- the FFmpeg expression

def _evaluate(expr: str, t: float) -> float:
    return eval(expr, {"clip": lambda v, lo, hi: min(max(v, lo), hi), "t": t})


def test_expression_for_still_shot_is_a_plain_number():
    assert float(crop_x_expression([(0.0, 300.0)], 1.0)) == 300.0


def test_expression_matches_the_keyframes():
    keys = [(0.0, 100.0), (2.0, 100.0), (4.0, 500.0), (10.0, 300.0)]
    expr = crop_x_expression(keys, 2.0)
    for t, x in keys:
        assert _evaluate(expr, t) == pytest.approx(x * 2.0, abs=0.02)
    assert _evaluate(expr, 3.0) == pytest.approx(600.0, abs=0.02)      # halfway up the ramp
    assert _evaluate(expr, 99.0) == pytest.approx(600.0, abs=0.02)     # holds the last position


def test_simplify_keeps_the_shape_with_fewer_points():
    pts = [(i / 3, float(i * 3)) for i in range(60)]                   # a straight line
    assert len(framing._simplify(pts, 1.5)) == 2


def test_smoothing_leaves_a_constant_path_alone_and_has_no_lag():
    assert np.allclose(framing._smooth(np.full(30, 7.0), 3), 7.0)
    ramp = np.linspace(0, 100, 61)
    smoothed = framing._smooth(ramp, 3)
    assert smoothed[30] == pytest.approx(ramp[30], abs=0.5)           # middle matches: no delay


# ---------------------------------------------------------------- real FFmpeg export

def _make_video(path, w=1280, h=720, seconds_=4):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", f"testsrc2=size={w}x{h}:rate=25:duration={seconds_}",
                    "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds_}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
                   check=True)


def _size(path):
    return export.video_size(path)


def test_export_without_faces_keeps_the_old_centre_crop(tmp_path):
    src, out = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _make_video(src)
    info = export.export_clip(src, [], 0, 3, out, tmp_path, "crop")
    assert info["mode"] == "center"
    assert _size(out) == (1080, 1920)


def test_export_with_a_moving_crop_makes_a_valid_1080x1920_video(tmp_path, monkeypatch):
    src, out = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _make_video(src)
    crop_w = 720 * 9 / 16
    plan = Plan("track", "test", crop_w, [(0.0, 0.0), (1.0, 0.0), (2.5, 600.0), (3.0, 600.0)], 10, 10)
    monkeypatch.setattr(export, "plan_for_clip", lambda *a, **k: plan)
    info = export.export_clip(src, [], 0, 3, out, tmp_path, "crop")
    assert info["mode"] == "track"
    assert _size(out) == (1080, 1920)
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True).stdout)
    assert math.isclose(duration, 3.0, abs_tol=0.2)


def test_the_crop_really_moves_with_the_plan(tmp_path, monkeypatch):
    """testsrc2 has a different picture on the left and right: the frames must differ."""
    src, out = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _make_video(src)
    plan = Plan("track", "test", 720 * 9 / 16, [(0.0, 0.0), (0.2, 0.0), (2.5, 800.0), (3.0, 800.0)], 10, 10)
    monkeypatch.setattr(export, "plan_for_clip", lambda *a, **k: plan)
    export.export_clip(src, [], 0, 3, out, tmp_path, "crop")
    frames = []
    for t in (0.1, 2.9):
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(out),
                              "-frames:v", "1", "-vf", "scale=54:96,format=gray", "-f", "rawvideo", "-"],
                             capture_output=True, check=True).stdout
        frames.append(np.frombuffer(raw, np.uint8).astype(float))
    assert np.abs(frames[0] - frames[1]).mean() > 10


def test_blur_plan_switches_the_export_to_the_blur_layout(tmp_path, monkeypatch):
    src, out = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _make_video(src)
    monkeypatch.setattr(export, "plan_for_clip",
                        lambda *a, **k: Plan("blur", "two far faces", 405.0, [], 10, 10))
    info = export.export_clip(src, [], 0, 3, out, tmp_path, "crop")
    assert info["mode"] == "blur"
    assert _size(out) == (1080, 1920)


def test_detection_failure_never_breaks_the_export(tmp_path, monkeypatch):
    src = tmp_path / "in.mp4"
    _make_video(src)

    def boom(*a, **k):
        raise RuntimeError("no OpenCV")
    monkeypatch.setattr(framing, "detect_faces", boom)
    plan = framing.plan_for_clip(src, 0, 3, 1280, 720)
    assert plan.mode == "center" and "unavailable" in plan.reason


def test_real_detector_runs_on_a_video_without_faces(tmp_path):
    src = tmp_path / "in.mp4"
    _make_video(src)
    plan = framing.plan_for_clip(src, 0, 3, 1280, 720)
    assert plan.mode == "center"
