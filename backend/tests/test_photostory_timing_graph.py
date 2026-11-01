"""Tests for scene timing and the FFmpeg commands. Commands are only BUILT here, never run:
the tests would fail loudly if anything tried to start a process."""
import subprocess
from pathlib import Path

import pytest

from app import captions, captionstyles
from app.photostory import graph, manifest as mf, timing


def project(scenes=None, **extra):
    raw = {"id": "0123456789ab", "title": "Test", "scenes": scenes or [
        {"id": "a", "image": "a.jpg", "duration": 4, "motion": "zoom_in", "rights": "own"},
        {"id": "b", "image": "b.jpg", "duration": 5, "motion": "pan_right", "transition": "fade", "rights": "own"},
        {"id": "c", "image": "c.jpg", "duration": 3, "motion": "hold", "transition": "slide_left", "rights": "own"},
    ]}
    raw.update(extra)
    return mf.parse(raw)


@pytest.fixture(autouse=True)
def no_processes(monkeypatch):
    """Prove that building commands never launches anything."""
    def boom(*a, **k):
        raise AssertionError("a process was started")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)


# ================================================================== timing

def test_a_scene_lasts_its_chosen_time_unless_the_narration_is_longer():
    m = project([{"id": "a", "image": "a.jpg", "duration": 4, "rights": "own"},
                 {"id": "b", "image": "b.jpg", "duration": 4, "narration_seconds": 3.0, "rights": "own"},
                 {"id": "c", "image": "c.jpg", "duration": 4, "narration_seconds": 9.0, "rights": "own"}])
    assert timing.durations(m.scenes) == [4.0, 4.0, pytest.approx(9.0 + timing.TAIL_PAD)]


def test_scenes_start_one_after_another_and_the_total_adds_up():
    m = project()
    assert timing.starts(m.scenes) == [0.0, 4.0, 9.0]
    assert timing.total_seconds(m.scenes) == 12.0


def test_overlaps_follow_the_transitions_and_cuts_have_none():
    m = project([{"id": "a", "image": "a.jpg", "duration": 4, "rights": "own"},
                 {"id": "b", "image": "b.jpg", "duration": 4, "transition": "cut", "rights": "own"},
                 {"id": "c", "image": "c.jpg", "duration": 4, "transition": "fade", "transition_seconds": 1.0,
                  "rights": "own"}])
    assert timing.overlaps(m.scenes) == [0.0, 0.0, 1.0]


def test_a_transition_never_swallows_a_short_scene():
    m = project([{"id": "a", "image": "a.jpg", "duration": 1, "rights": "own"},
                 {"id": "b", "image": "b.jpg", "duration": 1, "transition": "fade", "transition_seconds": 2.0,
                  "rights": "own"}])
    assert timing.overlaps(m.scenes)[1] == 0.5          # half of the 1-second scenes, not 2 s


def test_each_clip_is_rendered_long_enough_to_overlap_the_next_scene():
    m = project()
    overlap = timing.overlaps(m.scenes)
    lengths = timing.render_lengths(m.scenes)
    assert lengths == [4 + overlap[1], 5 + overlap[2], 3]
    assert lengths[-1] == 3                              # the last scene has nothing after it


def test_joining_the_clips_gives_exactly_the_total_length():
    for scenes in (None, [{"id": "a", "image": "a.jpg", "duration": 2, "rights": "own"},
                          {"id": "b", "image": "b.jpg", "duration": 3, "transition": "cut", "rights": "own"},
                          {"id": "c", "image": "c.jpg", "duration": 2.5, "narration_seconds": 6, "rights": "own"},
                          {"id": "d", "image": "d.jpg", "duration": 2, "transition": "wipe_left", "rights": "own"}]):
        m = project(scenes)
        lengths, overlap = timing.render_lengths(m.scenes), timing.overlaps(m.scenes)
        joined = lengths[0] + sum(lengths[i] - overlap[i] for i in range(1, len(lengths)))
        assert joined == pytest.approx(timing.total_seconds(m.scenes))


def test_frame_counts_round_and_are_never_zero():
    assert timing.frames(4) == 100 and timing.frames(0.001) == 1 and timing.frames(0.5) == 12 or timing.frames(0.5) == 13


# ---------------------------------------------------------------- caption timing

