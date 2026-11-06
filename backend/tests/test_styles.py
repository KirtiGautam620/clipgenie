"""Editing styles and the three edit modes: one engine, different choices. Auto Edit and AI + Manual
use the Natural style (what Auto Edit always did); Custom Style uses the one you pick; any video can
be restyled afterwards or taken back to CocoGenie's own edit."""
import copy
import json
import shutil
import subprocess

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import captionstyles, cuts, main, manifest, pipeline, plan, render, styles
from tests.test_plan import RELIABLE, transcript_with_a_pause
from tests.test_quality import speech_envelope
from tests.test_render import clip_entry, frames, make_job
from tests.test_segments import make_striped_job


@pytest.fixture(autouse=True)
def own_styles_file(tmp_path, monkeypatch):
    monkeypatch.setattr(styles, "USER_FILE", tmp_path / "styles.json")


@pytest.fixture
def client(folders):
    with TestClient(main.app) as c:
        yield c


# ---------------------------------------------------------------- the styles themselves

def test_every_builtin_style_is_valid_and_natural_has_no_opinion():
    for style in styles.all_styles():
        styles.validate({k: v for k, v in style.items() if k not in ("id", "builtin")})
    natural = styles.get("natural")
    assert natural["framing"] is None and natural["music"] is None            # your own choices stand
    assert natural["effects"] == {"zoom": 1.0, "pan": "none"} and natural["fades"] == {"in": 0.0, "out": 0.0}
    assert [s["id"] for s in styles.all_styles()][:4] == ["natural", "punchy", "calm", "podcast"]


@pytest.mark.parametrize("change, message", [
    ({"name": ""}, "name"), ({"name": "x" * 41}, "name"),
    ({"caption_preset": "neon"}, "caption look"), ({"pauses": "extreme"}, "pauses"),
    ({"hook": {"enabled": "yes"}}, "hook.enabled"), ({"hook": {"enabled": True, "preset": "nope"}}, "headline look"),
    ({"hook": {"enabled": True, "seconds": 60}}, "hook.seconds"),
    ({"effects": {"zoom": 3.0}}, "Zoom"), ({"fades": {"in": 9}}, "fades.in"),
    ({"music": {"enabled": True, "volume": 4}}, "music.volume"), ({"framing": "stretch"}, "framing"),
])
def test_bad_styles_are_refused(change, message):
    with pytest.raises(ValueError, match=message):
        styles.validate({**styles.BUILTIN["punchy"], **change})


def test_users_can_save_list_and_delete_their_own_styles():
    saved = styles.save_user({**styles.BUILTIN["calm"], "name": "My calm one"})
    assert saved["id"].startswith("u-") and saved["builtin"] is False
    assert styles.get(saved["id"])["name"] == "My calm one"
    assert [s["id"] for s in styles.all_styles()][-1] == saved["id"]
    styles.delete_user(saved["id"])
    assert styles.get(saved["id"]) is None
    with pytest.raises(KeyError):
        styles.delete_user(saved["id"])
    with pytest.raises(ValueError, match="Built-in"):
        styles.delete_user("natural")


def test_there_is_a_limit_and_a_damaged_file_is_not_a_crash(tmp_path):
    for i in range(styles.MAX_USER_STYLES):
        styles.save_user({**styles.BUILTIN["calm"], "name": f"s{i}"})
    with pytest.raises(ValueError, match="up to"):
        styles.save_user({**styles.BUILTIN["calm"], "name": "one too many"})
    styles.USER_FILE.write_text("{ broken")
    assert [s["id"] for s in styles.all_styles()] == ["natural", "punchy", "calm", "podcast"]


def test_a_style_can_be_made_from_a_finished_video():
    m = manifest.validate(manifest.from_clip(clip_entry(effects={"zoom": 1.3, "pan": "left"}, fades={"in": 0.5, "out": 0.5})))
    style = styles.from_manifest(m, "From my video", pauses="tight")
    assert style["effects"] == {"zoom": 1.3, "pan": "left"} and style["fades"] == {"in": 0.5, "out": 0.5}
    assert style["pauses"] == "tight" and style["framing"] == "crop" and style["caption_preset"] == "clean"


