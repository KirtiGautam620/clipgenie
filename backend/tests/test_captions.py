import subprocess

import numpy as np
import pytest

from app import captions, captionstyles, export
from app.captions import MAX_WORDS_PER_GROUP, make_groups
from app.captionstyles import resolve


def w(text, start, end):
    return {"word": " " + text, "start": start, "end": end}


def test_groups_are_relative_to_clip_start():
    groups = make_groups([w("hello", 10.0, 10.4), w("world", 10.5, 11.0)], 10.0, 12.0)
    assert groups[0][0]["start"] == 0.0 and groups[0][1]["end"] == 1.0


def test_group_size_limit_and_punctuation_break():
    words = [w(f"w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(9)]
    assert all(len(g) <= MAX_WORDS_PER_GROUP for g in make_groups(words, 0, 5))
    words = [w("Hi.", 0, 0.3), w("there", 0.4, 0.7), w("you", 0.8, 1.0)]
    assert [len(g) for g in make_groups(words, 0, 2)] == [1, 2]   # break after the full stop


def test_long_pause_starts_a_new_group():
    groups = make_groups([w("a", 0, 0.2), w("b", 2.0, 2.2)], 0, 3)
    assert len(groups) == 2


def test_words_outside_the_clip_are_ignored_and_hindi_is_kept():
    words = [w("before", 1, 2), w("नमस्ते", 5, 5.5), w("after", 9, 10)]
    groups = make_groups(words, 4.0, 8.0)
    assert [x["text"] for g in groups for x in g] == ["नमस्ते"]


def test_a_word_with_a_silly_long_duration_is_capped():
    """Whisper sometimes gives one word a 13-second duration. It must not hold the screen."""
    cap = captions.words_in_clip([w("hello", 0.0, 13.0), w("there", 13.1, 13.5)], 0.0, 14.0)
    assert cap[0]["end"] == captions.MAX_WORD_SECONDS
    timeline = captions._timeline(captions.group_words(cap), 14.0, resolve("clean"))
    assert max(secs for key, secs in timeline if key and key[1] >= 0) <= captions.MAX_WORD_SECONDS + captions.HOLD + 1e-6
    assert any(key is None and secs > 5 for key, secs in timeline)   # and the long silence is blank


# ---------------------------------------------------------------- timeline

def _cap(n=6, step=0.5):
    return [{"text": f"w{i}", "start": i * step, "end": i * step + 0.4} for i in range(n)]


def test_timeline_covers_the_whole_clip():
    for preset in captionstyles.PRESETS:
        style = resolve(preset)
        groups = captions.group_words(_cap(), style.words_per_line)
        assert sum(s for _, s in captions._timeline(groups, 4.0, style)) == pytest.approx(4.0, abs=0.05)


def test_no_animation_shows_each_line_steadily():
    style = resolve("subtitle")
    groups = captions.group_words(_cap(), style.words_per_line)
    keys = [k for k, _ in captions._timeline(groups, 4.0, style) if k]
    assert all(active == -1 for _, active, _ in keys)
    assert len(keys) == len(groups)


def test_pop_animation_enlarges_then_settles():
    style = resolve("bold_pop")
    groups = captions.group_words(_cap(2), style.words_per_line)
    scales = [k[2] for k, _ in captions._timeline(groups, 3.0, style) if k and k[1] == 0]
    assert scales[:4] == list(captions.POP_SCALES) and scales[-1] == captions.POP_HOLD


def test_highlight_follows_the_spoken_word():
    style = resolve("clean")
    groups = captions.group_words(_cap(3), style.words_per_line)
    actives = [k[1] for k, _ in captions._timeline(groups, 3.0, style) if k and k[1] >= 0]
    assert actives == sorted(actives) and set(actives) == {0, 1, 2}


# ---------------------------------------------------------------- drawing

def _colours(img, rgb, tol=40):
    a = np.asarray(img)
    near = (np.abs(a[..., :3].astype(int) - rgb).max(axis=2) < tol) & (a[..., 3] > 200)
    return int(near.sum())


def test_frames_are_transparent_and_use_the_style_colours():
    style = resolve("clean")
    img = captions._render_frame(["Hello", "brave", "world"], 1, 1.0, style)
    assert img.size == (captions.CANVAS_W, captions.CANVAS_H)
    assert img.getbbox() is not None
    assert np.asarray(img)[0, 0, 3] == 0                          # the corner is see-through
    assert _colours(img, (255, 184, 77)) > 300                    # the spoken word is amber
    assert _colours(img, (255, 255, 255)) > 300                   # the others are white


def test_pill_preset_draws_a_pill_behind_the_spoken_word():
    img = captions._render_frame(["Hello", "world"], 0, 1.0, resolve("pill"))
    assert _colours(img, (255, 184, 77)) > 3000                   # a big filled shape


def test_bar_preset_draws_a_dark_bar_behind_the_line():
    img = captions._render_frame(["Hello", "world"], -1, 1.0, resolve("subtitle"))
    a = np.asarray(img)
    assert (a[..., 3] > 100).sum() > 20000 and a[..., :3][a[..., 3] > 100].min() < 40


def test_presets_look_different():
    frames = {p: np.asarray(captions._render_frame(["Hello", "world"], 0, 1.0, resolve(p)))
              for p in captionstyles.PRESETS}
    names = list(frames)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert not np.array_equal(frames[a], frames[b]), (a, b)


def test_uppercase_changes_what_is_drawn():
    assert captions.display_text("hello", resolve("bold_pop")) == "HELLO"
    assert captions.display_text("नमस्ते", resolve("bold_pop")) == "नमस्ते"


def test_hindi_is_drawn_with_the_bundled_font():
    img = captions._render_frame(["नमस्ते", "दोस्तों"], 0, 1.0, resolve("clean"))
    assert _colours(img, (255, 184, 77)) > 500 and _colours(img, (255, 255, 255)) > 500


def test_long_text_shrinks_instead_of_overflowing():
    style = resolve("bold_pop")
    long = ("Supercalifragilisticexpialidocious " * 3).split()
    lay = captions._layout(tuple(captions.display_text(t, style) for t in long), style)
    assert lay.size < style.size
    assert lay.bounds[0] >= 0 and lay.bounds[2] <= captions.CANVAS_W
    one = captions._layout(("नमस्ते", "hi"), style)
    assert one.size == style.size                                  # short text keeps its size


def test_strip_stays_on_the_video():
    assert 0 <= captions.strip_y(resolve("clean", {"position": 78})) <= 1920 - captions.CANVAS_H
    assert captions.strip_y(resolve("clean")) == round(0.66 * 1920 - captions.CANVAS_H / 2)


# ---------------------------------------------------------------- the real video

def _make_video(path, seconds=4):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size=1280x720:rate=25:d={seconds}", "-f", "lavfi", "-i",
                    f"sine=f=300:d={seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(path)], check=True)


def _frame(path, t):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(path),
                          "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(1920, 1080, 3).astype(int)


def test_export_makes_a_base_and_a_captioned_clip(tmp_path):
    src, out = tmp_path / "in.mp4", tmp_path / "clip_1.mp4"
    _make_video(src)
    words = [w("hello", 0.5, 1.0), w("brave", 1.1, 1.6), w("world", 1.7, 2.3)]
    export.export_clip(src, words, 0, 4, out, tmp_path, "crop", style=resolve("clean"))
    base = export.base_path(out)
    assert base.exists() and out.exists()
    y = captions.strip_y(resolve("clean"))
    with_caps, without = _frame(out, 1.3)[y:y + 420], _frame(base, 1.3)[y:y + 420]
    assert np.abs(with_caps - without).mean() > 1            # the captions are really on the picture
    quiet = np.abs(_frame(out, 3.6) - _frame(base, 3.6)).mean()
    assert quiet < 1                                          # and gone again after the last word


def test_restyling_only_redraws_the_captions(tmp_path):
    src, out = tmp_path / "in.mp4", tmp_path / "clip_1.mp4"
    _make_video(src)
    words = [w("hello", 0.5, 1.0), w("brave", 1.1, 1.6), w("world", 1.7, 2.3)]
    export.export_clip(src, words, 0, 4, out, tmp_path, "crop", style=resolve("clean"))
    first = _frame(out, 1.3)
    cap = captions.words_in_clip(words, 0, 4)
    export.apply_captions(export.base_path(out), cap, resolve("bold_pop"), out, tmp_path)
    assert np.abs(_frame(out, 1.3) - first).mean() > 0.5


def test_edited_words_are_what_gets_drawn(tmp_path):
    src, out = tmp_path / "in.mp4", tmp_path / "clip_1.mp4"
    _make_video(src)
    cap = [{"text": "hello", "start": 0.5, "end": 1.0}]
    export.export_clip(src, [], 0, 4, out, tmp_path, "crop", cap_words=cap)
    before = _frame(out, 0.8)
    cap[0]["text"] = "goodbye"
    export.apply_captions(export.base_path(out), cap, resolve(), out, tmp_path)
    assert np.abs(_frame(out, 0.8) - before).mean() > 0.3


def test_no_speech_means_no_captions_but_still_a_clip(tmp_path):
    src, out = tmp_path / "in.mp4", tmp_path / "clip_1.mp4"
    _make_video(src, 2)
    export.export_clip(src, [], 0, 2, out, tmp_path, "crop")
    assert out.exists() and not list(tmp_path.glob("*_captions.mov"))


def test_neighbouring_words_never_touch():
    for preset in ("pill", "bold_pop", "clean"):
        style = resolve(preset)
        items = captions._layout(("नमस्ते", "दोस्तों", "आज"), style).items
        assert all(b[1] - (a[1] + a[3]) >= 8 for a, b in zip(items, items[1:])), preset