def test_estimated_caption_times_are_ordered_inside_the_speaking_window_and_flagged():
    words = timing.estimate_word_times("The fort stands above the old city.", 10.0, 5.0)
    assert [w["text"] for w in words] == "The fort stands above the old city.".split()
    assert all(w["estimated"] is True for w in words)
    assert words[0]["start"] == 10.0 and words[-1]["end"] <= 15.0 + 1e-6
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(words, words[1:]))
    assert all(w["end"] > w["start"] for w in words)


def test_longer_words_get_more_time_and_punctuation_adds_a_pause():
    words = timing.estimate_word_times("a extraordinary a", 0, 6)
    assert words[1]["end"] - words[1]["start"] > words[0]["end"] - words[0]["start"]
    paused = timing.estimate_word_times("end. next", 0, 4)
    plain = timing.estimate_word_times("end next", 0, 4)
    assert paused[1]["start"] - paused[0]["end"] > plain[1]["start"] - plain[0]["end"]


def test_no_words_means_no_captions():
    assert timing.estimate_word_times("   ", 0, 5) == []


def test_caption_words_follow_each_scene_on_the_finished_timeline():
    m = project([{"id": "a", "image": "a.jpg", "duration": 4, "narration_text": "First scene words.", "rights": "own"},
                 {"id": "b", "image": "b.jpg", "duration": 5, "rights": "own"},
                 {"id": "c", "image": "c.jpg", "duration": 3, "narration_text": "Last one.", "rights": "own"}])
    words = timing.caption_words(m)
    starts = timing.starts(m.scenes)
    assert [w["text"] for w in words] == ["First", "scene", "words.", "Last", "one."]
    assert words[0]["start"] >= starts[0] and words[2]["end"] <= starts[1]       # first scene's words stay in it
    assert words[3]["start"] >= starts[2]                                       # the silent scene has none


def test_known_narration_length_is_used_instead_of_a_guess():
    m = project([{"id": "a", "image": "a.jpg", "duration": 10, "narration_text": "Hello there friends.",
                  "narration_seconds": 3.0, "rights": "own"}])
    words = timing.caption_words(m)
    assert words[-1]["end"] <= timing.LEAD_IN + 3.0 + 1e-6


def test_the_estimates_fit_the_existing_caption_drawing_code():
    """captions.py draws words with start/end; these estimates must go straight in."""
    m = project([{"id": "a", "image": "a.jpg", "duration": 6, "rights": "own",
                  "narration_text": "The fort stands above the old city and watches the morning."}])
    words = timing.caption_words(m)
    groups = captions.group_words(words, 4)
    assert sum(len(g) for g in groups) == len(words)
    style = captionstyles.resolve("clean")
    line = captions._timeline(groups, timing.total_seconds(m.scenes), style)
    assert sum(secs for _, secs in line) == pytest.approx(timing.total_seconds(m.scenes), abs=0.05)


# ================================================================== commands

def test_a_still_scene_loops_its_picture_and_a_moving_one_uses_zoompan():
    m = project()
    still = graph.scene_command(m.scenes[2], "a.jpg", "out.mp4", 3.0)       # "hold"
    moving = graph.scene_command(m.scenes[0], "a.jpg", "out.mp4", 4.5)      # "zoom_in"
    assert "-loop" in still and "zoompan" not in " ".join(still)
    assert "-loop" not in moving and "zoompan" in " ".join(moving)
    for cmd in (still, moving):
        assert cmd[0] == "ffmpeg" and cmd[-1] == "out.mp4" and "-an" in cmd and "libx264" in cmd
        assert cmd[cmd.index("-t") + 1].endswith(".000") or cmd[cmd.index("-t") + 1].endswith(".500")


def test_a_moving_scene_asks_for_exactly_its_frames_at_full_size():
    m = project()
    cmd = graph.scene_command(m.scenes[0], "a.jpg", "o.mp4", 4.0)
    graph_text = cmd[cmd.index("-filter_complex") + 1]
    assert ":d=100:" in graph_text and "s=1080x1920" in graph_text and "fps=25" in graph_text
    assert f"scale={1080 * graph.UPSCALE}:{1920 * graph.UPSCALE}" in graph_text      # drawn from a bigger picture
    assert graph_text.endswith("[v]")


def test_the_expressions_are_quoted_so_their_commas_are_safe():
    cmd = graph.scene_command(project().scenes[1], "b.jpg", "o.mp4", 5.6)
    text = cmd[cmd.index("-filter_complex") + 1]
    for name in ("z", "x", "y"):
        assert f"{name}='" in text


