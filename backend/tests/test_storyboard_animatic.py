"""Tests for the animatic: a real video of the photo moving. Sizes are shrunk to a few dozen pixels, so
every render is a fraction of a second and uses very little memory. Nothing here uses a model."""
import json
import subprocess
import threading
import time
from io import BytesIO
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main, pipeline
from app.photostory import timing as story_timing
from app.storyboard import animatic, frames, model, store

PALETTE = {"red": (230, 40, 40), "green": (40, 200, 60), "blue": (40, 70, 230), "yellow": (240, 220, 40)}
TINY = {"preview": {"9:16": (54, 96), "16:9": (96, 54)}, "full": {"9:16": (108, 192), "16:9": (192, 108)}}


@pytest.fixture(autouse=True)
def tiny_sizes(monkeypatch):
    monkeypatch.setattr(animatic, "SIZES", TINY)


@pytest.fixture
def root(folders, tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "storyboards")
    return tmp_path / "storyboards"


def quadrant_photo():
    """Red top-left, green top-right, blue bottom-left, yellow bottom-right."""
    img = Image.new("RGB", (400, 300))
    for name, (x, y) in {"red": (0, 0), "green": (200, 0), "blue": (0, 150), "yellow": (200, 150)}.items():
        img.paste(PALETTE[name], (x, y, x + 200, y + 150))
    out = BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


FOCUS = {"red": (0.25, 0.25), "green": (0.75, 0.25), "blue": (0.25, 0.75), "yellow": (0.75, 0.75)}


def scene(color, duration=1.0, transition="fade", seconds=0.5, motion="hold", **kw):
    return {"zoom": 2.0, "focus": list(FOCUS[color]), "motion": motion, "intensity": 0.5, "duration": duration,
            "transition": transition, "transition_seconds": seconds, **kw}


def make_board(specs, aspect="9:16"):
    sb = store.create(quadrant_photo(), prompt="x", aspect=aspect, rights="own", people="none")
    raw = model.to_dict(sb)
    raw["scenes"] = [{**raw["scenes"][0], "id": f"s{i}", "title": f"Scene {i}", **spec} for i, spec in enumerate(specs, 1)]
    return store.save(model.parse(raw, photo=sb.photo))


def nearest(rgb):
    name = min(PALETTE, key=lambda n: float(np.linalg.norm(np.array(PALETTE[n]) - rgb)))
    return name, float(np.linalg.norm(np.array(PALETTE[name]) - rgb))


def decode(path, size):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, size[1], size[0], 3).astype(float)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_name,width,height,pix_fmt,color_range,color_space,nb_frames,codec_type:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    return {**video, "duration": float(data["format"]["duration"]),
            "audio": sum(s["codec_type"] == "audio" for s in data["streams"])}


def run_render(sid, quality="preview"):
    run = animatic.start(sid, quality)
    run()
    return animatic.status(store.load(sid))


# ================================================================== timing and easing

def test_overlaps_follow_exactly_the_same_rules_as_photo_story():
    cases = [("fade", 0.6, 4, 4), ("cut", 0.6, 4, 4), ("slide_left", 2.0, 1, 1), ("wipe_left", 0.3, 5, 1.5)]
    for kind, seconds, d_prev, d_next in cases:
        pair = [SimpleNamespace(duration=d_prev, transition="fade", transition_seconds=0.6, narration_seconds=None),
                SimpleNamespace(duration=d_next, transition=kind, transition_seconds=seconds, narration_seconds=None)]
        assert animatic.overlaps(pair) == story_timing.overlaps(pair), kind
        assert animatic.starts(pair) == story_timing.starts(pair)
        assert animatic.total_seconds(pair) == story_timing.total_seconds(pair)


def test_the_video_is_as_long_as_the_scenes_added_together():
    scenes = [SimpleNamespace(duration=d) for d in (2, 3.5, 1.5)]
    assert animatic.total_seconds(scenes) == 7.0 and animatic.frame_count(scenes) == 175
    assert animatic.starts(scenes) == [0.0, 2.0, 5.5]


def test_easing_starts_and_ends_gently_and_never_overshoots():
    assert animatic.ease(0) == 0 and animatic.ease(1) == 1 and animatic.ease(0.5) == pytest.approx(0.5)
    assert animatic.ease(-1) == 0 and animatic.ease(2) == 1
    steps = [animatic.ease((i + 1) / 20) - animatic.ease(i / 20) for i in range(20)]
    assert min(steps) >= 0 and steps[0] < steps[10] and steps[-1] < steps[10]


