"""Extending a clip at its end: the footage after it is used, and the captions said there are added."""
import json

from app import manifest
from tests.test_render import client, clip_entry, fixture_video, make_job  # noqa: F401 (the client fixture)

# what was said in the source video, in source seconds (the clip itself is 0.0 to 2.6)
TRANSCRIPT = {"language": "en", "asr": "test", "dropped": 0, "segments": [{"words": [
    {"word": "hello", "start": 0.4, "end": 0.9},
    {"word": "brave", "start": 1.0, "end": 1.5},
    {"word": "new", "start": 2.7, "end": 3.0},
    {"word": "world.", "start": 3.1, "end": 3.6},
    {"word": "again", "start": 4.0, "end": 4.4},
]}]}


def extended_job(folders, seconds=10):
    job, folder = make_job(folders[0], clip_entry())
    fixture_video(folder / "source.mp4", seconds=seconds)          # footage longer than the clip
    (folder / "transcript.json").write_text(json.dumps(TRANSCRIPT))
    return job, folder


def test_extend_to_the_end_of_the_sentence(client, folders):
    job, folder = extended_job(folders)
    r = client.post(f"/api/jobs/{job}/clips/1/extend", json={"to_sentence": True})
    assert r.status_code == 200, r.text
    m = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    assert m["clip"]["end"] == 3.8                                  # "world." ends at 3.6, plus a short pause
    assert [w["text"] for w in m["text"]["captions"]["words"]] == ["hello", "brave", "new", "world."]
    added = m["text"]["captions"]["words"][2:]
    assert abs(added[0]["start"] - 2.7) < 0.02                       # "new" at 2.7 s, counted from the clip start
    assert r.json()["version"] == 1
    assert abs(r.json()["duration"] - 3.8) < 0.2


def test_extend_by_seconds_adds_the_words_said_in_that_time(client, folders):
    job, folder = extended_job(folders)
    r = client.post(f"/api/jobs/{job}/clips/1/extend", json={"seconds": 2})
    assert r.status_code == 200, r.text
    m = client.get(f"/api/jobs/{job}/clips/1/manifest").json()
    assert m["clip"]["end"] == 4.6
    assert [w["text"] for w in m["text"]["captions"]["words"]] == ["hello", "brave", "new", "world.", "again"]


def test_extend_is_refused_beyond_the_limit_or_without_a_choice(client, folders):
    job, folder = extended_job(folders)
    assert client.post(f"/api/jobs/{job}/clips/1/extend", json={"seconds": 20}).status_code == 400
    assert client.post(f"/api/jobs/{job}/clips/1/extend", json={}).status_code == 400


def test_extend_stops_at_the_end_of_the_source(client, folders):
    job, folder = extended_job(folders, seconds=3)
    r = client.post(f"/api/jobs/{job}/clips/1/extend", json={"seconds": 15})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/jobs/{job}/clips/1/manifest").json()["clip"]["end"] <= 3.0 + 0.01
    r2 = client.post(f"/api/jobs/{job}/clips/1/extend", json={"seconds": 2})
    assert r2.status_code == 400 and "end of the source" in r2.text


def test_a_clip_without_captions_is_extended_without_text(client, folders):
    clip = clip_entry(text={"mode": "none", "verdict": "reliable", "reasons": [], "headline": None})
    clip.pop("captions")
    job, folder = make_job(folders[0], clip, build=False)
    fixture_video(folder / "source.mp4", seconds=10)
    (folder / "transcript.json").write_text(json.dumps(TRANSCRIPT))
    r = client.post(f"/api/jobs/{job}/clips/1/extend", json={"seconds": 2})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/jobs/{job}/clips/1/manifest").json()["clip"]["end"] == 4.6