def test_fill_crops_and_blur_fits_over_a_blurred_copy():
    m = project([{"id": "a", "image": "a.jpg", "duration": 4, "fit": "fill", "rights": "own"},
                 {"id": "b", "image": "b.jpg", "duration": 4, "fit": "blur", "rights": "own"}])
    fill = graph.scene_command(m.scenes[0], "a.jpg", "o.mp4", 4)
    blur = graph.scene_command(m.scenes[1], "b.jpg", "o.mp4", 4)
    assert "boxblur" not in " ".join(fill) and "crop=" in " ".join(fill)
    assert "boxblur" in " ".join(blur) and "overlay=(W-w)/2:(H-h)/2" in " ".join(blur)


def test_every_scene_is_converted_to_the_standard_colour_range_before_the_pixel_format():
    """JPEG photos are full range; without this the video is labelled yuvj420p (some players show it wrongly)."""
    m = project([{"id": "a", "image": "a.jpg", "duration": 4, "motion": "hold", "rights": "own"},
                 {"id": "b", "image": "b.jpg", "duration": 4, "motion": "zoom_in", "rights": "own"},
                 {"id": "c", "image": "c.jpg", "duration": 4, "motion": "pan_up", "fit": "blur", "rights": "own"}])
    for scene in m.scenes:
        for preview in (False, True):
            cmd = graph.scene_command(scene, "x.jpg", "o.mp4", 4.0, preview=preview)
            text = cmd[cmd.index("-filter_complex") + 1]
            assert text.endswith(",scale=out_range=tv,format=yuv420p[v]"), (scene.motion, text[-80:])


def test_a_preview_is_small_and_quick():
    m = project()
    full = graph.scene_command(m.scenes[0], "a.jpg", "o.mp4", 4)
    preview = graph.scene_command(m.scenes[0], "a.jpg", "o.mp4", 4, preview=True)
    assert "s=1080x1920" in " ".join(full) and "s=270x480" in " ".join(preview)
    assert "ultrafast" in preview and "veryfast" in full
    assert graph.canvas(0.25) == (270, 480) and all(n % 2 == 0 for n in graph.canvas(0.333))


def test_the_join_places_each_transition_exactly_where_the_next_scene_starts():
    m = project()
    text = graph.join_graph(m.scenes)
    assert "xfade=transition=fade:duration=0.600:offset=4.000" in text
    assert "xfade=transition=slideleft:duration=0.600:offset=9.000" in text
    assert "[n0][n1]xfade" in text and text.endswith("[v]")
    assert text.count("settb=AVTB") == 3                  # every clip is put on the same timebase first


def test_a_cut_is_a_plain_join_and_every_transition_style_has_a_name():
    m = project([{"id": "a", "image": "a.jpg", "duration": 3, "rights": "own"},
                 {"id": "b", "image": "b.jpg", "duration": 3, "transition": "cut", "rights": "own"},
                 {"id": "c", "image": "c.jpg", "duration": 3, "transition": "wipe_left", "rights": "own"},
                 {"id": "d", "image": "d.jpg", "duration": 3, "transition": "slide_right", "rights": "own"}])
    text = graph.join_graph(m.scenes)
    assert "concat=n=2:v=1:a=0,fps=25,settb=AVTB" in text and "wipeleft" in text and "slideright" in text
    assert set(graph.XFADE) == set(mf.TRANSITIONS) - {"cut"}


def test_one_scene_needs_no_join_and_the_clip_count_must_match():
    one = project([{"id": "a", "image": "a.jpg", "duration": 3, "rights": "own"}])
    assert graph.join_graph(one.scenes) == "[0:v]null[v]"
    with pytest.raises(ValueError, match="one clip per scene"):
        graph.join_command(["a.mp4"], project().scenes, "o.mp4")


def test_narration_is_placed_at_each_scene_start_and_silence_makes_no_command():
    m = project()
    audio = [Path("n1.wav"), None, Path("n3.wav")]
    cmd = graph.narration_command(m.scenes, audio, "n.m4a")
    text = cmd[cmd.index("-filter_complex") + 1]
    assert f"adelay={round(timing.LEAD_IN * 1000)}|" in text                  # scene 1 starts at 0 + a moment
    assert f"adelay={round((9 + timing.LEAD_IN) * 1000)}|" in text            # scene 3 starts at 9 s
    assert "amix=inputs=2" in text and cmd.count("-i") == 2
    assert "apad=whole_dur=12.000" in text                  # padded to the full video length
    assert graph.narration_command(m.scenes, [None, None, None], "n.m4a") is None