def test_the_box_moves_from_the_start_frame_to_the_end_frame():
    a, b = (0.0, 0.0, 0.5, 0.5), (0.5, 0.5, 1.0, 1.0)
    assert animatic.box_at(a, b, 0) == a and animatic.box_at(a, b, 1) == b
    assert animatic.box_at(a, b, 0.5) == pytest.approx((0.25, 0.25, 0.75, 0.75))


# ================================================================== single frames

def photo():
    return Image.open(BytesIO(quadrant_photo())).convert("RGB")


@pytest.mark.parametrize("colour", list(FOCUS))
def test_a_scene_frame_shows_the_part_of_the_photo_it_looks_at(colour):
    s = SimpleNamespace(zoom=2.0, intensity=0.5, motion="hold", focus=FOCUS[colour])
    start, end = frames.boxes(400, 300, "9:16", s)
    frame = animatic.scene_frame(photo(), start, end, 1.0, 0.5, (54, 96))
    name, distance = nearest(np.asarray(frame, float).mean(axis=(0, 1)))
    assert name == colour and distance < 25


def test_a_moving_scene_starts_on_its_start_frame_and_ends_on_its_end_frame():
    s = SimpleNamespace(zoom=2.0, intensity=1.0, motion="pan_right", focus=(0.5, 0.25))
    start, end = frames.boxes(400, 300, "9:16", s)
    p = photo()
    first, last = animatic.scene_frame(p, start, end, 2.0, 0.0, (54, 96)), animatic.scene_frame(p, start, end, 2.0, 2.0, (54, 96))
    assert first.tobytes() == animatic.scene_frame(p, start, start, 2.0, 0.0, (54, 96)).tobytes()
    assert last.tobytes() == animatic.scene_frame(p, end, end, 2.0, 0.0, (54, 96)).tobytes()
    assert first.tobytes() != last.tobytes()


def test_a_scene_holds_its_last_frame_after_its_own_time_and_its_first_before_it():
    s = SimpleNamespace(zoom=2.0, intensity=1.0, motion="push_in", focus=(0.5, 0.5))
    start, end = frames.boxes(400, 300, "9:16", s)
    p = photo()
    at = lambda t: animatic.scene_frame(p, start, end, 1.0, t, (54, 96)).tobytes()
    assert at(1.0) == at(5.0) and at(0.0) == at(-3.0)


# ================================================================== transitions

def flat(rgb, size=(40, 40)):
    return Image.new("RGB", size, rgb)


def half_colours(img):
    a = np.asarray(img, float)
    return nearest(a[:, :12].mean(axis=(0, 1)))[0], nearest(a[:, -12:].mean(axis=(0, 1)))[0]


def test_every_transition_starts_on_the_old_picture_and_ends_on_the_new_one():
    a, b = flat(PALETTE["red"]), flat(PALETTE["green"])
    for kind in ("fade", "slide_left", "slide_right", "wipe_left"):
        assert animatic.blend(a, b, kind, 0).tobytes() == a.tobytes(), kind
        assert animatic.blend(a, b, kind, 1).tobytes() == b.tobytes(), kind
    assert animatic.blend(a, b, "cut", 0.3).tobytes() == b.tobytes()


def test_a_fade_halfway_is_a_mix_of_both():
    mid = np.asarray(animatic.blend(flat(PALETTE["red"]), flat(PALETTE["green"]), "fade", 0.5), float).mean(axis=(0, 1))
    assert nearest(mid)[1] > 40
    assert np.linalg.norm(mid - (np.array(PALETTE["red"]) + np.array(PALETTE["green"])) / 2) < 3


def test_slides_and_wipes_show_both_pictures_side_by_side_and_the_two_slides_mirror_each_other():
    a, b = flat(PALETTE["red"]), flat(PALETTE["green"])
    left, right = half_colours(animatic.blend(a, b, "slide_left", 0.5)), half_colours(animatic.blend(a, b, "slide_right", 0.5))
    assert left == ("red", "green") and right == ("green", "red")            # new picture arrives from the right / left
    assert half_colours(animatic.blend(a, b, "wipe_left", 0.5)) == ("red", "green")


