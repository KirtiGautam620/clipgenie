"""Phase 4 content tools: title / description / hashtags, thumbnails, script outlines.
The AI model is replaced by fakes; thumbnails use tiny generated videos (a couple of seconds)."""
import json
import subprocess
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import jobs, main, pipeline
from app.assistant import ideas, router, store, workflows
from app.content import copy as clip_copy
from app.content import script as outline
from app.content import thumbnails
from app.llm import LLMError

SAID = ("Today I show you how cooking at home saves money. Simple recipes with rice and lentils "
        "cost very little, and meal prep on Sunday makes the whole week easier.")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch, folders):
    monkeypatch.setattr(store, "ROOT", tmp_path / "assistant")
    monkeypatch.setattr(workflows, "POLL_SECONDS", 0.02)
    monkeypatch.setattr(clip_copy, "unload", lambda: None)
    monkeypatch.setattr(outline, "unload", lambda: None)
    monkeypatch.setattr(ideas, "unload", lambda: None)
    monkeypatch.setattr(router, "unload", lambda: None)

    def no_model(*a, **k):
        raise LLMError("no model in tests")
    monkeypatch.setattr(router, "ask_json", no_model)


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


def project(work, job_id="abcdef0123", clips=None, text=SAID):
    folder = work / job_id
    folder.mkdir()
    (folder / "status.json").write_text(json.dumps({"status": "done"}))
    (folder / "provenance.json").write_text(json.dumps({"rights": "own", "url": None, "title": "Kitchen talk",
                                                        "uploader": "", "declared_at": "2026-11-01T10:00:00+00:00"}))
    (folder / "transcript.json").write_text(json.dumps({"language": "en", "segments": [
        {"start": 1.0, "end": 6.0, "text": text}, {"start": 40.0, "end": 45.0, "text": "Something else entirely"}]}))
    clips = clips or [{"id": 1, "start": 0.5, "end": 8.0, "duration": 7.5, "title": "Cheap home cooking",
                       "version": 0, "text": {"mode": "captions", "verdict": "good", "reasons": [], "headline": None}}]
    (folder / "clips.json").write_text(json.dumps({"status": "done", "note": "ok", "clips": clips}))
    for c in clips:
        (folder / f"clip_{c['id']}.mp4").write_bytes(b"fake")
    return job_id, folder


def untrusted_clip(clip_id=2):
    return {"id": clip_id, "start": 0.5, "end": 8.0, "duration": 7.5, "title": f"Clip {clip_id}", "version": 0,
            "withheld": {"title": "Secret AI title from bad speech"},
            "text": {"mode": "pending", "verdict": "unreliable", "reasons": ["garbled"], "headline": None}}


def stored_clip(folder, clip_id=1):
    return next(c for c in json.loads((folder / "clips.json").read_text())["clips"] if c["id"] == clip_id)


# ---------------------------------------------------------------- checking the model's text

def test_hashtags_must_be_made_of_words_said_in_the_clip():
    words = clip_copy._tokens(SAID)
    for tag in ("#cooking", "#cook", "#homecooking", "#mealprep", "#recipes", "#rice", "#shorts"):
        assert clip_copy.grounded_tag(tag, words), tag
    for tag in ("#fitness", "#viral", "#fyp", "#keto", "#ai"):
        assert not clip_copy.grounded_tag(tag, words), tag


def test_a_draft_is_tidied_limited_and_keeps_only_grounded_hashtags():
    raw = {"title": "  How   home cooking saves money " + "x" * 200, "description": "Rice and lentils on a budget.",
           "hashtags": ["#Cooking", "Meal Prep", "#viral", "#cooking", "#fyp", "#lentils!"]}
    out = clip_copy.check_draft(raw, SAID)
    assert len(out["title"]) == clip_copy.TITLE_MAX and "  " not in out["title"]
    assert out["hashtags"] == ["#cooking", "#mealprep", "#lentils", "#shorts"]


def test_a_draft_with_links_or_mentions_is_not_used():
    with pytest.raises(ValueError):
        clip_copy.check_draft({"title": "Watch at https://spam.example", "hashtags": []}, SAID)
    out = clip_copy.check_draft({"title": "Home cooking on a budget", "description": "Follow @someone for more",
                                 "hashtags": []}, SAID)
    assert out["description"] == "" and out["hashtags"] == ["#shorts"]
    with pytest.raises(ValueError):
        clip_copy.check_draft("not json", SAID)


def test_the_users_own_text_is_kept_as_typed_but_limited():
    out = clip_copy.check_user_copy({"title": " My title ", "description": "Line one\nLine two",
                                     "hashtags": ["anything", "#Goes", "#goes"] + [f"#t{i}" for i in range(20)]})
    assert out["title"] == "My title" and out["description"] == "Line one\nLine two"
    assert out["hashtags"][:2] == ["#anything", "#goes"] and len(out["hashtags"]) <= clip_copy.HASHTAGS_MAX
    with pytest.raises(ValueError):
        clip_copy.check_user_copy({"title": "   "})