# ---------------------------------------------------------------- creating with a style

def create(monkeypatch, work, job="abcdef0123", **settings):
    folder = work / job
    folder.mkdir()
    (folder / "status.json").write_text(json.dumps({"status": "uploaded"}))
    ws = transcript_with_a_pause(folder)
    made = []

    def fake_create(f, n, m):
        made.append(m)
        return {"stages": ["picture", "text", "music"], "music": {"id": "t1", "title": "S", "license_label": "CC0",
                                                                  "attribution": "", "warning": None},
                "framing": {"mode": "center", "reason": "test", "audio": {"applied": False}}}
    monkeypatch.setattr(pipeline.render, "create", fake_create)
    monkeypatch.setattr(pipeline, "_pauses", lambda f: ([(8.1, 10.9)], speech_envelope(30), 30.0))
    monkeypatch.setattr(pipeline, "_text_quality", lambda *a, **k: RELIABLE)
    monkeypatch.setattr(pipeline.music, "pick_track", lambda mood, key: {"id": "t1", "title": "S", "license_label": "CC0",
                                                                          "attribution": "", "warning": None})
    monkeypatch.setattr(pipeline, "pick_ai_clips", lambda *a: ([{"start": 0.0, "end": ws[-1]["end"], "title": "T",
                                                                  "reason": "R", "mood": "funny", "score": 7}], "ok"))
    monkeypatch.setattr(plan, "suggest_hook", lambda text: "A curious hook")
    monkeypatch.setattr(plan, "unload", lambda: None)
    pipeline._make_clips(job, dict(use_ai=True, count=1, min_len=5, max_len=30, **settings))
    return folder, json.loads((folder / "clips.json").read_text())["clips"][0], made[0]


def test_auto_edit_is_what_it_always_was(folders, monkeypatch):
    folder, clip, m = create(monkeypatch, folders[0], music=True, music_volume=0.6)
    assert clip["edit"] == {"mode": "auto", "style_id": "natural", "style_name": "Natural", "pauses": "natural"}
    assert m["effects"] == {"zoom": 1.0, "pan": "none"} and m["fades"] == {"in": 0.0, "out": 0.0}
    assert m["text"]["captions"]["style"]["preset"] == "clean" and m["audio"]["music"]["volume"] == 0.6
    assert len(m["segments"]) == 2                                            # the long pause was tightened


def test_ai_plus_manual_makes_the_same_edit_and_says_so(folders, monkeypatch):
    folder, clip, m = create(monkeypatch, folders[0], edit_mode="assist", music=True, music_volume=0.6)
    assert clip["edit"]["mode"] == "assist" and clip["edit"]["style_id"] == "natural"
    assert m["effects"]["zoom"] == 1.0 and len(m["segments"]) == 2


def test_custom_style_changes_the_edit(folders, monkeypatch):
    folder, clip, m = create(monkeypatch, folders[0], edit_mode="custom", style_id="punchy", music=False)
    assert clip["edit"] == {"mode": "custom", "style_id": "punchy", "style_name": "Punchy Shorts", "pauses": "tight"}
    assert m["effects"]["zoom"] == 1.12 and m["fades"] == {"in": 0.0, "out": 0.4}
    assert m["text"]["captions"]["style"]["preset"] == "bold_pop" and m["framing"]["mode"] == "crop"
    assert m["audio"]["music"]["volume"] == 0.5                              # the style turned music on at its level
    assert clip["text"]["hook"]["style"]["preset"] == "banner"               # the style's hook look
    saved = json.loads((folder / "plan.json").read_text())
    assert saved["options"]["style_id"] == "punchy" and saved["options"]["edit_mode"] == "custom"
    base, how = manifest.load_baseline(folder, 1)                            # CocoGenie's version is kept
    assert how["style_id"] == "punchy" and base["effects"]["zoom"] == 1.12