def test_a_wipe_uncovers_more_of_the_new_picture_as_it_goes():
    a, b = flat(PALETTE["red"]), flat(PALETTE["green"], (40, 40))
    shares = []
    for p in (0.25, 0.5, 0.75):
        arr = np.asarray(animatic.blend(a, b, "wipe_left", p), float)
        shares.append(float((np.abs(arr - np.array(PALETTE["green"])).sum(axis=2) < 30).mean()))
    assert shares == sorted(shares) and 0.15 < shares[0] < 0.35 and shares[-1] > 0.65


# ================================================================== a whole frame

def timeline(specs):
    sb = make_board(specs)
    return sb, photo(), animatic.scene_boxes(sb), animatic.starts(sb.scenes), animatic.overlaps(sb.scenes)


def colour_at(parts, t):
    sb, p, boxes, begin, overlap = parts
    frame = animatic.compose(p, sb.scenes, boxes, begin, overlap, t, (54, 96))
    return nearest(np.asarray(frame, float).mean(axis=(0, 1)))


def test_each_scene_shows_its_own_part_of_the_photo_between_transitions(root):
    parts = timeline([scene("red"), scene("green"), scene("blue", transition="cut")])
    for t, name in [(0.3, "red"), (0.95, "red"), (1.8, "green"), (2.6, "blue")]:
        got, distance = colour_at(parts, t)
        assert got == name and distance < 30, (t, got, distance)


def test_a_cut_is_instant_and_a_fade_passes_through_a_mix(root):
    parts = timeline([scene("red"), scene("green"), scene("blue", transition="cut")])
    for t in (1.92, 1.96, 1.99, 2.0, 2.01, 2.04, 2.08):                      # around the cut at 2.0 s
        assert colour_at(parts, t)[1] < 30, t                              # always a clean colour, never a blend
    assert colour_at(parts, 1.96)[0] == "green" and colour_at(parts, 2.04)[0] == "blue"
    assert colour_at(parts, 1.25)[1] > 40                                  # half way through the fade at 1.0-1.5 s


# ================================================================== the real video

def test_a_three_scene_animatic_is_a_real_standard_video_with_the_right_pictures(root):
    sb = make_board([scene("red"), scene("green"), scene("blue", transition="cut")])
    status = run_render(sb.id)
    assert status["state"] == "done" and status["frames"] == 75 and status["progress"] == 1.0 and status["stale"] is False
    path = store.folder(sb.id) / "animatic.mp4"
    info = probe(path)
    assert (info["codec_name"], info["width"], info["height"]) == ("h264", 54, 96)
    assert info["pix_fmt"] == "yuv420p" and info["color_range"] == "tv" and info["color_space"] == "bt709"
    assert info["nb_frames"] == "75" and info["duration"] == pytest.approx(3.0, abs=0.05) and info["audio"] == 0
    assert subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True).stderr.strip() == ""
    video = decode(path, (54, 96))
    at = lambda t: nearest(video[min(len(video) - 1, round(t * 25))].mean(axis=(0, 1)))
    assert [at(t)[0] for t in (0.4, 1.8, 2.6)] == ["red", "green", "blue"]
    assert at(1.25)[1] > 35                                                 # the fade really blends
    assert not (store.folder(sb.id) / "animatic.partial.mp4").exists()


def test_widescreen_storyboards_make_widescreen_video(root):
    sb = make_board([scene("red"), scene("green")], aspect="16:9")
    run_render(sb.id)
    info = probe(store.folder(sb.id) / "animatic.mp4")
    assert (info["width"], info["height"]) == (96, 54)


def test_moving_scenes_really_move_in_the_video(root):
    sb = make_board([scene("red", 2.0, motion="push_in", intensity=1.0)])
    run_render(sb.id)
    video = decode(store.folder(sb.id) / "animatic.mp4", (54, 96))
    assert float(np.abs(video[0] - video[-1]).mean()) > 0 and video.shape[0] == 50


def test_the_best_quality_is_a_bigger_picture_of_the_same_scenes(root):
    sb = make_board([scene("red"), scene("green")])
    run_render(sb.id, "full")
    info = probe(store.folder(sb.id) / "animatic.mp4")
    assert (info["width"], info["height"]) == (108, 192)
    assert animatic.status(store.load(sb.id))["quality"] == "full"


