"""The shared render path (app/render.py, pipeline._apply): only changed stages run, a failed
render changes nothing, old projects keep working, and the default manifest rebuilds the very same
picture the app always made. Media is a 2.6 s synthetic fixture."""
import copy
import hashlib
import json
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app import captionstyles, export, main, manifest, pipeline, render

WORDS = [{"text": "hello", "start": 0.4, "end": 0.9}, {"text": "brave", "start": 1.0, "end": 1.5}]
STYLE = captionstyles.resolve("clean").as_dict()


def fixture_video(path, seconds=2.6):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size=1280x720:rate=25:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    return path


def frames(path) -> str:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], check=True, capture_output=True).stdout
    return hashlib.sha256(raw).hexdigest()


def clip_entry(**extra):
    clip = {"id": 1, "start": 0.0, "end": 2.6, "duration": 2.6, "title": "T", "music": None, "version": 0,
            "cut": {"cut_start": 0.0, "cut_end": 2.6}, "framing_choice": "crop",
            "effects": {"zoom": 1.0, "pan": "none"},
            "text": {"mode": "captions", "verdict": "reliable", "reasons": [], "headline": None},
            "captions": {"style": copy.deepcopy(STYLE), "words": copy.deepcopy(WORDS)}}
    clip.update(extra)
    return clip


def make_job(work, clip, job_id="abcdef0123", build=True):
    """A finished job folder. With build=True the clip files are made the way the pipeline makes them."""
    folder = work / job_id
    folder.mkdir()
    (folder / "status.json").write_text(json.dumps({"status": "done"}))
    (folder / "provenance.json").write_text(json.dumps({"rights": "own", "url": None, "title": "", "uploader": ""}))
    fixture_video(folder / "source.mp4")
    if build:
        style = captionstyles.resolve("clean")
        export.export_clip(folder / "source.mp4", [], 0.0, 2.6, folder / "clip_1.mp4", folder, "crop",
                           style=style, cap_words=copy.deepcopy(WORDS))
    (folder / "clips.json").write_text(json.dumps({"status": "done", "note": "ok", "clips": [clip]}))
    return job_id, folder


@pytest.fixture
def client(folders):
    with TestClient(main.app) as c:
        yield c


# ---------------------------------------------------------------- which stages run

def base():
    return manifest.validate(manifest.from_clip(clip_entry()))


def test_stage_diff_runs_only_what_changed():
    old = base()
    same = copy.deepcopy(old)
    assert render.stages(old, same) == []
    assert render.stages(old, same, {render.TEXT}) == ["text", "music"]       # an explicit apply

    zoom = copy.deepcopy(old); zoom["effects"]["zoom"] = 1.3
    assert render.stages(old, zoom) == ["picture", "text", "music"]

    words = copy.deepcopy(old); words["text"]["captions"]["words"][0]["text"] = "hi"
    assert render.stages(old, words) == ["text", "music"]                     # the picture is not redone

    mus = copy.deepcopy(old); mus["audio"]["music"] = {"track_id": "t", "volume": 0.4}
    assert render.stages(old, mus) == ["music"]                               # only the mix


# ---------------------------------------------------------------- a failed render changes nothing

def test_a_failed_render_leaves_the_clip_exactly_as_it_was(client, folders, monkeypatch):
    job, folder = make_job(folders[0], clip_entry())
    before = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}

    def boom(*a, **k):
        raise RuntimeError("ffmpeg failed: simulated")
    monkeypatch.setattr(render, "apply_captions", boom)
    r = client.post(f"/api/jobs/{job}/clips/1/effects", json={"zoom": 1.4, "pan": "left"})
    assert r.status_code == 500
    log = (folder / "usage.jsonl").read_text()               # the usage log is append-only: it records the failure
    after = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file() and p.name != "usage.jsonl"}
    assert after == before                                  # clip, base and clips.json untouched
    assert '"ok": false' in log and '"kind": "render"' in log
    assert not (folder / ".render_1").exists()              # and no temporary files left behind
    assert not pipeline.heavy_job_lock.locked()


# ---------------------------------------------------------------- old projects keep working

