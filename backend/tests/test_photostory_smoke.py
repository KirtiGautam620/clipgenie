"""Tiny REAL renders of the Photo Story commands: 108 x 192 pixels, about 2 seconds of video in all,
FFmpeg only. They take well under a second and a few tens of MB, like the other small video tests.
They prove FFmpeg accepts the commands and that the output has the right shape and colour range;
they say nothing about how good a full-size video looks."""
import json
import shutil
import subprocess

import pytest
from PIL import Image, ImageDraw

from app.photostory import graph, ingest, manifest as mf

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")


@pytest.fixture(autouse=True)
def tiny_canvas(monkeypatch):
    monkeypatch.setattr(graph, "PREVIEW_SCALE", 0.1)           # 108 x 192


def make_project(tmp_path):
    project, work = tmp_path / "project", tmp_path / "work"
    project.mkdir()
    work.mkdir()
    for name, (base, accent) in {"a": ((30, 90, 160), (250, 200, 40)), "b": ((150, 40, 60), (240, 240, 240))}.items():
        img = Image.new("RGB", (480, 320), base)
        d = ImageDraw.Draw(img)
        d.ellipse([170, 90, 310, 230], fill=accent)
        img.save(tmp_path / f"{name}.png")
        ingest.normalize_image(tmp_path / f"{name}.png", project / f"{name}.jpg")     # the real intake path
    return project, work


def render(tmp_path, scenes):
    project, work = make_project(tmp_path)
    m = mf.parse({"id": "0123456789ab", "title": "Smoke", "scenes": scenes})
    plan = graph.build_plan(m, project, work, preview=True)
    for step in plan["steps"]:
        subprocess.run(step["argv"], check=True, capture_output=True)
    return plan, work


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,pix_fmt,color_range,nb_frames:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    return {**video, "duration": float(data["format"]["duration"]),
            "audio": sum(s["codec_type"] == "audio" for s in data["streams"])}


def test_a_still_scene_and_a_moving_blur_fit_scene_render_and_join_in_standard_video_format(tmp_path):
    plan, work = render(tmp_path, [
        {"id": "one", "image": "a.jpg", "duration": 1, "motion": "hold", "rights": "own"},           # the still path
        {"id": "two", "image": "b.jpg", "duration": 1, "motion": "pan_left", "intensity": 0.8,     # the moving path
         "fit": "blur", "transition": "fade", "transition_seconds": 0.5, "rights": "own"}])
    for step in plan["steps"]:
        info = probe(step["output"])
        assert (info["codec_name"], info["width"], info["height"]) == ("h264", 108, 192), step["name"]
        assert info["pix_fmt"] == "yuv420p" and info["color_range"] == "tv", (step["name"], info["pix_fmt"])
        assert info["audio"] == 0
    joined = probe(plan["base_video"])
    assert joined["nb_frames"] == "50" and joined["duration"] == pytest.approx(2.0, abs=0.05)
    decode = subprocess.run(["ffmpeg", "-v", "error", "-i", plan["base_video"], "-f", "null", "-"],
                            capture_output=True, text=True)
    assert decode.stderr.strip() == ""


def test_a_moving_scene_really_moves_and_the_picture_is_not_blank(tmp_path):
    import numpy as np
    plan, _ = render(tmp_path, [{"id": "one", "image": "a.jpg", "duration": 1, "motion": "zoom_in",
                                 "intensity": 1.0, "rights": "own"}])

    def frame(t):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", plan["base_video"], "-frames:v", "1",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        return np.frombuffer(raw, np.uint8).reshape(192, 108, 3).astype(float)
    first, last = frame(0.0), frame(0.9)
    assert float(np.abs(first - last).mean()) > 5            # the picture changed: it zoomed
    assert first.std() > 10                                  # and it is not a flat colour


# ================================================================== every transition, and narration

PALETTE = {"red": (230, 40, 40), "green": (40, 200, 60), "blue": (40, 70, 230),
           "yellow": (240, 220, 40), "purple": (150, 50, 200), "cyan": (40, 210, 220)}