def test_the_encoder_runs_gently_and_names_the_colour_standard(monkeypatch, root):
    seen = {}

    class Fake:
        stdin = BytesIO()
        stderr = BytesIO()

        def poll(self): return 0
        def wait(self): return 0

    monkeypatch.setattr(animatic.subprocess, "Popen", lambda cmd, **k: seen.setdefault("cmd", cmd) and Fake())
    animatic._encoder(root / "x.mp4", (54, 96), "preview")
    cmd = seen["cmd"]
    assert cmd[:3] == ["nice", "-n", "10"] and cmd[cmd.index("-threads") + 1] == "2"
    assert "out_color_matrix=bt709:out_range=tv" in cmd[cmd.index("-vf") + 1]
    assert cmd[cmd.index("-colorspace") + 1] == "bt709" and "-an" in cmd


# ================================================================== is it still up to date?

def test_a_finished_animatic_goes_out_of_date_only_when_the_picture_would_change(root):
    sb = make_board([scene("red"), scene("green")])
    assert run_render(sb.id)["stale"] is False
    raw = model.to_dict(store.load(sb.id))
    raw["scenes"][0].update(title="A new name", prompt="new words", camera="new camera text")
    store.save(model.parse(raw, photo=sb.photo))
    assert animatic.status(store.load(sb.id))["stale"] is False             # names and prompts are not in the video
    for change in ({"duration": 2.0}, {"zoom": 1.5}, {"focus": [0.1, 0.9]}, {"motion": "push_in"}, {"transition": "cut"}):
        raw = model.to_dict(store.load(sb.id))
        raw["scenes"][1].update(change)
        store.save(model.parse(raw, photo=sb.photo))
        assert animatic.status(store.load(sb.id))["stale"] is True, change
        raw["scenes"][1].update({"duration": 1.0, "zoom": 2.0, "focus": [0.75, 0.25], "motion": "hold", "transition": "fade"})
        store.save(model.parse(raw, photo=sb.photo))


def test_the_fingerprint_depends_on_the_quality_and_the_shape(root):
    a = make_board([scene("red")])
    b = make_board([scene("red")], aspect="16:9")
    assert animatic.fingerprint(a, "preview") != animatic.fingerprint(a, "full")
    assert animatic.fingerprint(a, "preview") != animatic.fingerprint(b, "preview")
    assert animatic.fingerprint(a, "preview") == animatic.fingerprint(store.load(a.id), "preview")


# ================================================================== safety

def test_it_will_not_start_when_the_disk_or_memory_is_short(root, monkeypatch):
    sb = make_board([scene("red")])
    with monkeypatch.context() as m:
        m.setattr(animatic.shutil, "disk_usage", lambda p: SimpleNamespace(free=int(0.3e9)))
        with pytest.raises(animatic.Busy, match="disk space"):
            animatic.start(sb.id, "preview")
    with monkeypatch.context() as m:
        m.setattr(animatic, "_pressure", lambda: 4)
        with pytest.raises(animatic.Busy, match="short of memory"):
            animatic.start(sb.id, "preview")
    assert not pipeline.heavy_job_lock.locked() and not animatic._cancel


def test_it_does_not_start_while_other_heavy_work_is_running(root):
    sb = make_board([scene("red")])
    with pipeline.heavy_job_lock:
        with pytest.raises(animatic.Busy, match="busy processing"):
            animatic.start(sb.id, "preview")
    assert not (store.folder(sb.id) / "animatic.json").exists()


def test_bad_requests_to_start_are_refused(root):
    sb = make_board([scene("red")])
    with pytest.raises(ValueError, match="quality must be"):
        animatic.start(sb.id, "ultra")
    with pytest.raises(store.UnknownStoryboard):
        animatic.start("0123456789ab", "preview")


def test_one_storyboard_cannot_be_rendered_twice_at_once(root):
    sb = make_board([scene("red")])
    run = animatic.start(sb.id, "preview")
    try:
        with pytest.raises(animatic.Busy):
            animatic.start(sb.id, "preview")
    finally:
        run()
    assert not pipeline.heavy_job_lock.locked() and not animatic._cancel and animatic.status(store.load(sb.id))["state"] == "done"


