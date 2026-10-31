"""Tests for the caption endpoints: looks, preview picture, restyling and word fixes.
The restyle tests use a real (tiny) video so the captions are really drawn again."""
import json
import subprocess

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import captions, captionstyles, export, jobs, main, pipeline

WORDS = [{"text": "hello", "start": 0.4, "end": 0.9}, {"text": "brave", "start": 1.0, "end": 1.5},
         {"text": "world", "start": 1.6, "end": 2.2}]


@pytest.fixture
def client(folders):
    with TestClient(main.app) as c:
        yield c


def make_job(work, music=None, captioned=True, job_id="abcdef0123"):
    """A finished job with one real 2.6 s clip, its caption-free base, and caption data."""
    folder = work / job_id
    folder.mkdir()
    (folder / "status.json").write_text(json.dumps({"status": "done"}))
    (folder / "provenance.json").write_text(json.dumps({"rights": "own", "url": None, "title": "", "uploader": ""}))
    base = export.base_path(folder / "clip_1.mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=25:d=2.6",
                    "-f", "lavfi", "-i", "sine=f=300:d=2.6", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(base)], check=True)
    style = captionstyles.resolve("clean")
    export.apply_captions(base, WORDS, style, folder / "clip_1.mp4", folder)
    clip = {"id": 1, "start": 0, "end": 2.6, "duration": 2.6, "title": "T", "music": music, "version": 0}
    if captioned:
        clip["captions"] = {"style": style.as_dict(), "words": WORDS}
    (folder / "clips.json").write_text(json.dumps({"status": "done", "note": "ok", "clips": [clip]}))
    return job_id, folder


def frame(path, t=1.2):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).astype(int)


# ---------------------------------------------------------------- looks and preview

def test_presets_endpoint(client):
    data = client.get("/api/caption-presets").json()
    assert [p["id"] for p in data["presets"]] == list(captionstyles.PRESETS)
    assert data["default"] == "clean" and "bold" in data["weights"] and data["limits"]["position"] == [20, 78]


def test_preview_is_a_png_and_follows_the_settings(client):
    a = client.get("/api/caption-preview.png?preset=clean")
    b = client.get("/api/caption-preview.png", params={"preset": "clean", "highlight_color": "#00ff00",
                                                        "size": "90", "uppercase": "true"})
    assert a.status_code == b.status_code == 200 and a.headers["content-type"] == "image/png"
    assert a.content[:4] == b"\x89PNG" and a.content != b.content


@pytest.mark.parametrize("query", ["preset=nope", "preset=clean&size=huge", "preset=clean&text_color=red",
                                   "preset=clean&weight=comic", "preset=clean&bogus=1"])
def test_preview_rejects_bad_settings(client, query):
    assert client.get(f"/api/caption-preview.png?{query}").status_code == 400


# ---------------------------------------------------------------- reading and changing captions

def test_get_captions(client, folders):
    job, _ = make_job(folders[0])
    data = client.get(f"/api/jobs/{job}/clips/1/captions").json()
    assert data["style"]["preset"] == "clean" and [w["text"] for w in data["words"]] == ["hello", "brave", "world"]


def test_clips_made_before_captions_were_editable_say_so(client, folders):
    job, _ = make_job(folders[0], captioned=False)
    assert client.get(f"/api/jobs/{job}/clips/1/captions").status_code == 409
    r = client.post(f"/api/jobs/{job}/clips/1/captions", json={"preset": "pill"})
    assert r.status_code == 400 and "Make new clips" in r.json()["detail"]


def test_changing_the_look_redraws_the_captions_and_resets_the_checklist(client, folders):
    job, folder = make_job(folders[0])
    before = frame(folder / "clip_1.mp4")
    r = client.post(f"/api/jobs/{job}/clips/1/captions", json={"preset": "bold_pop", "style": {"size": 90}})
    assert r.status_code == 200
    clip = r.json()
    assert clip["version"] == 1 and clip["captions"]["style"]["preset"] == "bold_pop"
    assert clip["captions"]["style"]["size"] == 90 and clip["confirmed"] is False
    assert np.abs(frame(folder / "clip_1.mp4") - before).mean() > 0.5       # really different pixels
    saved = json.loads((folder / "clips.json").read_text())["clips"][0]
    assert saved["captions"]["style"]["preset"] == "bold_pop"               # and it was remembered


def test_changes_without_a_preset_keep_the_current_look(client, folders):
    job, _ = make_job(folders[0])
    clip = client.post(f"/api/jobs/{job}/clips/1/captions", json={"style": {"position": 40}}).json()
    assert clip["captions"]["style"]["preset"] == "clean" and clip["captions"]["style"]["position"] == 40
    assert clip["captions"]["style"]["highlight_color"] == "#FFB84D"        # untouched settings stay


def test_fixing_words_changes_only_the_text(client, folders):
    job, folder = make_job(folders[0])
    before = frame(folder / "clip_1.mp4")
    r = client.post(f"/api/jobs/{job}/clips/1/captions", json={"words": ["hello", "bold", "world"]})
    assert r.status_code == 200
    words = r.json()["captions"]["words"]
    assert [w["text"] for w in words] == ["hello", "bold", "world"]
    assert [w["start"] for w in words] == [w["start"] for w in WORDS]       # timing untouched
    assert np.abs(frame(folder / "clip_1.mp4") - before).mean() > 0.1


@pytest.mark.parametrize("body", [
    {"words": ["only", "two"]}, {"words": ["a", "", "c"]}, {"words": ["a", "x" * 41, "c"]},
    {"preset": "neon"}, {"style": {"size": "big"}}, {"style": {"font": "Arial"}}])
def test_bad_edits_are_rejected_and_change_nothing(client, folders, body):
    job, folder = make_job(folders[0])
    before = (folder / "clips.json").read_text()
    assert client.post(f"/api/jobs/{job}/clips/1/captions", json=body).status_code == 400
    assert (folder / "clips.json").read_text() == before


def test_unknown_clip_and_job(client, folders):
    job, _ = make_job(folders[0])
    assert client.post(f"/api/jobs/{job}/clips/9/captions", json={}).status_code == 404
    assert client.post("/api/jobs/0123456789/clips/1/captions", json={}).status_code == 404


def test_busy_server_says_so_instead_of_waiting(client, folders):
    job, folder = make_job(folders[0])
    before = (folder / "clips.json").read_text()
    with pipeline.heavy_job_lock:
        r = client.post(f"/api/jobs/{job}/clips/1/captions", json={"preset": "pill"})
    assert r.status_code == 409 and "busy" in r.json()["detail"]
    assert (folder / "clips.json").read_text() == before


def test_music_is_mixed_back_in_after_a_caption_change(client, folders, monkeypatch):
    job, folder = make_job(folders[0], music={"track_id": "t1", "title": "S", "volume": 0.5, "license": "CC0",
                                              "attribution": "", "warning": None})
    mixed = []
    monkeypatch.setattr(pipeline, "set_clip_music", lambda j, c, t, v: mixed.append((c, t, v)) or
                        {"id": 1, "start": 0, "end": 2.6, "duration": 2.6, "music": None, "version": 5,
                         "captions": json.loads((folder / "clips.json").read_text())["clips"][0]["captions"]})
    r = client.post(f"/api/jobs/{job}/clips/1/captions", json={"preset": "pill"})
    assert r.status_code == 200 and mixed == [(1, "t1", 0.5)]
    assert r.json()["captions"]["style"]["preset"] == "pill"