def test_music_can_still_be_changed_on_an_old_clip(client, folders, monkeypatch):
    """Old clips have no stored captions or cut: only the mix may be remade, and it still works."""
    old_clip = {"id": 1, "start": 0.0, "end": 2.6, "duration": 2.6, "title": "T", "music": None, "version": 0}
    job, folder = make_job(folders[0], old_clip, build=False)
    shutil.copyfile(folder / "source.mp4", folder / "clip_1.mp4")
    track = {"id": "t1", "title": "S", "license_label": "CC0", "attribution": "", "warning": None}
    mixed = []
    monkeypatch.setattr(render.music, "get_track", lambda tid: track)
    monkeypatch.setattr(render.music, "track_path", lambda t: folder / "t.wav")
    monkeypatch.setattr(render.mix, "apply_music", lambda b, t, out, v: mixed.append(v) or shutil.copyfile(b, out))
    monkeypatch.setattr(render, "render_base", lambda *a, **k: pytest.fail("the picture must not be remade"))
    r = client.post(f"/api/jobs/{job}/clips/1/music", json={"track_id": "t1", "volume": 0.4})
    assert r.status_code == 200 and mixed == [0.4]
    assert r.json()["music"]["title"] == "S" and r.json()["version"] == 1
    assert (folder / "clip_1_music.mp4").exists()
    # and removing it deletes the mixed file so it is never served stale
    r = client.post(f"/api/jobs/{job}/clips/1/music", json={"track_id": None, "volume": 0.4})
    assert r.status_code == 200 and not (folder / "clip_1_music.mp4").exists()


# ---------------------------------------------------------------- the default manifest changes nothing

def test_rebuilding_with_the_default_manifest_gives_the_same_picture(folders):
    job, folder = make_job(folders[0], clip_entry())
    original = frames(folder / "clip_1.mp4")
    pipeline.set_clip_effects(job, 1, {"zoom": 1.0, "pan": "none"})       # re-makes picture, text, mix
    assert frames(folder / "clip_1.mp4") == original
    assert json.loads((folder / "clips.json").read_text())["clips"][0]["version"] == 1


# ---------------------------------------------------------------- the editor's one Apply

def test_put_manifest_remakes_only_what_it_changes(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    before = frames(folder / "clip_1.mp4")
    doc = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    doc["effects"] = {"zoom": 1.4, "pan": "right"}
    r = client.put(f"/api/jobs/{job}/clips/1/manifest", json=doc)
    assert r.status_code == 200, r.text
    assert r.json()["effects"] == {"zoom": 1.4, "pan": "right"} and r.json()["version"] == 1
    assert frames(folder / "clip_1.mp4") != before                         # the picture really changed
    assert client.get(f"/api/jobs/{job}/clips/1/manifest").json()["effects"]["zoom"] == 1.4


def test_put_manifest_with_no_change_does_nothing(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    doc = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    clips_before = (folder / "clips.json").read_text()
    r = client.put(f"/api/jobs/{job}/clips/1/manifest", json=doc)
    assert r.status_code == 200 and r.json()["version"] == 0
    assert (folder / "clips.json").read_text() == clips_before


@pytest.mark.parametrize("edit, message", [
    (lambda d: d["text"].update(mode="none", captions=None), "text"),          # text has its own tools
    (lambda d: d["effects"].update(zoom=3.0), "Zoom"),
    (lambda d: d.update(version=9), "version"),
])
def test_put_manifest_refuses_bad_or_text_changes(client, folders, edit, message):
    job, folder = make_job(folders[0], clip_entry())
    doc = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    before = (folder / "clips.json").read_text()
    edit(doc)
    r = client.put(f"/api/jobs/{job}/clips/1/manifest", json=doc)
    assert r.status_code == 400 and message in r.json()["detail"]
    assert (folder / "clips.json").read_text() == before


# ================================================================== video fades

import numpy as np  # noqa: E402


def luma_at(path, t) -> float:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t}", "-i", str(path), "-frames:v", "1",
                          "-vf", "scale=32:32", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         check=True, capture_output=True).stdout
    return float(np.frombuffer(raw, dtype=np.uint8).mean())


def rms_at(path, t, seconds=0.12) -> float:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t}", "-t", f"{seconds}", "-i", str(path),
                          "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         check=True, capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(float)
    return float(np.sqrt((x ** 2).mean())) if len(x) else 0.0


def put(client, job, edit):
    doc = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    edit(doc)
    return client.put(f"/api/jobs/{job}/clips/1/manifest", json=doc)


