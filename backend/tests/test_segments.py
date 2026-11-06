"""Timeline segments: the kept parts of a clip. Removing the gaps (pauses) in one pass, with the
captions moving to match. Media is a 6 s synthetic source whose picture is black on even seconds
and white on odd ones, so what was kept can be read straight from the pictures."""
import copy
import json
import subprocess

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import main, manifest, render
from tests.test_render import clip_entry, duration_of, luma_at, rms_at, frames  # noqa: F401  (helpers)

pytestmark = pytest.mark.usefixtures("folders")


def striped_source(path, seconds=6):
    """Black on even seconds, white on odd seconds, with a steady tone."""
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"color=c=white:s=1280x720:r=25:d={seconds}", "-f", "lavfi", "-i",
                    f"sine=frequency=440:duration={seconds}", "-vf", r"geq=lum='255*mod(floor(T)\,2)':cb=128:cr=128",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)


def make_striped_job(work, segments=None, words=None):
    folder = work / "abcdef0123"
    folder.mkdir()
    (folder / "status.json").write_text(json.dumps({"status": "done"}))
    (folder / "provenance.json").write_text(json.dumps({"rights": "own", "url": None, "title": "", "uploader": ""}))
    striped_source(folder / "source.mp4")
    clip = clip_entry(cut={"cut_start": 0.0, "cut_end": 6.0}, end=6.0, duration=6.0)
    if words is not None:
        clip["captions"]["words"] = words
    m = manifest.validate(manifest.from_clip(clip))
    if segments:
        m["segments"] = [{"start": a, "end": b} for a, b in segments]
        m = manifest.validate(m)
    result = render.create(folder, 1, m)
    manifest.save(folder, 1, m)
    from app import pipeline
    pipeline._sync_clip(clip, m, m, result)
    (folder / "clips.json").write_text(json.dumps({"status": "done", "note": "ok", "clips": [clip]}))
    return "abcdef0123", folder, m


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


# ---------------------------------------------------------------- the manifest

def base():
    return manifest.default_manifest(0.0, 10.0)


def test_version_1_manifests_are_read_and_upgraded():
    old = base()
    old["version"] = 1
    del old["segments"]
    m = manifest.validate(old)
    assert m["version"] == 2 and m["segments"] == [{"start": 0.0, "end": 10.0}]
    assert manifest.is_cut(m) is False and manifest.output_length(m) == 10.0


def test_segments_are_cut_to_the_range_sorted_and_summed():
    doc = base()
    doc["clip"] = {"start": 2.0, "end": 8.0}
    doc["segments"] = [{"start": 6.0, "end": 9.5}, {"start": 0.0, "end": 3.0}]       # out of order, past the ends
    m = manifest.validate(doc)
    assert m["segments"] == [{"start": 2.0, "end": 3.0}, {"start": 6.0, "end": 8.0}]
    assert manifest.output_length(m) == 3.0 and manifest.is_cut(m)


@pytest.mark.parametrize("segments, message", [
    ([], "at least one"),
    ([{"start": 1, "end": 5}, {"start": 4, "end": 8}], "overlap"),
    ([{"start": 20, "end": 30}], "inside the video"),
    ([{"start": 1, "end": 1.5}], "at least"),                                       # kept parts add up to 0.5 s
    ("nope", "list"),
    ([{"start": "a", "end": 2}], "number"),
])
def test_bad_segments_are_refused(segments, message):
    doc = base()
    doc["segments"] = segments
    with pytest.raises(ValueError, match=message):
        manifest.validate(doc)


def test_fades_are_judged_against_the_kept_length():
    doc = base()
    doc["segments"] = [{"start": 0, "end": 1.5}, {"start": 5, "end": 6.5}]            # 3 s kept of 10
    doc["fades"] = {"in": 1.6, "out": 1.6}
    with pytest.raises(ValueError, match="longer than the video"):
        manifest.validate(doc)


def test_caption_words_move_earlier_by_the_time_removed_and_cut_words_are_dropped():
    doc = base()
    doc["segments"] = [{"start": 0.0, "end": 2.0}, {"start": 4.0, "end": 6.0}]       # 2 s gap, 4 s kept
    m = manifest.validate(doc)
    words = [{"text": "a", "start": 0.5, "end": 1.0},      # in the first part
             {"text": "gap", "start": 2.5, "end": 3.0},    # in the removed gap
             {"text": "b", "start": 4.5, "end": 5.0},      # in the second part: moves 2 s earlier
             {"text": "half", "start": 1.8, "end": 2.3}]   # straddles the cut
    out = manifest.remap_words(words, m)
    assert [(w["text"], w["start"], w["end"]) for w in out] == [("a", 0.5, 1.0), ("b", 2.5, 3.0)]
    assert manifest.remap_words(words, manifest.validate(base())) == words          # nothing removed: untouched