def solid_project(tmp_path, names):
    project, work = tmp_path / "project", tmp_path / "work"
    project.mkdir()
    work.mkdir()
    for name in names:
        Image.new("RGB", (200, 300), PALETTE[name]).save(project / f"{name}.jpg", quality=95)
    return project, work


def decode_frames(path):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 192, 108, 3).astype(float)


def nearest(color):
    """The palette colour closest to this one, and how far away it is."""
    import numpy as np
    best = min(PALETTE, key=lambda n: float(np.linalg.norm(np.array(PALETTE[n]) - color)))
    return best, float(np.linalg.norm(np.array(PALETTE[best]) - color))


def halves(frame):
    """The dominant colour on the left and on the right of the picture."""
    return nearest(frame[60:130, 8:36].mean(axis=(0, 1)))[0], nearest(frame[60:130, 72:100].mean(axis=(0, 1)))[0]


def test_every_kind_of_join_renders_and_looks_like_what_it_says(tmp_path):
    order = ["red", "green", "blue", "yellow", "purple", "cyan"]
    project, work = solid_project(tmp_path, order)
    kinds = [None, "cut", "slide_left", "slide_right", "wipe_left", "fade"]
    scenes = []
    for name, kind in zip(order, kinds):
        scene = {"id": name, "image": f"{name}.jpg", "duration": 1, "motion": "hold", "rights": "own"}
        if kind:
            scene.update(transition=kind, transition_seconds=0.5)
        scenes.append(scene)
    m = mf.parse({"id": "0123456789ab", "title": "Joins", "scenes": scenes})
    plan = graph.build_plan(m, project, work, preview=True)
    for step in plan["steps"]:
        subprocess.run(step["argv"], check=True, capture_output=True)

    info = probe(plan["base_video"])
    assert info["nb_frames"] == "150" and info["duration"] == pytest.approx(6.0, abs=0.05)     # cuts and overlaps add up
    assert info["pix_fmt"] == "yuv420p" and info["color_range"] == "tv" and info["audio"] == 0
    frames = decode_frames(plan["base_video"])
    at = lambda t: frames[min(len(frames) - 1, round(t * 25))]

    # between transitions each scene shows its own clean colour
    for t, name in [(0.5, "red"), (1.5, "green"), (2.75, "blue"), (3.75, "yellow"), (4.75, "purple"), (5.75, "cyan")]:
        got, distance = nearest(at(t).mean(axis=(0, 1)))
        assert got == name and distance < 40, (t, got, distance)

    # a cut is instant: no blended frame at any moment around it
    for t in (0.88, 0.92, 0.96, 1.0, 1.04, 1.08, 1.12):
        got, distance = nearest(at(t).mean(axis=(0, 1)))
        assert got in ("red", "green") and distance < 40, (t, got, distance)
    assert nearest(at(0.92).mean(axis=(0, 1)))[0] == "red" and nearest(at(1.08).mean(axis=(0, 1)))[0] == "green"

    # slides and wipes show BOTH pictures side by side half way through; the two slide directions mirror each other
    left_a, right_a = halves(at(2.25))            # slide_left: green -> blue
    left_b, right_b = halves(at(3.25))            # slide_right: blue -> yellow
    left_c, right_c = halves(at(4.25))            # wipe_left: yellow -> purple
    assert {left_a, right_a} == {"green", "blue"} and {left_b, right_b} == {"blue", "yellow"}
    assert {left_c, right_c} == {"yellow", "purple"}
    assert (left_a == "green") != (left_b == "blue"), "slide_left and slide_right should go opposite ways"

    # a fade blends the two over the whole picture: not either clean colour
    import numpy as np
    mixed = at(5.25).mean(axis=(0, 1))
    assert nearest(mixed)[1] > 40                                                       # neither clean colour
    halfway = (np.array(PALETTE["purple"]) + np.array(PALETTE["cyan"])) / 2
    assert float(np.linalg.norm(mixed - halfway)) < 50                                  # but a mix of the two