# ---------------------------------------------------------------- title / description / hashtags endpoints

def test_suggest_with_ai_writes_a_draft_from_the_clips_own_words(client, folders, monkeypatch):
    job_id, folder = project(folders[0])
    asked = []

    def fake(system, user, timeout=0):
        asked.append(user)
        return {"title": "Cooking at home saves money", "description": "Rice and lentils, prepped on Sunday.",
                "hashtags": ["#cooking", "#budget", "#mealprep"]}
    monkeypatch.setattr(clip_copy, "ask_json", fake)
    r = client.post(f"/api/jobs/{job_id}/clips/1/copy/draft")
    assert r.status_code == 200, r.text
    copy = r.json()["copy"]
    assert copy["source"] == "ai" and copy["approved"] is False
    assert copy["hashtags"] == ["#cooking", "#mealprep", "#shorts"]         # "#budget" was never said
    assert "cooking at home" in asked[0] and "Something else entirely" not in asked[0]   # only this clip's words
    assert stored_clip(folder)["copy"] == copy and stored_clip(folder)["version"] == 0
    assert not pipeline.heavy_job_lock.locked()


def test_no_ai_text_for_a_clip_whose_speech_was_not_trusted(client, folders, monkeypatch):
    job_id, _ = project(folders[0], clips=[untrusted_clip(1)])
    monkeypatch.setattr(clip_copy, "ask_json", lambda *a, **k: pytest.fail("the model must not be asked"))
    r = client.post(f"/api/jobs/{job_id}/clips/1/copy/draft")
    assert r.status_code == 409 and "couldn't be trusted" in r.json()["detail"]
    assert client.get(f"/api/jobs/{job_id}/clips/1/copy").json()["can_draft"] is False


def test_suggest_waits_for_nothing_while_a_video_is_being_made(client, folders, monkeypatch):
    job_id, _ = project(folders[0])
    monkeypatch.setattr(clip_copy, "ask_json", lambda *a, **k: pytest.fail("the model must not be asked"))
    with pipeline.heavy_job_lock:
        r = client.post(f"/api/jobs/{job_id}/clips/1/copy/draft")
    assert r.status_code == 409 and "busy" in r.json()["detail"]


def test_a_missing_model_is_reported_plainly(client, folders, monkeypatch):
    job_id, _ = project(folders[0])

    def down(*a, **k):
        raise LLMError("connection refused")
    monkeypatch.setattr(clip_copy, "ask_json", down)
    r = client.post(f"/api/jobs/{job_id}/clips/1/copy/draft")
    assert r.status_code == 503 and "isn't running" in r.json()["detail"]
    assert not pipeline.heavy_job_lock.locked()


def test_saving_your_text_approves_it_without_changing_the_video(client, folders):
    job_id, folder = project(folders[0])
    clip = client.get(f"/api/jobs/{job_id}/clips").json()["clips"][0]
    client.post(f"/api/jobs/{job_id}/clips/1/checklist", json={"items": [i["id"] for i in clip["checklist"]]})
    r = client.put(f"/api/jobs/{job_id}/clips/1/copy", json={"title": "My own title", "description": "Hi",
                                                             "hashtags": ["#mine"]})
    assert r.status_code == 200
    assert r.json()["copy"] == {"title": "My own title", "description": "Hi", "hashtags": ["#mine"],
                                "source": "user", "approved": True}
    after = client.get(f"/api/jobs/{job_id}/clips").json()["clips"][0]
    assert after["version"] == 0 and after["confirmed"] is True                    # still the same video
    assert client.put(f"/api/jobs/{job_id}/clips/1/copy", json={"title": ""}).status_code == 400


def test_thumbnail_text_never_comes_from_untrusted_speech(folders):
    clip = untrusted_clip()
    assert clip_copy.headline_text(clip) == ""
    clip["copy"] = {"title": "Typed by me", "approved": True}
    assert clip_copy.headline_text(clip) == "Typed by me"
    assert clip_copy.headline_text({"id": 1, "title": "Cheap home cooking"}) == "Cheap home cooking"
    assert clip_copy.headline_text({"id": 1, "title": "Clip 1"}) == ""


# ---------------------------------------------------------------- thumbnails

def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture
def video_project(folders):
    """A clip with a real (tiny) picture: 3 s of a test pattern, and a 16:9 source."""
    job_id, folder = project(folders[0])
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=270x480:rate=10:duration=3", "-pix_fmt", "yuv420p",
           str(folder / "clip_1_base.mp4"))
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=10:duration=9", "-pix_fmt", "yuv420p",
           str(folder / "source.mp4"))
    return job_id, folder