def test_a_style_can_tighten_pauses_harder_or_leave_them(folders, monkeypatch):
    _, tight_clip, tight = create(monkeypatch, folders[0], "aaaaaaaaaa", edit_mode="custom", style_id="punchy")
    _, calm_clip, calm = create(monkeypatch, folders[0], "bbbbbbbbbb", edit_mode="custom", style_id="calm", music=False)
    gap = tight["segments"][1]["start"] - tight["segments"][0]["end"]
    assert abs(gap - 2.5) < 0.05                                             # removes 2.5 s of the 2.8 s pause (natural removes 2.3)
    assert len(calm["segments"]) == 1 and calm_clip["edit"]["pauses"] == "off"   # Calm Story keeps every pause


def test_the_users_own_framing_wins_unless_the_style_has_one(folders, monkeypatch):
    _, _, m = create(monkeypatch, folders[0], framing="blur", music=False)
    assert m["framing"]["mode"] == "blur"                                    # Natural has no opinion


def test_an_unknown_or_missing_style_is_refused_up_front():
    with pytest.raises(HTTPException) as e:
        main._check_edit("custom", "u-nope")
    assert e.value.status_code == 400
    with pytest.raises(HTTPException):
        main._check_edit("magic", "natural")
    main._check_edit("auto", "anything")                                    # not used outside Custom Style
    main._check_edit("custom", "punchy")


# ---------------------------------------------------------------- restyling a finished video

def test_applying_a_style_remakes_the_video_and_keeps_the_words(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    before = frames(folder / "clip_1.mp4")
    r = client.post(f"/api/jobs/{job}/clips/1/style", json={"style_id": "punchy"})
    assert r.status_code == 200, r.text
    got = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    assert got["effects"]["zoom"] == 1.12 and got["fades"]["out"] == 0.4 and got["framing"]["mode"] == "crop"
    assert got["text"]["captions"]["style"]["preset"] == "bold_pop"
    assert [w["text"] for w in got["text"]["captions"]["words"]] == ["hello", "brave"]       # the words are untouched
    assert r.json()["edit"]["style_name"] == "Punchy Shorts" and r.json()["version"] == 1
    assert any("pauses unchanged" in note for note in r.json()["edit"]["skipped"])   # this project saved no audio
    assert "no music track available" in r.json()["edit"]["skipped"]                 # and its library is empty
    assert frames(folder / "clip_1.mp4") != before


def test_applying_a_style_leaves_your_headline_alone(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    assert client.post(f"/api/jobs/{job}/clips/1/text", json={"headline": {"text": "My title"}, "approve": True}).status_code == 200
    assert client.post(f"/api/jobs/{job}/clips/1/style", json={"style_id": "calm"}).status_code == 200
    got = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    assert got["text"]["mode"] == "headline" and got["text"]["headline"]["text"] == "My title"


def test_applying_a_style_can_tighten_the_pauses_of_a_saved_project(client, folders):
    """With the project's audio and transcript saved, a style re-measures the pauses and cuts them."""
    job, folder, m = make_striped_job(folders[0])
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=6",
                    "-af", "volume=enable='between(t,2,4.5)':volume=0", "-ac", "1", "-ar", "16000",
                    str(folder / "audio.wav")], check=True)
    words = [{"word": "a", "start": 0.5, "end": 1.0}, {"word": "b", "start": 4.8, "end": 5.3}]
    (folder / "transcript.json").write_text(json.dumps(
        {"language": "en", "segments": [{"start": 0.5, "end": 5.3, "text": "a b", "words": words}]}))
    r = client.post(f"/api/jobs/{job}/clips/1/style", json={"style_id": "punchy"})
    assert r.status_code == 200, r.text
    got = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    assert len(got["segments"]) == 2 and manifest.is_cut(manifest.validate(got))
    assert r.json()["duration"] < 6.0
    assert not any("pauses" in note for note in r.json()["edit"]["skipped"])          # the pauses were measured
    # and a style that keeps pauses puts them back
    assert client.post(f"/api/jobs/{job}/clips/1/style", json={"style_id": "calm"}).status_code == 200
    assert len(client.get(f"/api/jobs/{job}/clips/1/manifest").json()["segments"]) == 1