def test_the_voice_is_put_on_the_picture_without_re_encoding_either():
    cmd = graph.mux_command("v.mp4", "a.m4a", "o.mp4", 12.0)
    assert cmd[cmd.index("-map"):cmd.index("-map") + 4] == ["-map", "0:v", "-map", "1:a"]
    assert cmd[cmd.index("-c:v") + 1] == "copy" and cmd[cmd.index("-c:a") + 1] == "copy" and cmd[-1] == "o.mp4"


def test_without_narration_the_base_video_is_just_the_joined_scenes(tmp_path):
    plan = graph.build_plan(project(), tmp_path, tmp_path)
    assert plan["base_video"].endswith("story_base.mp4") and plan["narration_audio"] is None
    assert [s["name"] for s in plan["steps"]][-1] == "join scenes"


def test_commands_are_lists_of_text_so_odd_file_names_are_safe():
    m = project()
    cmd = graph.scene_command(m.scenes[0], "/tmp/my photos/été; rm -rf.jpg", "/tmp/o ut.mp4", 4)
    assert all(isinstance(part, str) for part in cmd)
    assert "/tmp/my photos/été; rm -rf.jpg" in cmd             # one single argument, never split or run by a shell


def test_this_package_cannot_start_a_process():
    source = Path(graph.__file__).read_text()
    assert "subprocess" not in source and "os.system" not in source and "Popen" not in source


# ================================================================== the whole plan

def test_the_plan_lists_every_step_from_the_manifest_alone(tmp_path):
    m = project(captions={"on": True, "preset": "clean"}, headline={"text": "A day in Jaipur"},
                music={"track_id": "starter-educational", "volume": 0.4})
    m.scenes[0].narration_text = "The fort stands above the old city."
    plan = graph.build_plan(m, tmp_path / "project", tmp_path / "work")
    assert [s["name"] for s in plan["steps"]] == ["scene 1", "scene 2", "scene 3", "join scenes"]
    assert plan["base_video"].endswith("story_base.mp4") and plan["narration_audio"] is None
    assert plan["total_seconds"] == 12.0 and plan["photos"] == ["a.jpg", "b.jpg", "c.jpg"]
    assert plan["headline"]["text"] == "A day in Jaipur" and plan["music"]["volume"] == 0.4
    assert plan["caption_words"] and plan["caption_preset"] == "clean"
    assert all(isinstance(a, str) for s in plan["steps"] for a in s["argv"])
    assert all(str(tmp_path / "project") in " ".join(s["argv"]) for s in plan["steps"][:3])   # photos come from the project folder


def test_captions_are_only_planned_when_switched_on(tmp_path):
    m = project()
    m.scenes[0].narration_text = "Hello world."
    assert graph.build_plan(m, tmp_path, tmp_path)["caption_words"] == []
    m.captions["on"] = True
    assert graph.build_plan(m, tmp_path, tmp_path)["caption_words"]


def test_narration_adds_a_step_and_a_preview_uses_its_own_files(tmp_path):
    m = project()
    m.scenes[1].narration_audio = "voice.wav"
    m.scenes[1].narration_seconds = 4.0
    plan = graph.build_plan(m, tmp_path / "p", tmp_path / "w")
    assert [s["name"] for s in plan["steps"]][-2:] == ["place narration", "add narration"]
    assert plan["narration_audio"].endswith("narration.m4a") and plan["base_video"].endswith("story_with_voice.mp4")
    preview = graph.build_plan(m, tmp_path / "p", tmp_path / "w", preview=True)
    assert all("preview_" in s["output"] for s in preview["steps"]) and "s=270x480" in " ".join(preview["steps"][0]["argv"])
    assert not set(s["output"] for s in preview["steps"]) & set(s["output"] for s in plan["steps"])


def test_the_plan_changes_when_the_manifest_changes(tmp_path):
    a = project()
    b = project()
    b.scenes[1].motion, b.scenes[1].intensity, b.scenes[1].duration = "zoom_out", 1.0, 8.0
    pa, pb = graph.build_plan(a, tmp_path, tmp_path), graph.build_plan(b, tmp_path, tmp_path)
    assert pa["steps"][1]["argv"] != pb["steps"][1]["argv"] and pa["total_seconds"] != pb["total_seconds"]
    assert pa["steps"][0]["argv"] == pb["steps"][0]["argv"]            # the untouched scene is identical