def test_black_and_blurry_frames_score_low():
    black = Image.new("RGB", (270, 480), (0, 0, 0))
    flat = Image.new("RGB", (270, 480), (120, 130, 125))
    import numpy as np
    detail = np.random.default_rng(1).integers(60, 190, (480, 270, 3), dtype=np.uint8)   # sharp, mid brightness
    pattern = Image.fromarray(detail)
    assert thumbnails.score(black)["score"] < thumbnails.score(flat)["score"] < thumbnails.score(pattern)["score"]


def test_the_best_frames_are_found_spread_out_and_saved(client, video_project):
    job_id, folder = video_project
    r = client.post(f"/api/jobs/{job_id}/clips/1/thumbnails/frames")
    assert r.status_code == 200, r.text
    frames = r.json()["frames"]
    assert 1 <= len(frames) <= thumbnails.KEEP
    times = sorted(f["t"] for f in frames)
    assert all(b - a >= thumbnails.MIN_GAP for a, b in zip(times, times[1:]))
    assert [f["score"] for f in frames] == sorted((f["score"] for f in frames), reverse=True)
    assert client.get(f"/api/jobs/{job_id}/clips/1/thumbnails/frames/0.jpg").status_code == 200
    assert not list((folder / "thumbs" / "clip_1").glob("sample_*"))            # working files cleaned up


def test_both_thumbnail_sizes_are_made_with_the_text(client, video_project):
    job_id, folder = video_project
    client.post(f"/api/jobs/{job_id}/clips/1/thumbnails/frames")
    r = client.post(f"/api/jobs/{job_id}/clips/1/thumbnails", json={"frame": 0, "text": "", "preset": "poster"})
    assert r.status_code == 200, r.text
    out = folder / "thumbs" / "clip_1"
    plain = {s: Image.open(out / f"thumbnail_{s}.png").convert("RGB") for s in thumbnails.SIZES}
    assert plain["9x16"].size == (1080, 1920) and plain["16x9"].size == (1280, 720)
    r = client.post(f"/api/jobs/{job_id}/clips/1/thumbnails", json={"frame": 0, "text": "Cheap home cooking",
                                                                    "preset": "banner"})
    assert r.status_code == 200 and r.json()["chosen"]["text"] == "Cheap home cooking"
    with_text = Image.open(out / "thumbnail_9x16.png").convert("RGB")
    diff = sum(abs(a - b) for a, b in zip(plain["9x16"].tobytes()[::97], with_text.tobytes()[::97]))
    assert diff > 0                                                                # the text is drawn
    assert stored_clip(folder)["version"] == 0                                    # the video is unchanged
    assert client.post(f"/api/jobs/{job_id}/clips/1/thumbnails", json={"frame": 9}).status_code == 400
    assert client.post(f"/api/jobs/{job_id}/clips/1/thumbnails",
                       json={"frame": 0, "preset": "nope"}).status_code == 400


def test_a_thumbnail_download_needs_the_copyright_checklist(client, video_project):
    job_id, _ = video_project
    client.post(f"/api/jobs/{job_id}/clips/1/thumbnails/frames")
    client.post(f"/api/jobs/{job_id}/clips/1/thumbnails", json={"frame": 0, "text": "Hi"})
    assert client.get(f"/api/jobs/{job_id}/clips/1/thumbnails/9x16.png").status_code == 200    # preview is fine
    assert client.get(f"/api/jobs/{job_id}/clips/1/thumbnails/9x16/download").status_code == 403
    clip = client.get(f"/api/jobs/{job_id}/clips").json()["clips"][0]
    client.post(f"/api/jobs/{job_id}/clips/1/checklist", json={"items": [i["id"] for i in clip["checklist"]]})
    r = client.get(f"/api/jobs/{job_id}/clips/1/thumbnails/16x9/download")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]


def test_frames_are_found_again_after_the_clip_is_edited(client, video_project):
    job_id, folder = video_project
    client.post(f"/api/jobs/{job_id}/clips/1/thumbnails/frames")
    client.post(f"/api/jobs/{job_id}/clips/1/thumbnails", json={"frame": 0})
    data = json.loads((folder / "clips.json").read_text())
    data["clips"][0]["version"] = 1                                               # an edit made a new version
    (folder / "clips.json").write_text(json.dumps(data))
    view = client.get(f"/api/jobs/{job_id}/clips/1/thumbnails").json()
    assert view["frames"] == [] and view["outdated"] is True
    assert client.post(f"/api/jobs/{job_id}/clips/1/thumbnails", json={"frame": 0}).status_code == 400