def test_a_cancelled_render_leaves_no_file_and_frees_the_slot(root, monkeypatch):
    sb = make_board([scene("red", 3.0)])
    real, count = animatic.compose, {"n": 0}

    def compose_then_cancel(*a, **k):
        count["n"] += 1
        if count["n"] == 10:
            animatic.cancel(sb.id)
        return real(*a, **k)
    monkeypatch.setattr(animatic, "compose", compose_then_cancel)
    status = run_render(sb.id)
    folder = store.folder(sb.id)
    assert status["state"] == "cancelled" and count["n"] < 75
    assert not (folder / "animatic.mp4").exists() and not (folder / "animatic.partial.mp4").exists()
    assert not pipeline.heavy_job_lock.locked()


def test_starting_a_new_render_removes_the_old_video_so_the_status_never_describes_a_file_that_is_gone(root, monkeypatch):
    sb = make_board([scene("red"), scene("green")])
    run_render(sb.id)
    video = store.folder(sb.id) / "animatic.mp4"
    assert video.exists()
    run = animatic.start(sb.id, "preview")
    assert not video.exists() and animatic.status(store.load(sb.id))["state"] == "rendering"
    animatic.cancel(sb.id)
    run()
    assert animatic.status(store.load(sb.id))["state"] == "cancelled" and not video.exists()


def test_a_failing_encoder_gives_a_readable_error_and_no_file(root, monkeypatch):
    monkeypatch.setattr(animatic, "_encoder", lambda out, size, quality: subprocess.Popen(
        ["sh", "-c", "cat > /dev/null; echo broken >&2; exit 3"], stdin=subprocess.PIPE, stderr=subprocess.PIPE))
    sb = make_board([scene("red")])
    status = run_render(sb.id)
    assert status["state"] == "error" and "could not be encoded" in status["error"] and "broken" in status["error"]
    assert not (store.folder(sb.id) / "animatic.mp4").exists() and not pipeline.heavy_job_lock.locked()


def test_a_render_stops_by_itself_when_memory_runs_out(root, monkeypatch):
    sb = make_board([scene("red", 3.0)])
    monkeypatch.setattr(animatic, "CHECK_EVERY", 5)
    levels = iter([1, 1, 4, 4, 4])
    monkeypatch.setattr(animatic, "_pressure", lambda: next(levels, 4))
    monkeypatch.setattr(animatic, "trouble", lambda folder: None)
    status = run_render(sb.id)
    assert status["state"] == "error" and "ran short of memory" in status["error"]
    assert not (store.folder(sb.id) / "animatic.partial.mp4").exists()


def test_a_render_that_was_interrupted_by_a_restart_is_reported_as_such(root):
    sb = make_board([scene("red")])
    animatic._write(sb.id, state="rendering", progress=0.4, quality="preview")        # nothing is running it
    status = animatic.status(store.load(sb.id))
    assert status["state"] == "error" and "interrupted" in status["error"]


# ================================================================== the API

@pytest.fixture
def client(root):
    with TestClient(main.app) as c:
        yield c


def board(client, **form):
    return client.post("/api/storyboards", files={"photo": ("p.png", quadrant_photo(), "image/png")},
                       data={"prompt": "a macro and a close-up", "count": "3", "rights": "own", **form}).json()


def test_start_then_status_then_watch_the_video(client):
    sb = board(client)
    assert client.get(f"/api/storyboards/{sb['id']}/animatic").json() == {"state": "none"}
    r = client.post(f"/api/storyboards/{sb['id']}/animatic", json={})
    assert r.status_code == 200 and r.json()["state"] in ("rendering", "done")
    done = client.get(f"/api/storyboards/{sb['id']}/animatic").json()
    assert done["state"] == "done" and done["quality"] == "preview" and done["stale"] is False and done["bytes"] > 0
    video = client.get(f"/api/storyboards/{sb['id']}/animatic.mp4")
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4" and video.content[4:8] == b"ftyp"


