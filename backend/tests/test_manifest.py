"""The editing manifest (app/manifest.py): building it from old and new clips, checking it, and
proving that the default manifest renders exactly what the app rendered before.
All media here is a 2-3 second synthetic fixture."""
import copy
import hashlib
import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from app import captionstyles, export, main, manifest

# A clip entry exactly as an OLD job saved it (no effects, no captions block, no text block).
LEGACY_CLIP = {
    "id": 1, "start": 0.0, "end": 2.0, "title": "T", "duration": 2.0,
    "music": {"track_id": "starter-emotional", "title": "Quiet Window", "volume": 0.6,
              "license": "CC0 / public domain", "attribution": "", "warning": None},
    "framing": {"mode": "track", "reason": "following the speaker"},
    "cut": {"cut_start": 0.0, "cut_end": 2.0, "start_snapped": False, "end_snapped": False, "clean_end": True},
    "audio": {"applied": True, "target_lufs": -14.0},
}
WORDS = [{"text": "hello", "start": 0.4, "end": 0.9}, {"text": "brave", "start": 1.0, "end": 1.5}]


def new_clip(**extra):
    """A clip entry as the current pipeline saves it."""
    style = captionstyles.resolve("clean")
    clip = copy.deepcopy(LEGACY_CLIP)
    clip.update(framing_choice="crop", effects={"zoom": 1.0, "pan": "none"},
                text={"mode": "captions", "verdict": "reliable", "reasons": [], "headline": None},
                captions={"style": style.as_dict(), "words": copy.deepcopy(WORDS)})
    clip.update(extra)
    return clip


# ---------------------------------------------------------------- building

def test_default_manifest_is_valid_and_changes_nothing():
    m = manifest.validate(manifest.default_manifest(1.0, 31.0))
    assert m["effects"] == {"zoom": 1.0, "pan": "none"}
    assert m["fades"] == {"in": 0.0, "out": 0.0} and m["transitions"] == []
    assert m["framing"]["mode"] == "crop" and m["audio"]["clean_voice"] is True


def test_old_job_clip_gets_a_manifest_with_todays_defaults():
    before = copy.deepcopy(LEGACY_CLIP)
    m = manifest.validate(manifest.from_clip(LEGACY_CLIP))
    assert LEGACY_CLIP == before                                   # the clip is not touched
    assert m["clip"] == {"start": 0.0, "end": 2.0}
    assert m["framing"]["mode"] == "crop"
    assert m["effects"] == {"zoom": 1.0, "pan": "none"}
    assert m["text"] == {"mode": "captions", "captions": None, "headline": None, "hook": None}
    assert m["audio"]["music"] == {"track_id": "starter-emotional", "volume": 0.6}


def test_new_clip_manifest_carries_captions_effects_and_framing():
    clip = new_clip(framing_choice="blur", effects={"zoom": 1.3, "pan": "left"})
    m = manifest.validate(manifest.from_clip(clip))
    assert m["framing"]["mode"] == "blur"
    assert m["effects"] == {"zoom": 1.3, "pan": "left"}
    assert [w["text"] for w in m["text"]["captions"]["words"]] == ["hello", "brave"]


def test_headline_clip():
    clip = new_clip(text={"mode": "headline", "verdict": "unreliable", "reasons": [],
                          "headline": {"text": "My title", "style": {"preset": "clean"}, "approved": True}})
    clip.pop("captions")
    m = manifest.validate(manifest.from_clip(clip))
    assert m["text"]["mode"] == "headline" and m["text"]["headline"]["text"] == "My title"
    assert manifest.text_drawer_spec(m)["kind"] == "headline"


def test_words_of_an_untrusted_clip_never_enter_the_manifest():
    clip = new_clip(text={"mode": "pending", "verdict": "unusable", "reasons": [], "headline": None})
    m = manifest.validate(manifest.from_clip(clip))
    assert m["text"] == {"mode": "pending", "captions": None, "headline": None, "hook": None}
    assert "hello" not in json.dumps(m)


def test_manifest_survives_json():
    m = manifest.validate(manifest.from_clip(new_clip()))
    assert manifest.validate(json.loads(json.dumps(m))) == m


# ---------------------------------------------------------------- checking

def bad(**changes):
    m = manifest.default_manifest(0.0, 2.0)
    for path, value in changes.items():
        node = m
        *parents, last = path.split("__")
        for p in parents:
            node = node[p]
        node[last] = value
    return m


@pytest.mark.parametrize("m, message", [
    (bad(version=9), "Unsupported manifest version"),
    (bad(clip__end=0.0), "after clip.start"),
    (bad(clip__start=-1), "between"),
    (bad(clip__start="x"), "must be a number"),
    (bad(framing__mode="stretch"), "crop or blur"),
    (bad(effects__zoom=2.0), "Zoom must be between"),
    (bad(effects__pan="up"), "Pan must be"),
    (bad(fades__in=5), "fades.in must be between"),
    (bad(fades__in=1.5, fades__out=1.0), "longer than the video"),
    (bad(clip__end=0.5), "at least"),
    (bad(audio__fade_with_video="yes"), "fade_with_video"),
    (bad(transitions=[{"type": "fade"}]), "Transitions are not supported yet"),
    (bad(text__mode="banner"), "text.mode"),
    (bad(text__mode="headline"), "headline needs its text"),
    (bad(text__captions={"style": {}, "words": []}, text__mode="none"), "only allowed when"),
    (bad(audio__music={"track_id": "t", "volume": 2}), "volume"),
    (bad(audio__clean_voice="yes"), "true or false"),
])
def test_invalid_manifests_are_refused_with_a_reason(m, message):
    with pytest.raises(ValueError, match=message):
        manifest.validate(m)