def test_video_fades_darken_the_ends_picture_text_and_sound(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    clip = folder / "clip_1.mp4"
    assert luma_at(clip, 0.0) > 20 and rms_at(clip, 0.0) > 100               # a normal start, no fade yet
    plain_mid = luma_at(clip, 1.3)
    r = put(client, job, lambda d: d.update(fades={"in": 0.8, "out": 0.8}))
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 1
    assert luma_at(clip, 0.0) < 0.35 * plain_mid                              # starts from black
    assert luma_at(clip, 2.55) < 0.55 * plain_mid                             # ends fading to black
    assert abs(luma_at(clip, 1.3) - plain_mid) < 0.15 * plain_mid             # the middle is untouched
    assert rms_at(clip, 0.0, 0.05) < 0.5 * rms_at(clip, 1.3)                  # the sound fades in too
    assert client.get(f"/api/jobs/{job}/clips/1/manifest").json()["fades"] == {"in": 0.8, "out": 0.8}


def test_fades_can_leave_the_sound_alone(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    clip = folder / "clip_1.mp4"
    r = put(client, job, lambda d: (d.update(fades={"in": 0.8, "out": 0}), d["audio"].update(fade_with_video=False)))
    assert r.status_code == 200, r.text
    assert luma_at(clip, 0.0) < 40                                            # picture fades in
    assert rms_at(clip, 0.0, 0.05) > 0.5 * rms_at(clip, 1.3)                  # the sound does not


def test_fades_work_on_a_clip_with_no_text(client, folders):
    clip = clip_entry(text={"mode": "none", "verdict": "reliable", "reasons": [], "headline": None})
    clip.pop("captions")
    job, folder = make_job(folders[0], clip, build=False)
    export.export_clip(folder / "source.mp4", [], 0.0, 2.6, folder / "clip_1.mp4", folder, "crop", cap_words=[])
    assert put(client, job, lambda d: d.update(fades={"in": 0.8, "out": 0})).status_code == 200
    assert luma_at(folder / "clip_1.mp4", 0.0) < 40


def test_removing_the_fades_brings_the_original_picture_back(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    original = frames(folder / "clip_1.mp4")
    assert put(client, job, lambda d: d.update(fades={"in": 0.8, "out": 0.8})).status_code == 200
    assert frames(folder / "clip_1.mp4") != original
    assert put(client, job, lambda d: d.update(fades={"in": 0, "out": 0})).status_code == 200
    assert frames(folder / "clip_1.mp4") == original                         # fades off = exactly as before


@pytest.mark.parametrize("fades, message", [({"in": 4, "out": 0}, "between"), ({"in": 1.5, "out": 1.5}, "longer")])
def test_unreasonable_fades_are_refused(client, folders, fades, message):
    job, folder = make_job(folders[0], clip_entry(), build=False)
    (folder / "clip_1.mp4").write_bytes(b"x")
    before = (folder / "clips.json").read_text()
    r = put(client, job, lambda d: d.update(fades=fades, clip={"start": 0.0, "end": 2.6}))
    assert r.status_code == 400 and message in r.json()["detail"]
    assert (folder / "clips.json").read_text() == before


# ================================================================== trim (shorten only, for now)

def duration_of(path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(path)], check=True, capture_output=True, text=True).stdout)


def test_trimming_shortens_the_video_and_moves_the_captions(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    r = put(client, job, lambda d: d.update(clip={"start": 0.5, "end": 2.1}))
    assert r.status_code == 200, r.text
    assert abs(duration_of(folder / "clip_1.mp4") - 1.6) < 0.1
    saved = json.loads((folder / "clips.json").read_text())["clips"][0]
    assert saved["duration"] == 1.6 and saved["cut"] == {"cut_start": 0.5, "cut_end": 2.1}
    assert saved["start"] == 0.5 and saved["end"] == 2.1
    words = saved["captions"]["words"]
    assert [w["text"] for w in words] == ["brave"]                            # "hello" was cut in half: dropped
    assert (words[0]["start"], words[0]["end"]) == (0.5, 1.0)                 # shifted by the new start
    assert client.get(f"/api/jobs/{job}/clips/1/manifest").json()["clip"] == {"start": 0.5, "end": 2.1}


def test_the_trimmed_picture_matches_the_same_part_of_the_source(client, folders):
    """What you keep is the right part of the video: the first frame is the source at the new start."""
    job, folder = make_job(folders[0], clip_entry())
    put(client, job, lambda d: (d.update(clip={"start": 1.0, "end": 2.4}), d["text"].update(mode="captions")))
    ref = folder / "ref.mp4"
    export.render_base(folder / "source.mp4", base=ref, start=1.0, end=2.4, framing="crop", clean_audio=True)
    # same stage-1 settings, same range: the trimmed clip's picture equals it apart from the caption strip
    assert abs(luma_at(folder / "clip_1.mp4", 0.0) - luma_at(ref, 0.0)) < 8


@pytest.mark.parametrize("span, message", [
    ({"start": 0.0, "end": 2.9}, "shortened"),
    ({"start": -0.2 + 0.2, "end": 2.6 + 0.5}, "shortened"),
    ({"start": 1.0, "end": 1.4}, "at least"),
])
def test_trim_can_only_shorten_and_never_below_a_second(client, folders, span, message):
    job, folder = make_job(folders[0], clip_entry())
    before = (folder / "clips.json").read_text()
    r = put(client, job, lambda d: d.update(clip=span))
    assert r.status_code == 400 and message in r.json()["detail"]
    assert (folder / "clips.json").read_text() == before


# ================================================================== later edits keep earlier ones

def test_fades_and_trim_survive_later_edits(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    assert put(client, job, lambda d: d.update(clip={"start": 0.2, "end": 2.4}, fades={"in": 0.5, "out": 0.5})).status_code == 200
    # a different tool (zoom) and a caption restyle must not undo the trim or the fades
    assert client.post(f"/api/jobs/{job}/clips/1/effects", json={"zoom": 1.2, "pan": "none"}).status_code == 200
    assert client.post(f"/api/jobs/{job}/clips/1/captions", json={"preset": "pill"}).status_code == 200
    m = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    assert m["clip"] == {"start": 0.2, "end": 2.4} and m["fades"] == {"in": 0.5, "out": 0.5}
    assert m["effects"]["zoom"] == 1.2 and m["text"]["captions"]["style"]["preset"] == "pill"
    assert abs(duration_of(folder / "clip_1.mp4") - 2.2) < 0.1
    assert luma_at(folder / "clip_1.mp4", 0.0) < 40                           # still fading in


# ================================================================== creating a clip, and the saved manifest

def test_creating_a_clip_from_its_manifest_gives_the_same_video_as_the_old_export(folders):
    """Creation now goes through the manifest and render.py. It must make exactly what export_clip made."""
    job, folder = make_job(folders[0], clip_entry())                 # made with export_clip
    old_video = folder / "clip_1.mp4"
    m = manifest.validate(manifest.from_clip(clip_entry()))
    other = folders[0] / "second"
    other.mkdir()
    shutil.copyfile(folder / "source.mp4", other / "source.mp4")
    result = render.create(other, 1, m)
    assert result["stages"] == ["picture", "text", "music"]
    assert frames(other / "clip_1.mp4") == frames(old_video)
    assert (other / "clip_1_base.mp4").exists() and not (other / ".render_1").exists()


def test_every_edit_saves_the_manifest_and_keeps_a_history(client, folders):
    job, folder = make_job(folders[0], clip_entry())                 # an old-style clip: nothing saved yet
    assert manifest.load(folder, 1) is None
    assert client.post(f"/api/jobs/{job}/clips/1/effects", json={"zoom": 1.2, "pan": "none"}).status_code == 200
    saved = manifest.load(folder, 1)
    assert saved["effects"]["zoom"] == 1.2
    assert client.post(f"/api/jobs/{job}/clips/1/effects", json={"zoom": 1.4, "pan": "left"}).status_code == 200
    doc = json.loads(manifest.store_path(folder, 1).read_text())
    assert doc["current"]["effects"] == {"zoom": 1.4, "pan": "left"}
    assert [h["manifest"]["effects"]["zoom"] for h in doc["history"]] == [1.2]      # the one it replaced
    assert client.get(f"/api/jobs/{job}/clips/1/manifest").json()["effects"]["zoom"] == 1.4


def test_a_failed_edit_does_not_touch_the_saved_manifest(client, folders, monkeypatch):
    job, folder = make_job(folders[0], clip_entry())
    assert client.post(f"/api/jobs/{job}/clips/1/effects", json={"zoom": 1.2, "pan": "none"}).status_code == 200
    before = manifest.store_path(folder, 1).read_text()
    monkeypatch.setattr(render, "apply_captions", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert client.post(f"/api/jobs/{job}/clips/1/effects", json={"zoom": 1.5, "pan": "none"}).status_code == 500
    assert manifest.store_path(folder, 1).read_text() == before


def test_a_saved_manifest_never_gives_captions_to_an_untrusted_clip(folders):
    folder = folders[0] / "j"
    folder.mkdir()
    clip = clip_entry(text={"mode": "pending", "verdict": "unusable", "reasons": [], "headline": None})
    m = manifest.validate(manifest.from_clip(clip_entry()))          # a manifest that (wrongly) holds words
    m["text"]["mode"] = "captions"
    manifest.save(folder, 1, m)
    assert manifest.current(folder, clip)["text"]["captions"] is None


def test_an_unreadable_saved_manifest_falls_back_to_the_clip(folders):
    folder = folders[0] / "j2"
    folder.mkdir()
    manifest.store_path(folder, 1).write_text("{ not json")
    assert manifest.load(folder, 1) is None
    assert manifest.current(folder, clip_entry())["effects"] == {"zoom": 1.0, "pan": "none"}