def test_the_video_can_be_played_part_by_part_so_the_page_can_skip_around(client):
    sb = board(client)
    client.post(f"/api/storyboards/{sb['id']}/animatic", json={"quality": "preview"})
    part = client.get(f"/api/storyboards/{sb['id']}/animatic.mp4", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100


def test_bad_start_requests_are_refused(client):
    sb = board(client)
    assert client.post(f"/api/storyboards/{sb['id']}/animatic", json={"quality": "ultra"}).status_code == 400
    with pipeline.heavy_job_lock:
        r = client.post(f"/api/storyboards/{sb['id']}/animatic", json={})
    assert r.status_code == 409 and "busy" in r.json()["detail"]


def test_playing_is_always_allowed_but_downloading_follows_the_rights_rule(client):
    sb = board(client, rights="unsure")
    client.post(f"/api/storyboards/{sb['id']}/animatic", json={})
    assert client.get(f"/api/storyboards/{sb['id']}/animatic.mp4").status_code == 200          # watching in the page
    blocked = client.get(f"/api/storyboards/{sb['id']}/animatic.mp4?download=1")
    assert blocked.status_code == 409 and "right to use" in blocked.json()["detail"]
    sb.update(rights="own")
    client.put(f"/api/storyboards/{sb['id']}", json=sb)
    ok = client.get(f"/api/storyboards/{sb['id']}/animatic.mp4?download=1")
    assert ok.status_code == 200 and "attachment" in ok.headers["content-disposition"]


def test_editing_the_scenes_marks_the_video_out_of_date(client):
    sb = board(client)
    client.post(f"/api/storyboards/{sb['id']}/animatic", json={})
    sb["scenes"][0]["duration"] = 6
    client.put(f"/api/storyboards/{sb['id']}", json=sb)
    assert client.get(f"/api/storyboards/{sb['id']}/animatic").json()["stale"] is True


def test_there_is_nothing_to_watch_before_a_render(client):
    sb = board(client)
    assert client.get(f"/api/storyboards/{sb['id']}/animatic.mp4").status_code == 404


def test_cancel_is_harmless_when_nothing_is_running(client):
    sb = board(client)
    assert client.post(f"/api/storyboards/{sb['id']}/animatic/cancel").json() == {"state": "none"}


def test_unknown_storyboards_are_404_for_every_animatic_route(client):
    sid = "0123456789ab"
    assert client.get(f"/api/storyboards/{sid}/animatic").status_code == 404
    assert client.post(f"/api/storyboards/{sid}/animatic", json={}).status_code == 404
    assert client.post(f"/api/storyboards/{sid}/animatic/cancel").status_code == 404
    assert client.get(f"/api/storyboards/{sid}/animatic.mp4").status_code == 404


def test_deleting_a_storyboard_stops_its_render_first_and_leaves_nothing(client, root, monkeypatch):
    sb = board(client)
    real = animatic.compose
    monkeypatch.setattr(animatic, "compose", lambda *a, **k: (time.sleep(0.02), real(*a, **k))[1])
    run = animatic.start(sb["id"], "preview")
    worker = threading.Thread(target=run)
    worker.start()
    time.sleep(0.2)
    assert animatic._cancel                                                  # it is rendering
    assert client.delete(f"/api/storyboards/{sb['id']}").json() == {"deleted": sb["id"]}
    worker.join(timeout=15)
    assert not worker.is_alive() and not (root / sb["id"]).exists()
    assert not pipeline.heavy_job_lock.locked() and not animatic._cancel


def test_the_shorts_routes_are_unaffected(client):
    assert client.get("/api/health").status_code == 200 and client.get("/api/caption-presets").status_code == 200


# ================================================================== music

import re

from app import music


def make_tone_track(title="Test Tone", licence="cc0", attribution="", seconds=2.0, name="tone.wav"):
    out = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                          "-ar", "44100", "-ac", "2", "-f", "wav", "-"], capture_output=True, check=True).stdout
    return music.add_track(out, name, title, ["other"], licence, attribution, "made for a test")


def with_music(sb, track, volume=0.7):
    raw = model.to_dict(store.load(sb.id))
    raw["music"] = {"track_id": track["id"] if track else None, "volume": volume}
    return store.save(model.parse(raw, photo=sb.photo))


def loudness(path):
    log = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", log)[-1])


def audio_level(path, start, end):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-f", "s16le", "-ac", "1", "-ar", "8000", "-"],
                         capture_output=True, check=True).stdout
    samples = np.frombuffer(raw, np.int16).astype(float) / 32768
    window = samples[int(start * 8000):int(end * 8000)]
    return float(np.sqrt((window ** 2).mean())) if len(window) else 0.0