def test_an_unknown_style_is_a_404_and_changes_nothing(client, folders):
    job, folder = make_job(folders[0], clip_entry())
    before = (folder / "clips.json").read_text()
    assert client.post(f"/api/jobs/{job}/clips/1/style", json={"style_id": "u-missing"}).status_code == 404
    assert (folder / "clips.json").read_text() == before


# ---------------------------------------------------------------- going back to CocoGenie's own edit

def made_with_baseline(work):
    job, folder = make_job(work, clip_entry())
    m = manifest.validate(manifest.from_clip(clip_entry()))
    manifest.save_baseline(folder, 1, m, edit={"mode": "assist", "style_id": "natural", "style_name": "Natural", "pauses": "natural"})
    return job, folder


def test_reset_brings_back_the_original_picture_exactly(client, folders):
    job, folder = made_with_baseline(folders[0])
    original = frames(folder / "clip_1.mp4")
    assert client.post(f"/api/jobs/{job}/clips/1/effects", json={"zoom": 1.4, "pan": "left"}).status_code == 200
    doc = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    doc["fades"] = {"in": 0.5, "out": 0.5}
    assert client.put(f"/api/jobs/{job}/clips/1/manifest", json=doc).status_code == 200
    assert frames(folder / "clip_1.mp4") != original
    r = client.post(f"/api/jobs/{job}/clips/1/reset")
    assert r.status_code == 200, r.text
    assert frames(folder / "clip_1.mp4") == original                         # as CocoGenie first made it
    assert r.json()["edit"]["mode"] == "assist" and r.json()["effects"] == {"zoom": 1.0, "pan": "none"}


def test_reset_restores_the_trim_and_the_caption_words_but_keeps_your_caption_look(client, folders):
    job, folder = made_with_baseline(folders[0])
    doc = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    doc["clip"] = {"start": 0.5, "end": 2.1}
    assert client.put(f"/api/jobs/{job}/clips/1/manifest", json=doc).status_code == 200       # drops "hello"
    assert client.post(f"/api/jobs/{job}/clips/1/captions", json={"preset": "pill"}).status_code == 200
    r = client.post(f"/api/jobs/{job}/clips/1/reset")
    assert r.status_code == 200, r.text
    got = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    assert got["clip"] == {"start": 0.0, "end": 2.6}
    assert [w["text"] for w in got["text"]["captions"]["words"]] == ["hello", "brave"]
    assert got["text"]["captions"]["style"]["preset"] == "pill"             # your look stays


def test_reset_needs_a_saved_original(client, folders):
    job, folder = make_job(folders[0], clip_entry())                         # made before originals were kept
    r = client.post(f"/api/jobs/{job}/clips/1/reset")
    assert r.status_code == 400 and "nothing to go back to" in r.json()["detail"]


# ---------------------------------------------------------------- the style list and saving your own

def test_the_style_list_endpoint(client):
    body = client.get("/api/styles").json()
    assert body["default"] == "natural" and [s["id"] for s in body["styles"]][:2] == ["natural", "punchy"]
    assert all({"id", "name", "description", "builtin"} <= set(s) for s in body["styles"])


def test_saving_how_a_video_was_edited_as_a_style(client, folders):
    job, folder = make_job(folders[0], clip_entry(effects={"zoom": 1.2, "pan": "none"}, fades={"in": 0.4, "out": 0.4}))
    r = client.post("/api/styles", json={"name": "Warm intro", "job_id": job, "clip_id": 1})
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["name"] == "Warm intro" and saved["effects"]["zoom"] == 1.2 and saved["fades"] == {"in": 0.4, "out": 0.4}
    assert saved["id"] in [s["id"] for s in client.get("/api/styles").json()["styles"]]
    assert client.delete(f"/api/styles/{saved['id']}").status_code == 200
    assert client.delete(f"/api/styles/{saved['id']}").status_code == 404
    assert client.delete("/api/styles/natural").status_code == 400
    assert client.post("/api/styles", json={"name": "", "job_id": job, "clip_id": 1}).status_code == 400