def test_the_wide_thumbnail_comes_from_the_same_moment_of_the_source():
    m = {"segments": [{"start": 10.0, "end": 12.0}, {"start": 20.0, "end": 25.0}]}
    from app import manifest
    assert manifest.source_time(m, 0.5) == 10.5
    assert manifest.source_time(m, 3.0) == 21.0
    assert manifest.source_time(m, 99) == 25.0


# ---------------------------------------------------------------- script outlines

def test_an_outline_is_checked():
    good = outline.check_outline({"hook": "Cooking at home is cheaper than you think",
                                  "points": ["Rice and lentils cost little", "Prep on Sunday", "Cook once, eat twice", "x"],
                                  "closing": "Try it this week"})
    assert len(good["points"]) == 3                                                # too-short points dropped
    with pytest.raises(ValueError):
        outline.check_outline({"hook": "Hi", "points": ["only one point here"]})


def ideas_card(client, folders, monkeypatch):
    job_id, _ = project(folders[0])
    monkeypatch.setattr(ideas, "ask_json", lambda *a, **k: {"ideas": [
        {"title": "Cheap meal prep", "angle": "A week of meals from rice and lentils",
         "based_on": "Simple recipes with rice and lentils cost very little", "why": "You said it"}]})
    out = client.post("/api/assistant/messages", json={"text": "Give me ideas for my next video"}).json()
    wf = wait(client, out["workflow"]["id"])
    assert wf["status"] == "done", wf
    return out["conversation"]["id"], wf


def wait(client, wf_id, seconds=5):
    end = time.time() + seconds
    while time.time() < end:
        wf = client.get(f"/api/assistant/workflows/{wf_id}").json()
        if wf["status"] in ("done", "error"):
            return wf
        time.sleep(0.03)
    raise AssertionError("workflow did not finish")


def test_draft_a_script_from_an_idea(client, folders, monkeypatch):
    conv_id, ideas_wf = ideas_card(client, folders, monkeypatch)
    asked = []

    def fake(system, user, timeout=0):
        asked.append(user)
        return {"hook": "What if a week of food cost less than one takeaway?",
                "points": ["Why rice and lentils", "What to cook on Sunday", "How to store it"],
                "closing": "Try it and tell me how it went."}
    monkeypatch.setattr(outline, "ask_json", fake)
    r = client.post(f"/api/assistant/workflows/{ideas_wf['id']}/script", json={"index": 0})
    assert r.status_code == 200, r.text
    conv = r.json()["conversation"]
    assert conv["id"] == conv_id and conv["messages"][-1]["workflow_id"] == r.json()["workflow"]["id"]
    wf = wait(client, r.json()["workflow"]["id"])
    assert wf["status"] == "done" and wf["result"]["hook"].startswith("What if")
    assert "Cheap meal prep" in asked[0] and "rice and lentils" in asked[0]
    assert not pipeline.heavy_job_lock.locked()
    assert client.post(f"/api/assistant/workflows/{ideas_wf['id']}/script", json={"index": 5}).status_code == 400
    assert client.post(f"/api/assistant/workflows/{wf['id']}/script", json={"index": 0}).status_code == 400


# ---------------------------------------------------------------- the assistant

def test_write_titles_drafts_only_the_trusted_clips(client, folders, monkeypatch):
    good = {"id": 1, "start": 0.5, "end": 8.0, "duration": 7.5, "title": "Cheap home cooking", "version": 0,
            "text": {"mode": "captions", "verdict": "good", "reasons": [], "headline": None}}
    job_id, folder = project(folders[0], clips=[good, untrusted_clip(2)])
    monkeypatch.setattr(clip_copy, "ask_json", lambda *a, **k: {
        "title": "Cooking at home saves money", "description": "", "hashtags": ["#cooking"]})
    out = client.post("/api/assistant/messages", json={"text": "Write titles and hashtags for my clips"}).json()
    assert out["workflow"]["tool"] == "write_copy"
    wf = wait(client, out["workflow"]["id"])
    assert wf["status"] == "done", wf
    assert [d["id"] for d in wf["result"]["drafts"]] == [1]
    assert "1 skipped" in wf["steps"][0]["detail"]
    assert "copy" not in stored_clip(folder, 2)


def test_create_a_thumbnail_lists_the_clips_of_the_last_project(client, folders):
    job_id, _ = project(folders[0])
    out = client.post("/api/assistant/messages", json={"text": "Create a thumbnail for my last video"}).json()
    wf = out["workflow"]
    assert wf["tool"] == "create_thumbnail" and wf["status"] == "done"
    assert wf["job_id"] == job_id and [c["id"] for c in wf["result"]["clips"]] == [1]


def test_making_shorts_with_titles_is_still_making_clips():
    assert router.route("Make 5 shorts with titles", use_model=False)["tool"] == "make_clips"
    assert router.route("write a title for my clip", use_model=False)["tool"] == "write_copy"