def tone(path, seconds):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-ar", "16000", "-ac", "1", str(path)], check=True)


def audio_level(path, start, end):
    """Loudness (RMS, 0..1) of a stretch of an audio file."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", "8000", "-"],
                         capture_output=True, check=True).stdout
    samples = np.frombuffer(raw, np.int16).astype(float) / 32768
    window = samples[int(start * 8000):int(end * 8000)]
    return float(np.sqrt((window ** 2).mean())) if len(window) else 0.0


def audio_seconds(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(path)], capture_output=True, text=True, check=True).stdout)


def test_narration_is_placed_on_the_timeline_and_makes_scenes_long_enough_for_it(tmp_path):
    project, work = solid_project(tmp_path, ["red", "green", "blue"])
    tone(project / "one.wav", 1.2)                   # longer than its 1-second scene
    tone(project / "three.wav", 0.8)
    scenes = [
        {"id": "a", "image": "red.jpg", "duration": 1, "motion": "hold", "narration_audio": "one.wav",
         "narration_seconds": audio_seconds(project / "one.wav"), "narration_text": "Hello there.", "rights": "own"},
        {"id": "b", "image": "green.jpg", "duration": 1, "motion": "hold", "rights": "own"},
        {"id": "c", "image": "blue.jpg", "duration": 1, "motion": "hold", "narration_audio": "three.wav",
         "narration_seconds": audio_seconds(project / "three.wav"), "transition": "fade", "transition_seconds": 0.5,
         "rights": "own"}]
    m = mf.parse({"id": "0123456789ab", "title": "Voice", "scenes": scenes, "captions": {"on": True}})
    plan = graph.build_plan(m, project, work, preview=True)
    assert [s["name"] for s in plan["steps"]][-2:] == ["place narration", "add narration"]
    for step in plan["steps"]:
        subprocess.run(step["argv"], check=True, capture_output=True)

    # scene 1 was stretched to hold its 1.2 s of speech plus a pause; the video is as long as the plan says
    total = plan["total_seconds"]
    assert total == pytest.approx(1.2 + 0.4 + 1 + 1.2, abs=0.01)
    narration = plan["narration_audio"]
    assert audio_seconds(narration) == pytest.approx(total, abs=0.1)        # padded: as long as the video

    # the voiced base video has the picture AND the sound, both the planned length
    voiced = probe(plan["base_video"])
    assert voiced["duration"] == pytest.approx(total, abs=0.1) and voiced["audio"] == 1
    assert probe(work / "preview_story_base.mp4")["audio"] == 0               # the plain join stays silent

    # the first voice is heard at the start, the gap is silent, the second voice arrives with scene 3
    assert audio_level(plan["base_video"], 0.3, 1.2) > 0.05                   # scene 1's narration
    assert audio_level(plan["base_video"], 1.7, 2.5) < 0.01                   # scene 2 has none
    assert audio_level(plan["base_video"], 2.9, 3.3) > 0.05                   # scene 3's narration
    assert audio_level(plan["base_video"], 3.65, 3.75) < 0.01                 # then silence to the end
    assert plan["caption_words"] and plan["caption_words"][-1]["end"] <= 1.6    # captions stay inside scene 1


def test_narration_for_a_single_scene_also_renders(tmp_path):
    project, work = solid_project(tmp_path, ["red"])
    tone(project / "solo.wav", 0.9)
    m = mf.parse({"id": "0123456789ab", "title": "Solo", "scenes": [
        {"id": "a", "image": "red.jpg", "duration": 1, "motion": "hold", "narration_audio": "solo.wav",
         "narration_seconds": 0.9, "rights": "own"}]})
    plan = graph.build_plan(m, project, work, preview=True)
    for step in plan["steps"]:
        subprocess.run(step["argv"], check=True, capture_output=True)
    assert audio_level(plan["base_video"], 0.3, 0.9) > 0.05
    assert probe(plan["base_video"])["audio"] == 1