def test_missing_section_and_non_object_are_refused():
    m = manifest.default_manifest(0, 2)
    del m["audio"]
    with pytest.raises(ValueError, match="'audio' section"):
        manifest.validate(m)
    with pytest.raises(ValueError):
        manifest.validate([])


def test_a_caption_word_that_ends_before_it_starts_is_refused():
    m = manifest.default_manifest(0, 2)
    m["text"]["captions"] = {"style": {}, "words": [{"text": "a", "start": 1.5, "end": 1.2}]}
    with pytest.raises(ValueError, match="ends before it starts"):
        manifest.validate(m)


def test_a_clip_with_burned_in_captions_cannot_be_rendered_again():
    m = manifest.validate(manifest.from_clip(LEGACY_CLIP))
    with pytest.raises(ValueError, match="before its captions"):
        manifest.check_renderable(m)
    manifest.check_renderable(manifest.validate(manifest.from_clip(new_clip())))   # fine


# ---------------------------------------------------------------- reading it

def test_default_render_args_equal_the_arguments_the_app_always_used():
    args = manifest.render_args(manifest.from_clip(LEGACY_CLIP))
    assert args == {"start": 0.0, "end": 2.0, "framing": "crop", "clean_audio": True,
                    "effects": {"zoom": 1.0, "pan": "none"}, "segments": None}


def _fixture_video(path, seconds=2.0):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size=1280x720:rate=25:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    return path


def _frames_hash(path) -> str:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], check=True, capture_output=True).stdout
    return hashlib.sha256(raw).hexdigest()


def test_default_manifest_renders_the_same_picture_as_the_old_direct_call(tmp_path):
    """The key promise: moving to the manifest changes nothing in the output."""
    src = _fixture_video(tmp_path / "src.mp4")
    old, new = tmp_path / "old.mp4", tmp_path / "new.mp4"
    export.render_base(src, 0.0, 2.0, old, framing="crop", clean_audio=False)        # how it was called
    args = manifest.render_args(manifest.from_clip(LEGACY_CLIP))
    args["clean_audio"] = False                                                      # keep the test quick
    export.render_base(src, base=new, **args)                                        # from the manifest
    assert _frames_hash(old) == _frames_hash(new)


# ---------------------------------------------------------------- the endpoint and the re-render

@pytest.fixture
def client(folders):
    with TestClient(main.app) as c:
        yield c


def make_job(work, clip, job_id="abcdef0123"):
    folder = work / job_id
    folder.mkdir()
    (folder / "status.json").write_text(json.dumps({"status": "done"}))
    (folder / "provenance.json").write_text(json.dumps({"rights": "own", "url": None, "title": "", "uploader": ""}))
    _fixture_video(folder / "source.mp4", 2.6)
    (folder / "clip_1.mp4").write_bytes(b"old")
    (folder / "clips.json").write_text(json.dumps({"status": "done", "note": "ok", "clips": [clip]}))
    return job_id, folder


def test_endpoint_gives_every_old_job_a_manifest(client, folders):
    job, _ = make_job(folders[0], LEGACY_CLIP)
    r = client.get(f"/api/jobs/{job}/clips/1/manifest")
    assert r.status_code == 200
    assert r.json()["version"] == manifest.SCHEMA_VERSION
    assert r.json()["effects"] == {"zoom": 1.0, "pan": "none"}


def test_endpoint_hides_words_of_an_untrusted_clip(client, folders):
    clip = new_clip(text={"mode": "pending", "verdict": "unusable", "reasons": [], "headline": None})
    job, _ = make_job(folders[0], clip)
    body = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    assert body["text"]["captions"] is None and "hello" not in json.dumps(body)


def test_changing_effects_on_a_new_clip_rebuilds_it_from_the_manifest(client, folders):
    clip = new_clip(cut={"cut_start": 0.0, "cut_end": 2.6}, duration=2.6, end=2.6, music=None)
    job, folder = make_job(folders[0], clip)
    r = client.post(f"/api/jobs/{job}/clips/1/effects", json={"zoom": 1.3, "pan": "left"})
    assert r.status_code == 200, r.text
    assert r.json()["effects"] == {"zoom": 1.3, "pan": "left"}
    assert r.json()["version"] == 1
    assert (folder / "clip_1.mp4").stat().st_size > 1000          # a real video, not the placeholder
    saved = json.loads((folder / "clips.json").read_text())["clips"][0]
    assert saved["effects"] == {"zoom": 1.3, "pan": "left"}
    assert client.get(f"/api/jobs/{job}/clips/1/manifest").json()["effects"]["zoom"] == 1.3


def test_changing_effects_on_an_old_clip_is_refused_and_leaves_it_alone(client, folders):
    job, folder = make_job(folders[0], LEGACY_CLIP)
    r = client.post(f"/api/jobs/{job}/clips/1/effects", json={"zoom": 1.3, "pan": "none"})
    assert r.status_code == 400 and "captions" in r.json()["detail"]
    assert (folder / "clip_1.mp4").read_bytes() == b"old"          # the old clip file is untouched
    assert json.loads((folder / "clips.json").read_text())["clips"][0] == LEGACY_CLIP