def test_the_drawer_spec_uses_the_time_of_the_finished_video():
    doc = base()
    doc["text"] = {"mode": "captions", "headline": None,
                   "captions": {"style": {}, "words": [{"text": "b", "start": 4.5, "end": 5.0}]}}
    doc["segments"] = [{"start": 0.0, "end": 2.0}, {"start": 4.0, "end": 6.0}]
    spec = manifest.text_drawer_spec(doc)
    assert spec["words"][0]["start"] == 2.5


def test_render_args_only_pass_segments_when_something_is_removed():
    assert manifest.render_args(base())["segments"] is None
    doc = base()
    doc["segments"] = [{"start": 0, "end": 4}, {"start": 6, "end": 10}]
    assert manifest.render_args(doc)["segments"] == [(0.0, 4.0), (6.0, 10.0)]


# ---------------------------------------------------------------- the render

def test_the_removed_parts_are_really_gone_picture_and_sound(folders):
    # keep the white seconds only: (1-2), (3-4), (5-6)
    job, folder, m = make_striped_job(folders[0], segments=[(1, 2), (3, 4), (5, 6)])
    clip = folder / "clip_1.mp4"
    assert abs(duration_of(clip) - 3.0) < 0.15
    for t in (0.2, 1.2, 2.4):
        assert luma_at(clip, t) > 200                       # white all the way: every black second was dropped
    assert rms_at(clip, 1.0) > 100                          # and the sound carries on


def test_keeping_the_black_seconds_gives_a_black_video(folders):
    job, folder, m = make_striped_job(folders[0], segments=[(0, 1), (2, 3)])
    clip = folder / "clip_1.mp4"
    assert abs(duration_of(clip) - 2.0) < 0.15
    assert luma_at(clip, 0.5) < 40 and luma_at(clip, 1.5) < 40


def test_nothing_removed_renders_exactly_as_before(folders):
    job, folder, _ = make_striped_job(folders[0])
    plain = frames(folder / "clip_1.mp4")
    job2 = folders[0] / "second"
    job2.mkdir()
    import shutil
    shutil.copyfile(folder / "source.mp4", job2 / "source.mp4")
    clip = clip_entry(cut={"cut_start": 0.0, "cut_end": 6.0}, end=6.0)
    m = manifest.validate(manifest.from_clip(clip))
    m["segments"] = [{"start": 0.0, "end": 6.0}]                      # the whole clip, said explicitly
    render.create(job2, 1, m)
    assert frames(job2 / "clip_1.mp4") == plain


def test_removing_parts_through_the_editor_updates_everything_and_survives_later_edits(client, folders):
    job, folder, _ = make_striped_job(folders[0])
    doc = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    doc["segments"] = [{"start": 1, "end": 2}, {"start": 3, "end": 4}, {"start": 5, "end": 6}]
    r = client.put(f"/api/jobs/{job}/clips/1/manifest", json=doc)
    assert r.status_code == 200, r.text
    assert r.json()["duration"] == 3.0 and r.json()["version"] == 1
    assert abs(duration_of(folder / "clip_1.mp4") - 3.0) < 0.15
    # a different tool must not bring the removed parts back
    assert client.post(f"/api/jobs/{job}/clips/1/effects", json={"zoom": 1.2, "pan": "none"}).status_code == 200
    assert abs(duration_of(folder / "clip_1.mp4") - 3.0) < 0.15
    got = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    assert len(got["segments"]) == 3 and got["effects"]["zoom"] == 1.2


def test_trimming_a_tightened_video_keeps_only_the_parts_inside(client, folders):
    job, folder, _ = make_striped_job(folders[0], segments=[(1, 2), (3, 4), (5, 6)])
    doc = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    doc["clip"] = {"start": 0.0, "end": 4.2}                           # trim off the last part
    r = client.put(f"/api/jobs/{job}/clips/1/manifest", json=doc)
    assert r.status_code == 200, r.text
    got = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    assert got["segments"] == [{"start": 1.0, "end": 2.0}, {"start": 3.0, "end": 4.0}]
    assert abs(duration_of(folder / "clip_1.mp4") - 2.0) < 0.15


def test_captions_follow_the_cuts_in_the_finished_video(folders):
    words = [{"text": "one", "start": 1.2, "end": 1.7}, {"text": "mid", "start": 2.3, "end": 2.8},
             {"text": "two", "start": 3.2, "end": 3.7}]
    job, folder, m = make_striped_job(folders[0], segments=[(1, 2), (3, 4)], words=words)
    spec = manifest.text_drawer_spec(m)
    assert [(w["text"], round(w["start"], 2)) for w in spec["words"]] == [("one", 0.2), ("two", 1.2)]