def streams(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,nb_frames,sample_rate",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return {s["codec_type"]: s for s in json.loads(out)["streams"]}


def three_scenes():
    return [scene("red"), scene("green"), scene("blue", transition="cut")]


def test_music_is_saved_with_the_storyboard_and_defaults_to_none(root):
    sb = make_board(three_scenes())
    assert sb.music == {"track_id": None, "volume": 0.7}
    legacy = model.to_dict(sb)
    del legacy["music"]                                             # a storyboard saved before music existed
    assert model.parse(legacy, photo=sb.photo).music == {"track_id": None, "volume": 0.7}


@pytest.mark.parametrize("bad", [{"track_id": "../etc/passwd"}, {"track_id": "has space"}, {"track_id": 5},
                                 {"track_id": "ok", "volume": 2}, {"track_id": "ok", "volume": -0.1},
                                 {"track_id": "ok", "volume": "loud"}, "a track", ["x"]])
def test_bad_music_settings_are_refused(root, bad):
    sb = make_board(three_scenes())
    raw = model.to_dict(sb)
    raw["music"] = bad
    with pytest.raises(ValueError):
        model.parse(raw, photo=sb.photo)


def test_a_track_is_mixed_in_at_a_sensible_level_with_fades_and_the_picture_untouched(root):
    sb = make_board(three_scenes())
    silent = run_render(sb.id)
    silent_streams = streams(store.folder(sb.id) / "animatic.mp4")
    track = make_tone_track()
    with_music(sb, track, 0.7)
    status = run_render(sb.id)
    path = store.folder(sb.id) / "animatic.mp4"
    assert status["state"] == "done" and status["stale"] is False
    s = streams(path)
    assert s["audio"]["codec_name"] == "aac" and s["video"]["codec_name"] == "h264"
    assert s["audio"]["sample_rate"] == "48000"                          # loudnorm works at 192 kHz inside: bring it back down
    assert s["video"]["nb_frames"] == silent_streams["video"]["nb_frames"] == "75"             # the picture is the same
    assert "audio" not in silent_streams and silent["state"] == "done"
    assert subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True).stderr.strip() == ""
    assert loudness(path) == pytest.approx(animatic.MUSIC_LUFS + 20 * np.log10(0.7), abs=3.0)
    middle = audio_level(path, 1.0, 2.0)
    assert audio_level(path, 0.0, 0.1) < middle * 0.7                      # faded in
    assert audio_level(path, 2.7, 3.0) < middle * 0.5                      # faded out


def test_the_volume_setting_changes_how_loud_it_is(root):
    sb = make_board(three_scenes())
    track = make_tone_track()
    levels = {}
    for volume in (0.3, 1.0):
        with_music(sb, track, volume)
        run_render(sb.id)
        levels[volume] = loudness(store.folder(sb.id) / "animatic.mp4")
    assert 7 < levels[1.0] - levels[0.3] < 13                              # 20*log10(1/0.3) = 10.5 dB


def test_a_short_track_loops_to_fill_a_long_video(root):
    sb = make_board([scene("red", 3.0), scene("green", 3.0)])               # 6 seconds
    with_music(sb, make_tone_track(seconds=1.5), 1.0)                       # a 1.5-second track
    run_render(sb.id)
    path = store.folder(sb.id) / "animatic.mp4"
    assert audio_level(path, 3.0, 4.0) > 0.02 and audio_level(path, 4.2, 4.4) > 0.02      # long after the track ended once
    assert probe(path)["duration"] == pytest.approx(6.0, abs=0.1)


def test_the_status_carries_the_licence_warnings_and_the_credit_line(root):
    sb = make_board(three_scenes())
    credited = make_tone_track("Morning Light", "cc-by", "Ana Rao, example.org/ana", name="a.wav")
    with_music(sb, credited)
    info = run_render(sb.id)["music"]
    assert info["title"] == "Morning Light" and info["license"] == "CC BY (credit the artist)"
    assert "Morning Light" in info["credits"] and "Ana Rao" in info["credits"]
    assert any("credit" in w.lower() for w in info["warnings"])
    unknown = make_tone_track("Mystery", "unknown", name="b.wav")
    with_music(sb, unknown)
    info = run_render(sb.id)["music"]
    assert any("Licence unknown" in w for w in info["warnings"])
    with_music(sb, make_tone_track("Free", "cc0", name="c.wav"))
    assert "no credit required" in run_render(sb.id)["music"]["credits"]


def test_no_music_means_no_sound_track_and_no_music_in_the_status(root):
    sb = make_board(three_scenes())
    status = run_render(sb.id)
    assert status["music"] is None and "audio" not in streams(store.folder(sb.id) / "animatic.mp4")


