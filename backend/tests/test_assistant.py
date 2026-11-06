"""The creator assistant: routing a request to a real tool, plans that wait for Start, workflows that
run the real pipeline and report progress, grounded video ideas, and honest "not yet" answers.
Nothing here runs Whisper, the AI model or FFmpeg: those parts are replaced by fakes at their edges."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import jobs, main, pipeline, projects
from app.assistant import ideas, router, store, tools, workflows
from app.llm import LLMError

YT = "https://www.youtube.com/watch?v=abc123XYZ"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch, folders):
    monkeypatch.setattr(store, "ROOT", tmp_path / "assistant")
    monkeypatch.setattr(workflows, "POLL_SECONDS", 0.02)

    def no_model(*a, **k):
        raise LLMError("no model in tests")
    monkeypatch.setattr(router, "ask_json", no_model)
    monkeypatch.setattr(router, "unload", lambda: None)
    monkeypatch.setattr(ideas, "unload", lambda: None)


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


def say(client, text, **extra):
    r = client.post("/api/assistant/messages", json={"text": text, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def wait_for(client, wf_id, statuses=("done", "error"), seconds=5):
    end = time.time() + seconds
    while time.time() < end:
        wf = client.get(f"/api/assistant/workflows/{wf_id}").json()
        if wf["status"] in statuses:
            return wf
        time.sleep(0.03)
    raise AssertionError(f"workflow still {wf['status']}")


def fake_pipeline(calls, *, fail=False):
    """Stands in for the real pipeline: walks the job through its statuses and writes one clip."""
    def run(job_id, *args):
        calls.append((job_id, args))
        for status, progress in (("queued", None), ("transcribing", None), ("choosing", None),
                                 ("exporting", "Clip 1 of 1")):
            jobs.set_status(job_id, status, **({"progress": progress} if progress else {}))
            time.sleep(0.03)
        if fail:
            jobs.set_status(job_id, "error", error="ffmpeg failed: simulated")
            return
        clip = {"id": 1, "start": 0, "end": 20, "duration": 20, "title": "Best moment", "version": 0,
                "checks": {"status": "ok", "issues": []}}
        (jobs.job_dir(job_id) / "clips.json").write_text(json.dumps({"status": "done", "note": "ok", "clips": [clip]}))
        jobs.set_status(job_id, "done", language="en", note="ok")
    return run


def existing_project(work, job_id="abcdef0123", title="My podcast", text=None):
    folder = work / job_id
    folder.mkdir()
    (folder / "status.json").write_text(json.dumps({"status": "done"}))
    (folder / "provenance.json").write_text(json.dumps({"rights": "own", "url": None, "title": title, "uploader": "",
                                                        "declared_at": "2026-11-01T10:00:00+00:00"}))
    segments = [{"start": 0, "end": 5, "text": text or "Today we talk about saving money on groceries every week"},
                {"start": 5, "end": 10, "text": "and why cooking at home with simple recipes changes your budget"}]
    (folder / "transcript.json").write_text(json.dumps({"language": "en", "segments": segments}))
    (folder / "clips.json").write_text(json.dumps({"status": "done", "note": "ok", "clips": []}))
    return job_id, folder


# ---------------------------------------------------------------- tools

def test_the_shortcuts_are_listed_and_only_real_ones_are_available():
    listing = tools.listing()
    assert [t["title"] for t in listing] == ["Get more views", "Channel audit", "Create thumbnail", "Write titles",
                                             "Video ideas", "Make clips", "Find B-roll", "AI voiceover", "Compose video"]
    assert {t["name"] for t in listing if t["available"]} == {"make_clips", "video_ideas", "create_thumbnail",
                                                               "write_copy"}
    assert all(t["reason"] for t in listing if not t["available"])             # every "Soon" says why


# ---------------------------------------------------------------- the router

@pytest.mark.parametrize("text, tool", [
    ("Turn my 30-minute podcast into 5 Shorts", "make_clips"),
    ("make clips from this", "make_clips"),
    (f"{YT}", "make_clips"),
    ("Give me ideas for my next YouTube video", "video_ideas"),
    ("what should I make next?", "video_ideas"),
    ("create a thumbnail for my video", "create_thumbnail"),
    ("find some b-roll", "find_broll"),
    ("add an AI voiceover", "ai_voiceover"),
    ("audit my channel", "channel_audit"),
    ("how do I get more views", "get_more_views"),
    ("compose a video from my photos", "compose_video"),
    ("hello there", None),
])
def test_requests_are_routed_by_fixed_rules(text, tool):
    assert router.route(text, use_model=False)["tool"] == tool


def test_the_router_reads_links_numbers_styles_and_wishes():
    args = router.route(f"Make five punchy shorts from {YT} please", use_model=False)["args"]
    assert args == {"url": YT, "count": 5, "edit_mode": "custom", "style_id": "punchy"}
    assert router.extract_args("10 clips, I'll edit them myself, from my last video")["edit_mode"] == "assist"
    assert router.extract_args("clips from my last video")["project"] == "latest"
    assert "count" not in router.extract_args("make 40 clips")                  # out of range: not taken
    assert router.extract_args("3 short vertical clips")["count"] == 3
    assert "count" not in router.extract_args("my 30-minute podcast")          # a length, not a number of clips
    assert router.route("", has_attachment=True, use_model=False)["tool"] == "make_clips"


def test_the_model_is_asked_only_when_the_rules_find_nothing_and_its_answer_is_checked(monkeypatch):
    asked = []
    monkeypatch.setattr(router, "ask_json", lambda s, u, timeout=60: asked.append(u) or {"tool": "video_ideas"})
    assert router.route("help me plan what to film this month", use_model=True) == {"tool": "video_ideas", "args": {}, "how": "model"}
    assert router.route("make 3 shorts", use_model=True)["how"] == "rules" and len(asked) == 1   # rules first
    monkeypatch.setattr(router, "ask_json", lambda s, u, timeout=60: {"tool": "delete_everything"})
    assert router.route("do the thing with the stuff", use_model=True)["tool"] is None          # not a real tool


# ---------------------------------------------------------------- ideas are grounded

def test_ideas_must_quote_the_transcript(monkeypatch):
    segments = [{"start": 0, "end": 5, "text": "Today we talk about saving money on groceries every week"}]
    monkeypatch.setattr(ideas, "ask_json", lambda s, u, timeout=240: {"ideas": [
        {"title": "Cheap weekly grocery plan", "angle": "A full week of shopping", "why": "They asked",
         "based_on": "saving money on groceries every week"},
        {"title": "Crypto riches for beginners", "angle": "Invest now", "why": "Trending",
         "based_on": "the stock market will triple"},                          # never said: dropped
        {"title": "x", "angle": "too short a title", "why": "", "based_on": "saving money"}]})   # bad title: dropped
    found = ideas.suggest(segments * 3)
    assert [i["title"] for i in found] == ["Cheap weekly grocery plan"]


def test_too_little_speech_gives_no_ideas_and_the_excerpt_spans_the_video():
    assert ideas.suggest([{"start": 0, "end": 1, "text": "hi"}]) == []
    long = [{"start": i, "end": i + 1, "text": f"sentence number {i} " + "word " * 20} for i in range(400)]
    text = ideas.excerpt(long)
    numbers = [int(n) for n in __import__("re").findall(r"sentence number (\d+)", text)]
    assert len(text) <= ideas.EXCERPT_CHARS and numbers[0] == 0 and numbers[-1] > 300   # from start to near the end


# ---------------------------------------------------------------- conversations and honest answers

def test_a_tool_that_is_not_built_says_why_and_starts_nothing(client):
    out = say(client, "find b-roll for my video")
    assert out["workflow"] is None and "isn't available yet" in out["reply"] and "stock footage" in out["reply"]


def test_a_thumbnail_without_any_clips_says_so_and_starts_nothing(client):
    out = say(client, "make me a thumbnail")
    assert out["workflow"] is None and "finished clips" in out["reply"]


def test_an_unclear_request_gets_help_not_an_invented_answer(client):
    out = say(client, "hmm")
    assert out["workflow"] is None and "make clips" in out["reply"]


def test_the_conversation_is_kept(client):
    first = say(client, "make me a thumbnail")
    second = say(client, "find b-roll", conversation_id=first["conversation"]["id"])
    conv = client.get(f"/api/assistant/conversations/{first['conversation']['id']}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant", "user", "assistant"]
    assert second["conversation"]["id"] == first["conversation"]["id"]
    assert client.get("/api/assistant/conversations/zzz").status_code == 404


def test_asking_for_clips_without_a_video_asks_which_video(client):
    out = say(client, "make 5 shorts")
    assert out["workflow"] is None and "Which video" in out["reply"]


# ---------------------------------------------------------------- Make clips: plan, confirm, run

def test_a_youtube_link_becomes_a_plan_that_waits_for_start(client, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "run_pipeline", fake_pipeline(calls))
    out = say(client, f"Turn {YT} into 3 punchy shorts")
    wf = out["workflow"]
    assert wf["status"] == "awaiting_confirmation" and wf["needs_rights"] is True and calls == []
    assert wf["args"] == {"count": 3, "edit_mode": "custom", "style_id": "punchy"}
    # who owns it must be said, and "not sure" cannot import from a link
    assert client.post(f"/api/assistant/workflows/{wf['id']}/confirm", json={}).status_code == 400
    assert client.post(f"/api/assistant/workflows/{wf['id']}/confirm", json={"rights": "unsure"}).status_code == 400
    r = client.post(f"/api/assistant/workflows/{wf['id']}/confirm", json={"rights": "own", "count": 2})
    assert r.status_code == 200, r.text
    done = wait_for(client, wf["id"])
    assert done["status"] == "done" and [s["status"] for s in done["steps"]] == ["done"] * 5
    assert done["result"]["clips"][0]["title"] == "Best moment" and done["steps"][-1]["detail"] == "1 of 1 passed every check"
    job_id, args = calls[0]
    language, settings, url = args
    assert url == YT and settings["count"] == 2 and settings["style_id"] == "punchy" and settings["rights"] == "own"
    assert json.loads((jobs.job_dir(job_id) / "provenance.json").read_text())["rights"] == "own"


def test_an_uploaded_video_waits_in_the_chat_until_the_plan_is_started(client, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "run_pipeline", fake_pipeline(calls))
    up = client.post("/api/assistant/upload", files={"file": ("talk.mp4", b"not really a video", "video/mp4")}).json()
    assert jobs.get_status(up["job_id"])["status"] == "waiting" and calls == []        # nothing started
    out = say(client, "make 4 clips", attachment_job_id=up["job_id"])
    assert out["workflow"]["source"] == {"kind": "upload", "job_id": up["job_id"], "filename": "talk.mp4"}
    client.post(f"/api/assistant/workflows/{out['workflow']['id']}/confirm", json={"rights": "permission"})
    done = wait_for(client, out["workflow"]["id"])
    assert done["status"] == "done" and calls[0][0] == up["job_id"] and calls[0][1][1]["count"] == 4
    assert client.post("/api/assistant/upload", files={"file": ("x.mov", b"x", "video/quicktime")}).status_code == 400


def test_clips_from_the_last_video_go_into_a_new_project_and_the_old_videos_stay(client, folders, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "run_clips_only", fake_pipeline(calls))
    job, folder = existing_project(folders[0])
    (folder / "source.mp4").write_bytes(b"the original video")
    (folder / "audio.wav").write_bytes(b"its audio")
    (folder / "clips.json").write_text(json.dumps({"status": "done", "clips": [{"id": 1, "title": "Keep me"}]}))
    (folder / "clip_1.mp4").write_bytes(b"a finished video the user already has")
    before = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}

    out = say(client, "make 2 more shorts from my last video")
    wf = out["workflow"]
    assert wf["source"]["kind"] == "project" and wf["source"]["job_id"] == job and wf["needs_rights"] is False
    assert wf["warning"] == "" and "new project" in wf["note"] and "new project" in out["reply"]
    client.post(f"/api/assistant/workflows/{wf['id']}/confirm", json={})
    done = wait_for(client, wf["id"])
    new_job = calls[0][0]
    assert done["status"] == "done" and new_job != job and done["job_id"] == new_job
    assert {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()} == before     # the original is untouched
    new = jobs.job_dir(new_job)
    assert (new / "source.mp4").stat().st_ino == (folder / "source.mp4").stat().st_ino     # shared, no extra disk
    assert json.loads((new / "transcript.json").read_text()) == json.loads((folder / "transcript.json").read_text())
    assert json.loads((new / "meta.json").read_text())["derived_from"] == job
    assert json.loads((new / "provenance.json").read_text())["rights"] == "own"             # the declaration carries over
    assert [s["status"] for s in done["steps"]][1] == "skipped"                              # no need to transcribe again


def test_a_new_project_cannot_be_made_from_a_project_without_its_video(client, folders, monkeypatch):
    monkeypatch.setattr(pipeline, "run_clips_only", fake_pipeline([]))
    existing_project(folders[0])                                    # has a transcript but no source.mp4
    wf = say(client, "shorts from my last video")["workflow"]
    r = client.post(f"/api/assistant/workflows/{wf['id']}/confirm", json={})
    assert r.status_code == 400 and "no longer on this computer" in r.json()["detail"]
    assert client.get(f"/api/assistant/workflows/{wf['id']}").json()["status"] == "awaiting_confirmation"


def test_a_failed_job_is_reported_as_failed(client, monkeypatch):
    monkeypatch.setattr(pipeline, "run_pipeline", fake_pipeline([], fail=True))
    wf = say(client, f"shorts from {YT}")["workflow"]
    client.post(f"/api/assistant/workflows/{wf['id']}/confirm", json={"rights": "own"})
    done = wait_for(client, wf["id"])
    assert done["status"] == "error" and "simulated" in done["error"]
    assert "error" in [s["status"] for s in done["steps"]]


def test_a_plan_can_be_cancelled_and_then_never_starts(client, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "run_pipeline", fake_pipeline(calls))
    wf = say(client, f"5 shorts from {YT}")["workflow"]
    assert client.post(f"/api/assistant/workflows/{wf['id']}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/api/assistant/workflows/{wf['id']}/confirm", json={"rights": "own"}).status_code == 400
    assert calls == []
    assert client.get("/api/assistant/workflows/nope").status_code == 404


def test_bad_choices_on_the_plan_are_refused(client):
    wf = say(client, f"shorts from {YT}")["workflow"]
    for bad in ({"rights": "own", "count": 0}, {"rights": "own", "edit_mode": "magic"},
                {"rights": "own", "edit_mode": "custom", "style_id": "u-missing"}):
        assert client.post(f"/api/assistant/workflows/{wf['id']}/confirm", json=bad).status_code == 400
    assert client.get(f"/api/assistant/workflows/{wf['id']}").json()["status"] == "awaiting_confirmation"


# ---------------------------------------------------------------- Video ideas

def test_video_ideas_come_from_the_last_video(client, folders, monkeypatch):
    existing_project(folders[0])
    monkeypatch.setattr(ideas, "ask_json", lambda s, u, timeout=240: {"ideas": [
        {"title": "A week of meals for very little", "angle": "Plan, shop, cook", "why": "Budget questions",
         "based_on": "cooking at home with simple recipes"}]})
    out = say(client, "Give me ideas for my next YouTube video")
    assert "My podcast" in out["reply"] and out["workflow"]["status"] == "running"
    done = wait_for(client, out["workflow"]["id"])
    assert done["status"] == "done" and done["result"]["ideas"][0]["title"] == "A week of meals for very little"
    assert "doesn't use YouTube search or trend data" in done["result"]["note"]
    assert [s["status"] for s in done["steps"]] == ["done", "done", "done"]


def test_ideas_without_any_video_ask_for_one(client):
    out = say(client, "give me video ideas")
    assert out["workflow"] is None and "need one of your videos" in out["reply"]


def test_ideas_when_the_model_is_down_say_so(client, folders, monkeypatch):
    existing_project(folders[0])

    def down(*a, **k):
        raise LLMError("no ollama")
    monkeypatch.setattr(ideas, "ask_json", down)
    done = wait_for(client, say(client, "video ideas please")["workflow"]["id"])
    assert done["status"] == "error" and "isn't running" in done["error"]


def test_ideas_that_cannot_be_tied_to_the_video_are_not_shown(client, folders, monkeypatch):
    existing_project(folders[0])
    monkeypatch.setattr(ideas, "ask_json", lambda s, u, timeout=240: {"ideas": [
        {"title": "Get rich with crypto today", "angle": "x", "why": "y", "based_on": "the moon is made of cheese"}]})
    done = wait_for(client, say(client, "ideas for my next video")["workflow"]["id"])
    assert done["status"] == "error" and "couldn't come up with ideas" in done["error"]


def test_ideas_wait_for_a_heavy_job_to_finish(client, folders, monkeypatch):
    existing_project(folders[0])
    monkeypatch.setattr(ideas, "ask_json", lambda s, u, timeout=240: {"ideas": [
        {"title": "A week of meals for very little", "angle": "a", "why": "b", "based_on": "simple recipes changes your budget"}]})
    with pipeline.heavy_job_lock:                      # a video is being made
        wf = say(client, "ideas please")["workflow"]
        time.sleep(0.2)
        assert client.get(f"/api/assistant/workflows/{wf['id']}").json()["status"] == "running"
    assert wait_for(client, wf["id"])["status"] == "done"


# ---------------------------------------------------------------- projects and restarts

def test_projects_are_listed_newest_first(client, folders):
    existing_project(folders[0], "abcdef0123", "Older")
    job2, folder2 = existing_project(folders[0], "bbbbbbbbbb", "Newer")
    (folder2 / "meta.json").write_text(json.dumps({"owner_id": "local", "created_at": "2026-11-05T10:00:00+00:00"}))
    got = client.get("/api/projects").json()["projects"]
    assert [p["title"] for p in got] == ["Newer", "Older"] and got[0]["has_transcript"] is True
    assert projects.latest_with_transcript()["job_id"] == job2


def test_after_a_restart_an_unfinished_ideas_run_is_marked_as_interrupted(folders):
    store.save("workflows", {"id": "aaaaaaaaaaaa", "tool": "video_ideas", "status": "running", "steps": []})
    assert workflows.mark_interrupted() == 1
    assert "interrupted" in workflows.get("aaaaaaaaaaaa")["error"]


# ---------------------------------------------------------------- after a restart, plans and uploads are safe

def test_a_chat_upload_and_its_plan_survive_a_restart(client, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "run_pipeline", fake_pipeline(calls))
    up = client.post("/api/assistant/upload", files={"file": ("talk.mp4", b"video bytes", "video/mp4")}).json()
    wf = say(client, "make 3 clips", attachment_job_id=up["job_id"])["workflow"]
    assert jobs.get_status(up["job_id"])["status"] == "waiting"
    # the server restarts
    assert jobs.mark_interrupted() == 0 and workflows.mark_interrupted() == 0
    assert jobs.get_status(up["job_id"])["status"] == "waiting"                 # not marked as failed
    assert (jobs.job_dir(up["job_id"]) / "source.mp4").read_bytes() == b"video bytes"
    assert client.get(f"/api/assistant/workflows/{wf['id']}").json()["status"] == "awaiting_confirmation"
    client.post(f"/api/assistant/workflows/{wf['id']}/confirm", json={"rights": "own"})
    assert wait_for(client, wf["id"])["status"] == "done"                       # and it can still be started


def test_a_plan_whose_upload_is_gone_says_so(client, monkeypatch):
    monkeypatch.setattr(pipeline, "run_pipeline", fake_pipeline([]))
    up = client.post("/api/assistant/upload", files={"file": ("talk.mp4", b"video bytes", "video/mp4")}).json()
    wf = say(client, "make 3 clips", attachment_job_id=up["job_id"])["workflow"]
    (jobs.job_dir(up["job_id"]) / "source.mp4").unlink()                        # e.g. cleaned up by hand
    r = client.post(f"/api/assistant/workflows/{wf['id']}/confirm", json={"rights": "own"})
    assert r.status_code == 400 and "Attach the video again" in r.json()["detail"]


def test_a_make_clips_run_interrupted_by_a_restart_ends_as_an_error(client, monkeypatch):
    hold = []
    monkeypatch.setattr(pipeline, "run_pipeline", lambda job, *a: hold.append(job))     # starts, never finishes
    wf = say(client, f"shorts from {YT}")["workflow"]
    client.post(f"/api/assistant/workflows/{wf['id']}/confirm", json={"rights": "own"})
    jobs.set_status(hold[0], "transcribing")
    jobs.mark_interrupted()                                                     # the restart marks the job failed
    workflows.mark_interrupted()                                                # and the workflow follows it to the end
    done = wait_for(client, wf["id"])
    assert done["status"] == "error" and "restarted" in done["error"]


# ---------------------------------------------------------------- unavailable tools can never start anything

@pytest.mark.parametrize("text", ["get more views", "audit my channel", "find b-roll",
                                  "add a voiceover", "compose a video from my photos"])
def test_every_unavailable_shortcut_only_explains(client, text):
    before = len(store.all_of("workflows"))
    out = say(client, text)
    assert out["workflow"] is None and "isn't available yet" in out["reply"]
    assert len(store.all_of("workflows")) == before


def test_even_if_the_model_picks_an_unavailable_tool_nothing_starts(client, monkeypatch):
    monkeypatch.setattr(router, "ask_json", lambda s, u, timeout=60: {"tool": "ai_voiceover"})
    out = say(client, "please narrate my whole story for me")
    assert out["workflow"] is None and "isn't available yet" in out["reply"]


def test_only_a_make_clips_plan_can_be_started(client, folders, monkeypatch):
    existing_project(folders[0])
    monkeypatch.setattr(ideas, "ask_json", lambda s, u, timeout=240: {"ideas": []})
    wf = say(client, "video ideas")["workflow"]
    wait_for(client, wf["id"])
    r = client.post(f"/api/assistant/workflows/{wf['id']}/confirm", json={})
    assert r.status_code == 400 and "Only a Make clips plan" in r.json()["detail"]


# ---------------------------------------------------------------- the model never runs beside a heavy job

def test_the_router_never_asks_the_model_while_a_video_is_being_made(monkeypatch):
    asked, unloaded = [], []
    monkeypatch.setattr(router, "ask_json", lambda s, u, timeout=60: asked.append(u) or {"tool": "video_ideas"})
    monkeypatch.setattr(router, "unload", lambda: unloaded.append(1))
    with pipeline.heavy_job_lock:
        assert router.route("help me plan what to film this month")["tool"] is None
    assert asked == []
    assert router.route("help me plan what to film this month")["tool"] == "video_ideas"
    assert unloaded == [1] and not pipeline.heavy_job_lock.locked()           # unloaded, and the lock is free again


def test_ideas_unload_the_model_even_when_it_fails(monkeypatch):
    unloaded = []
    monkeypatch.setattr(ideas, "unload", lambda: unloaded.append(1))

    def down(*a, **k):
        raise LLMError("no ollama")
    monkeypatch.setattr(ideas, "ask_json", down)
    with pytest.raises(LLMError):
        ideas.suggest([{"start": 0, "end": 9, "text": "a long enough sentence about cooking at home every single week"}] * 3)
    assert unloaded == [1]