def test_changing_the_music_or_its_volume_makes_the_video_out_of_date(root):
    sb = make_board(three_scenes())
    one, two = make_tone_track("One", name="1.wav"), make_tone_track("Two", name="2.wav")
    with_music(sb, one, 0.7)
    assert run_render(sb.id)["stale"] is False
    with_music(sb, one, 0.7)
    assert animatic.status(store.load(sb.id))["stale"] is False
    for track, volume in ((one, 0.4), (two, 0.7), (None, 0.7)):
        with_music(sb, track, volume)
        assert animatic.status(store.load(sb.id))["stale"] is True, (track, volume)


def test_a_missing_track_is_refused_before_anything_starts(root):
    sb = make_board(three_scenes())
    track = make_tone_track()
    with_music(sb, track)
    (music.MUSIC_DIR / track["file"]).unlink()                              # the file vanished from the library
    with pytest.raises(ValueError, match="not in your library"):
        animatic.start(sb.id, "preview")
    assert not pipeline.heavy_job_lock.locked() and not animatic._cancel


def test_a_track_that_disappears_after_the_start_is_an_error_not_a_silent_video(root, monkeypatch):
    sb = make_board(three_scenes())
    with_music(sb, make_tone_track())
    run = animatic.start(sb.id, "preview")
    monkeypatch.setattr(music, "get_track", lambda track_id: None)
    run()
    status = animatic.status(store.load(sb.id))
    assert status["state"] == "error" and "not in your library" in status["error"]
    assert not (store.folder(sb.id) / "animatic.mp4").exists() and not pipeline.heavy_job_lock.locked()


def test_a_failed_mix_leaves_no_files_and_says_why(root, monkeypatch):
    sb = make_board(three_scenes())
    with_music(sb, make_tone_track())
    monkeypatch.setattr(animatic, "_mix_music", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("The music could not be added: boom")))
    status = run_render(sb.id)
    folder = store.folder(sb.id)
    assert status["state"] == "error" and "boom" in status["error"]
    assert not list(folder.glob("animatic*.mp4")) and not pipeline.heavy_job_lock.locked()


def test_the_status_says_when_it_is_adding_the_music(root, monkeypatch):
    sb = make_board(three_scenes())
    with_music(sb, make_tone_track())
    seen, real = {}, animatic._mix_music

    def spy(*a, **k):
        seen.update(animatic.status(store.load(sb.id)))
        return real(*a, **k)
    monkeypatch.setattr(animatic, "_mix_music", spy)
    run_render(sb.id)
    assert seen["state"] == "rendering" and seen["phase"] == "music"


def test_the_mixer_runs_gently_and_does_not_touch_the_picture(monkeypatch, root):
    captured = {}
    monkeypatch.setattr(animatic.subprocess, "run", lambda cmd, **k: captured.setdefault("cmd", cmd))
    animatic._mix_music(root / "in.mp4", root / "t.wav", root / "out.mp4", 0.5, 6.0)
    cmd = captured["cmd"]
    assert cmd[:3] == ["nice", "-n", "10"] and cmd[cmd.index("-c:v") + 1] == "copy" and "-stream_loop" in cmd
    assert f"loudnorm=I={animatic.MUSIC_LUFS}" in cmd[cmd.index("-filter_complex") + 1]


def test_the_api_saves_the_choice_rejects_unknown_tracks_and_serves_a_video_with_sound(client):
    sb = board(client)
    track = make_tone_track()
    sb["music"] = {"track_id": "nothere", "volume": 0.5}
    bad = client.put(f"/api/storyboards/{sb['id']}", json=sb)
    assert bad.status_code == 400 and "not in your library" in bad.json()["detail"]
    sb["music"] = {"track_id": track["id"], "volume": 0.5}
    saved = client.put(f"/api/storyboards/{sb['id']}", json=sb).json()
    assert saved["music"] == {"track_id": track["id"], "volume": 0.5}
    sb["music"]["volume"] = 3
    assert client.put(f"/api/storyboards/{sb['id']}", json=sb).status_code == 400
    client.post(f"/api/storyboards/{sb['id']}/animatic", json={})
    done = client.get(f"/api/storyboards/{sb['id']}/animatic").json()
    assert done["state"] == "done" and done["music"]["title"] == "Test Tone"
    video = client.get(f"/api/storyboards/{sb['id']}/animatic.mp4")
    assert video.status_code == 200
    from pathlib import Path
    assert "audio" in streams(Path(store.folder(sb["id"]) / "animatic.mp4"))
